from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.auth.dependencies import require_permission
from app.auth.principal import Principal
from app.config import get_settings
from app.database import get_db
from app.routers.v1.agents import run_out
from app.schemas_v1 import ApiError, ApprovalDecisionRequest, ApprovalDecisionResponse, ApprovalOut, ApprovalStatus, Page
from app.services.agent_runtime import AgentflowClient, expire_if_due, get_agentflow_client, resume_run, utcnow
from app.services.audit_chain import append_audit_event

router = APIRouter(
    prefix="/api/v1/approvals",
    tags=["v1 approvals"],
    responses={401: {"model": ApiError}, 403: {"model": ApiError}, 404: {"model": ApiError}, 409: {"model": ApiError}},
)


def _approval_in_tenant(db: Session, approval_id: str, tenant_id: str) -> models.Approval:
    approval = db.get(models.Approval, approval_id)
    if approval is None or approval.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Approval not found")
    return approval


@router.get("", response_model=Page, summary="Approval queue for the caller's tenant")
def list_approvals(
    status: ApprovalStatus | None = Query(default="pending"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_permission("approval:read")),
    db: Session = Depends(get_db),
) -> Page:
    query = select(models.Approval).where(models.Approval.tenant_id == principal.tenant_id)
    if status:
        query = query.where(models.Approval.status == status)
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = db.execute(query.order_by(models.Approval.created_at.asc()).limit(limit).offset(offset)).scalars().all()
    if any(expire_if_due(db, row) for row in rows):
        db.commit()
    return Page(items=[ApprovalOut.model_validate(row) for row in rows], limit=limit, offset=offset, total=total)


@router.get("/{approval_id}", response_model=ApprovalOut)
def get_approval(approval_id: str, principal: Principal = Depends(require_permission("approval:read")), db: Session = Depends(get_db)) -> ApprovalOut:
    approval = _approval_in_tenant(db, approval_id, principal.tenant_id)
    if expire_if_due(db, approval):
        db.commit()
    return ApprovalOut.model_validate(approval)


@router.post("/{approval_id}/decision", response_model=ApprovalDecisionResponse, summary="Record the human credit decision and resume the run")
def decide(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    principal: Principal = Depends(require_permission("approval:decide")),
    db: Session = Depends(get_db),
    client: AgentflowClient = Depends(get_agentflow_client),
) -> ApprovalDecisionResponse:
    """The only way a credit decision is recorded for an Agentflow run. The decider is taken from the
    token, must be a human with `approval:decide`, and (by default) must not be the person who started the run."""
    approval = _approval_in_tenant(db, approval_id, principal.tenant_id)
    if expire_if_due(db, approval):
        append_audit_event(db, principal, "approval_expired", customer_id=approval.customer_id, run_id=approval.run_id, details={"approval_id": approval.id})
        db.commit()
        raise HTTPException(status_code=409, detail="Approval has expired; start a new appraisal run")
    if approval.status != "pending":
        raise HTTPException(status_code=409, detail=f"Approval is already {approval.status}")
    if get_settings().approval_require_four_eyes and principal.subject == approval.run_requested_by:
        raise HTTPException(status_code=403, detail="Four-eyes rule: the officer who started the run cannot approve it")
    if payload.decision == "conditional" and not payload.conditions:
        raise HTTPException(status_code=422, detail="A conditional decision needs at least one condition")
    funded = payload.decision in {"approved", "conditional"}
    if funded and payload.approved_amount <= 0:
        raise HTTPException(status_code=422, detail="approved_amount must be positive for an approval")

    run = db.get(models.AgentRun, approval.run_id)
    # Decision of record, written to the existing decision table so LISA reports keep working.
    final = models.FinalDecision(
        committee_case_id=f"APR-{approval.id}",
        customer_id=str(approval.customer_id),
        decision=payload.decision,
        approved_amount=payload.approved_amount if funded else 0,
        approved_rate_pct=payload.approved_rate_pct if funded else 0,
        conditions=payload.conditions if funded else [],
        decision_by=principal.subject,
        decision_notes=payload.notes,
    )
    db.add(final)
    db.flush()
    approval.status = payload.decision
    approval.approved_amount = final.approved_amount
    approval.approved_rate_pct = final.approved_rate_pct
    approval.conditions = final.conditions
    approval.decision_notes = payload.notes
    approval.decided_by = principal.subject
    approval.decided_at = utcnow()
    approval.final_decision_id = final.id
    append_audit_event(
        db,
        principal,
        "credit_decision_recorded",
        customer_id=approval.customer_id,
        run_id=approval.run_id,
        details={
            "approval_id": approval.id,
            "decision": payload.decision,
            "final_decision_id": final.id,
            "ai_recommendation": (approval.recommendation or {}).get("recommendation"),
            "overrides_ai": (approval.recommendation or {}).get("recommendation") != payload.decision,
        },
    )
    db.commit()

    resume_error = None
    if run is not None and run.status == "awaiting_approval":
        resume_error = resume_run(db, principal, run, approval, client)
        run = db.get(models.AgentRun, approval.run_id)
    db.refresh(approval)
    return ApprovalDecisionResponse(approval=ApprovalOut.model_validate(approval), run=run_out(db, run), resume_error=resume_error)
