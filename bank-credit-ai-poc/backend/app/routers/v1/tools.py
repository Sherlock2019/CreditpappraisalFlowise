"""Agent tool gateway: the only data and action surface the Flowise Agentflow can reach.

Every call is authorised from the run-bound agent token alone. Customer, tenant and run come from
the token; a customer_id in the body must match it, so text injected into a prompt cannot redirect
a tool to another customer. No tool can record a credit decision.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.auth.dependencies import require_agent, require_scope
from app.auth.principal import Principal
from app.auth.tokens import agent_registry
from app.correlation import correlation_id_var
from app.database import get_db
from app.flowise_compat import external_document_id
from app.models import AgentRun, Approval
from app.routers.loan_policy import calculate_policy_score, draft_customer_decision_email
from app.schemas_v1 import (
    ApiError,
    ApprovalRequestInput,
    ApprovalRequestOutput,
    ApprovalStatusOutput,
    AuditEventAck,
    AuditEventInput,
    EmailDraftInput,
    EvidenceItem,
    EvidenceSearchInput,
    EvidenceSearchOutput,
)
from app.services.agent_runtime import TOOL_ACTIVE_STATUSES, expire_if_due, new_approval, pending_approval
from app.services.audit_chain import append_audit_event
from app.services.retrieval_service import missing_documents_from_context, retrieve_customer_context

router = APIRouter(
    prefix="/api/v1/tools",
    tags=["v1 agent tools"],
    responses={401: {"model": ApiError}, 403: {"model": ApiError}, 404: {"model": ApiError}, 409: {"model": ApiError}},
)

agent_principal = require_agent()


def _active_run(db: Session, principal: Principal, customer_id: int | None = None) -> AgentRun:
    run = db.get(AgentRun, principal.run_id)
    if run is None or run.tenant_id != principal.tenant_id or run.customer_id != principal.customer_id:
        raise HTTPException(status_code=403, detail="Agent token is not bound to a valid run")
    if run.status not in TOOL_ACTIVE_STATUSES:
        # Tokens are useless while a run waits for a human or after it ends.
        raise HTTPException(status_code=403, detail=f"Run is {run.status}; tools are disabled")
    if customer_id is not None and customer_id != principal.customer_id:
        raise HTTPException(status_code=403, detail="customer_id does not match the customer bound to this run")
    # Trace tool calls under the run's correlation id, whatever header the caller sent.
    correlation_id_var.set(run.correlation_id)
    return run


def _audit_denied(db: Session, principal: Principal, tool: str, reason: str) -> None:
    run = db.get(AgentRun, principal.run_id)
    if run is not None and run.tenant_id == principal.tenant_id:
        correlation_id_var.set(run.correlation_id)
    append_audit_event(db, principal, "agent_tool_denied", customer_id=principal.customer_id, details={"tool": tool, "reason": reason})
    db.commit()


@router.get("/manifest")
def tool_manifest(principal: Principal = Depends(agent_principal)) -> dict:
    """MCP-style tool listing (name, description, inputSchema) filtered to the caller's scopes."""
    schemas_by_tool = {
        "evidence.search": EvidenceSearchInput,
        "policy.score": schemas.LoanPolicyRequest,
        "approval.request": ApprovalRequestInput,
        "approval.read": None,
        "email.draft": EmailDraftInput,
        "audit.write": AuditEventInput,
    }
    tools = []
    for name, spec in agent_registry()["tools"].items():
        scope = spec["scope"]
        allowed = any(p == scope or (scope.endswith("{domain}") and p.startswith(scope[: -len("{domain}")])) for p in principal.permissions)
        if not allowed:
            continue
        model = schemas_by_tool[name]
        tools.append(
            {
                "name": name,
                "method": spec["method"],
                "path": spec["path"],
                "inputSchema": model.model_json_schema() if model else {"type": "object", "properties": {}},
            }
        )
    return {"agent_id": principal.agent_id, "tools": tools}


@router.post("/evidence.search", response_model=EvidenceSearchOutput)
def evidence_search(payload: EvidenceSearchInput, principal: Principal = Depends(agent_principal), db: Session = Depends(get_db)) -> EvidenceSearchOutput:
    scope = f"tool:evidence.search:{payload.domain}"
    if scope not in principal.permissions:
        _audit_denied(db, principal, "evidence.search", f"missing {scope}")
        require_scope(principal, scope)
    try:
        _active_run(db, principal, payload.customer_id)
    except HTTPException as exc:
        _audit_denied(db, principal, "evidence.search", str(exc.detail))
        raise
    context = retrieve_customer_context(db, principal.customer_id, payload.question, payload.top_k)
    evidence = [
        EvidenceItem(
            chunk_id=f"chunk_{chunk.get('document_id', '')}_{chunk.get('chunk_index', '')}",
            document_id=external_document_id(chunk.get("document_id", "")),
            document_name=chunk.get("filename") or "Unknown document",
            page=chunk.get("page_number"),
            text=chunk.get("chunk_text") or "",
            score=float(chunk.get("score") or 0),
        )
        for chunk in context.get("retrieved_chunks", [])
    ]
    append_audit_event(
        db,
        principal,
        "agent_tool_evidence_search",
        customer_id=principal.customer_id,
        details={"domain": payload.domain, "evidence_ids": [item.chunk_id for item in evidence]},
    )
    db.commit()
    return EvidenceSearchOutput(
        customer_id=principal.customer_id,
        domain=payload.domain,
        evidence=evidence,
        missing_documents=missing_documents_from_context(context),
    )


@router.post("/policy.score", response_model=schemas.LoanPolicyResponse)
def policy_score(payload: schemas.LoanPolicyRequest, principal: Principal = Depends(agent_principal), db: Session = Depends(get_db)) -> schemas.LoanPolicyResponse:
    require_scope(principal, "tool:policy.score")
    if str(payload.customer_id).strip() != str(principal.customer_id):
        _audit_denied(db, principal, "policy.score", "customer_id mismatch")
        raise HTTPException(status_code=403, detail="customer_id does not match the customer bound to this run")
    _active_run(db, principal)
    result = calculate_policy_score(payload, db)
    append_audit_event(db, principal, "agent_tool_policy_score", customer_id=principal.customer_id, details={"policy_score_id": result.policy_score_id})
    db.commit()
    return result


@router.post("/approval.request", response_model=ApprovalRequestOutput, status_code=201)
def approval_request(payload: ApprovalRequestInput, principal: Principal = Depends(agent_principal), db: Session = Depends(get_db)) -> ApprovalRequestOutput:
    require_scope(principal, "tool:approval.request")
    run = _active_run(db, principal, payload.customer_id)
    existing = pending_approval(db, run.id)
    if existing is not None and existing.status == "pending":
        approval = existing  # idempotent: one open approval per run
    else:
        approval = new_approval(
            db,
            principal,
            run,
            recommendation={
                "recommendation": payload.recommendation,
                "proposed_amount": payload.proposed_amount,
                "proposed_rate_pct": payload.proposed_rate_pct,
                "conditions": payload.conditions,
                "reason_summary": payload.reason_summary,
                "memo": payload.memo,
            },
            policy_score_id=payload.policy_score_id,
            evidence_ids=payload.evidence_ids,
            conditions=[],
        )
        db.flush()
        append_audit_event(
            db,
            principal,
            "approval_requested",
            customer_id=run.customer_id,
            details={"approval_id": approval.id, "ai_recommendation": payload.recommendation, "policy_score_id": payload.policy_score_id},
        )
    db.commit()
    return ApprovalRequestOutput(
        approval_id=approval.id,
        status=approval.status,
        expires_at=approval.expires_at,
        decide_with=f"POST /api/v1/approvals/{approval.id}/decision (authenticated human with approval:decide)",
    )


@router.get("/approvals/{approval_id}", response_model=ApprovalStatusOutput)
def approval_status(approval_id: str, principal: Principal = Depends(agent_principal), db: Session = Depends(get_db)) -> ApprovalStatusOutput:
    require_scope(principal, "tool:approval.read")
    run = _active_run(db, principal)
    approval = db.get(Approval, approval_id)
    if approval is None or approval.run_id != run.id:
        raise HTTPException(status_code=404, detail="Approval not found for this run")
    if expire_if_due(db, approval):
        db.commit()
    decided = approval.decided_by is not None and approval.status not in {"pending", "expired"}
    return ApprovalStatusOutput(
        approval_id=approval.id,
        status=approval.status,
        decision_recorded=decided,
        decided_by=approval.decided_by,
        decided_at=approval.decided_at,
        final_decision_id=f"DEC-{approval.final_decision_id}" if approval.final_decision_id else None,
        approved_amount=approval.approved_amount,
        approved_rate_pct=approval.approved_rate_pct,
        conditions=approval.conditions or [],
    )


@router.post("/email.draft", response_model=schemas.CustomerDecisionEmailDraftResponse)
def email_draft(payload: EmailDraftInput, principal: Principal = Depends(agent_principal), db: Session = Depends(get_db)) -> schemas.CustomerDecisionEmailDraftResponse:
    require_scope(principal, "tool:email.draft")
    run = _active_run(db, principal)
    approval = db.get(Approval, payload.approval_id)
    if approval is None or approval.run_id != run.id:
        raise HTTPException(status_code=404, detail="Approval not found for this run")
    if approval.decided_by is None or approval.status in {"pending", "expired"}:
        raise HTTPException(status_code=409, detail="No human decision is recorded; an email cannot be drafted")
    # The draft is built from the recorded human decision, never from LLM output.
    draft = draft_customer_decision_email(
        schemas.CustomerDecisionEmailDraftRequest(
            customer_id=str(run.customer_id),
            customer_email=payload.customer_email,
            decision=approval.status,
            approved_amount=approval.approved_amount or 0,
            approved_rate_pct=approval.approved_rate_pct or 0,
            conditions=approval.conditions or [],
            reason_summary=(approval.recommendation or {}).get("reason_summary") or None,
            officer_name=approval.decided_by,
            decision_id=f"DEC-{approval.final_decision_id}" if approval.final_decision_id else None,
            language=payload.language,
        ),
        db,
    )
    append_audit_event(db, principal, "agent_tool_email_draft", customer_id=run.customer_id, details={"approval_id": approval.id, "email_draft_id": draft.email_draft_id})
    db.commit()
    return draft


@router.post("/audit.event", response_model=AuditEventAck, status_code=201)
def audit_event(payload: AuditEventInput, principal: Principal = Depends(agent_principal), db: Session = Depends(get_db)) -> AuditEventAck:
    require_scope(principal, "tool:audit.write")
    _active_run(db, principal, payload.customer_id)
    # actor, tenant and run come from the token; the body cannot claim to be a human.
    event = append_audit_event(db, principal, f"flow_{payload.event_type}", customer_id=principal.customer_id, details=payload.details)
    db.commit()
    return AuditEventAck(audit_event_id=event.id, hash=event.hash)
