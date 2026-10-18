"""Governed execution of the Flowise credit appraisal Agentflow.

Ownership: Flowise runs the reasoning and tool calls inside a run. FastAPI owns the run record,
the approval gate, the decision of record and the audit trail, and is the only caller that may
resume a paused run.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.auth.principal import Principal
from app.auth.tokens import mint_run_tokens
from app.config import get_settings
from app.correlation import current_correlation_id
from app.schemas_v1 import AgentExecuteRequest
from app.services.audit_chain import append_audit_event

logger = logging.getLogger(__name__)

TOOL_ACTIVE_STATUSES = {"running", "resuming"}
TRANSIENT_STATUS_CODES = {502, 503, 504}
POSITIVE_DECISIONS = {"approved", "conditional"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_aware(value: datetime | None) -> datetime | None:
    # SQLite drops tzinfo; every timestamp we write is UTC.
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


class AgentflowClient:
    """Thin synchronous Flowise prediction client with bounded retries on gateway errors."""

    def __init__(self, base_url: str, flow_id: str, api_key: str = "", timeout: float = 900, transport: httpx.BaseTransport | None = None, max_retries: int = 2):
        self.base_url = base_url.rstrip("/")
        self.flow_id = flow_id
        self.api_key = api_key
        self.timeout = timeout
        self.transport = transport
        self.max_retries = max_retries

    def predict(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.base_url or not self.flow_id:
            raise RuntimeError("Flowise Agentflow is not configured (FLOWISE_API_URL / FLOWISE_AGENTFLOW_ID)")
        headers = {"Content-Type": "application/json", "X-Correlation-ID": current_correlation_id()}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        url = f"{self.base_url}/api/v1/prediction/{self.flow_id}"
        last_error = "Flowise prediction failed"
        with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
            for attempt in range(self.max_retries + 1):
                try:
                    response = client.post(url, json=payload, headers=headers)
                except httpx.TransportError as exc:
                    last_error = f"Flowise unreachable: {exc}"
                else:
                    if response.status_code not in TRANSIENT_STATUS_CODES:
                        if response.status_code >= 400:
                            # Flowise error bodies can echo prompts; keep only the status and a short prefix.
                            raise RuntimeError(f"Flowise returned {response.status_code}: {response.text[:300]}")
                        return response.json()
                    last_error = f"Flowise returned {response.status_code}"
                if attempt < self.max_retries:
                    time.sleep(0.5 * 2**attempt)
        raise RuntimeError(last_error)


def get_agentflow_client() -> AgentflowClient:
    settings = get_settings()
    return AgentflowClient(
        base_url=settings.flowise_base_url or settings.flowise_api_url,
        flow_id=settings.flowise_agentflow_id,
        api_key=settings.flowise_api_key,
        timeout=settings.flowise_agentflow_timeout_seconds,
    )


def customer_in_tenant(db: Session, customer_id: int, tenant_id: str) -> models.Customer:
    customer = db.get(models.Customer, customer_id)
    if customer is None or customer.tenant_id != tenant_id:
        # Same answer for "missing" and "other tenant", so tenant membership is not disclosed.
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


def run_in_tenant(db: Session, run_id: str, tenant_id: str) -> models.AgentRun:
    run = db.get(models.AgentRun, run_id)
    if run is None or run.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return run


def pending_approval(db: Session, run_id: str) -> models.Approval | None:
    return db.execute(select(models.Approval).where(models.Approval.run_id == run_id).order_by(models.Approval.created_at.desc())).scalars().first()


def _flow_vars(run: models.AgentRun) -> dict[str, Any]:
    req = run.request
    return {
        "run_id": run.id,
        "tenant_id": run.tenant_id,
        "correlation_id": run.correlation_id,
        "requested_by": run.requested_by,
        "customer_id": str(run.customer_id),
        "session_id": run.id,
        "loan_amount": req.get("loan_amount", 0),
        "collateral_value": req.get("collateral_value", 0),
        "monthly_income": req.get("monthly_income", 0),
        "monthly_debt_payments": req.get("monthly_debt_payments", 0),
        "term_months": req.get("term_months", 60),
        # Fresh run-bound identities on every call; the LLM never sees these values.
        **mint_run_tokens(run_id=run.id, tenant_id=run.tenant_id, customer_id=run.customer_id),
    }


def _apply_flow_result(db: Session, run: models.AgentRun, data: dict[str, Any]) -> None:
    action = data.get("action") or {}
    run.result = {"answer": data.get("text") or "", "flowise_execution_id": data.get("executionId"), "paused": bool(action)}
    if action:
        approval = pending_approval(db, run.id)
        if approval is None or approval.status != "pending":
            # A pause without a recorded approval request would leave nothing for a human to decide.
            run.status = "failed"
            run.error = "Agentflow paused for human input without creating an approval request"
        else:
            run.status = "awaiting_approval"
            run.human_input_node_id = (action.get("data") or {}).get("nodeId") or run.human_input_node_id
    else:
        run.status = "completed"
    run.updated_at = utcnow()


def start_run(db: Session, principal: Principal, payload: AgentExecuteRequest, idempotency_key: str | None, client: AgentflowClient) -> models.AgentRun:
    customer_in_tenant(db, payload.customer_id, principal.tenant_id)
    if idempotency_key:
        existing = db.execute(
            select(models.AgentRun).where(models.AgentRun.tenant_id == principal.tenant_id, models.AgentRun.idempotency_key == idempotency_key)
        ).scalar_one_or_none()
        if existing is not None:
            if existing.customer_id != payload.customer_id or existing.request.get("request") != payload.request:
                raise HTTPException(status_code=409, detail="Idempotency-Key was already used for a different request")
            return existing

    now = utcnow()
    run_id = str(uuid.uuid4())
    run = models.AgentRun(
        id=run_id,
        tenant_id=principal.tenant_id,
        customer_id=payload.customer_id,
        requested_by=principal.subject,
        status="running",
        flow_id=client.flow_id,
        chat_id=run_id,
        correlation_id=current_correlation_id() or uuid.uuid4().hex,
        idempotency_key=idempotency_key,
        request=payload.model_dump(),
        result={},
        created_at=now,
        updated_at=now,
    )
    db.add(run)
    append_audit_event(db, principal, "agent_run_started", customer_id=payload.customer_id, run_id=run_id, details={"flow_id": client.flow_id})
    # Commit before calling Flowise: its tool calls come back on other requests and must see the run.
    db.commit()

    try:
        data = client.predict({"question": payload.request, "chatId": run.chat_id, "overrideConfig": {"sessionId": run.chat_id, "vars": _flow_vars(run)}})
    except Exception as exc:
        db.rollback()
        run.status, run.error, run.updated_at = "failed", str(exc)[:500], utcnow()
        append_audit_event(db, principal, "agent_run_failed", customer_id=run.customer_id, run_id=run.id, details={"error": run.error})
        db.commit()
        return run

    db.expire_all()
    run = db.get(models.AgentRun, run_id)
    _apply_flow_result(db, run, data)
    append_audit_event(db, principal, f"agent_run_{run.status}", customer_id=run.customer_id, run_id=run.id, details={"error": run.error})
    db.commit()
    return run


def resume_run(db: Session, principal: Principal, run: models.AgentRun, approval: models.Approval, client: AgentflowClient) -> str | None:
    """Resume the paused Agentflow after a human decision. Returns an error message if the resume failed."""
    run.status, run.updated_at = "resuming", utcnow()
    db.commit()
    human_input: dict[str, Any] = {
        "type": "proceed" if approval.status in POSITIVE_DECISIONS else "reject",
        "feedback": (approval.decision_notes or approval.status)[:2000],
    }
    if run.human_input_node_id:
        human_input["startNodeId"] = run.human_input_node_id
    try:
        data = client.predict({"question": "", "chatId": run.chat_id, "humanInput": human_input, "overrideConfig": {"sessionId": run.chat_id, "vars": _flow_vars(run)}})
    except Exception as exc:
        db.rollback()
        run.status, run.error, run.updated_at = "failed", f"Resume failed: {str(exc)[:450]}", utcnow()
        append_audit_event(db, principal, "agent_run_resume_failed", customer_id=run.customer_id, run_id=run.id, details={"error": run.error})
        db.commit()
        return run.error
    db.expire_all()
    run = db.get(models.AgentRun, run.id)
    run.result = {**(run.result or {}), "answer": data.get("text") or "", "paused": False}
    run.status, run.updated_at = "completed", utcnow()
    append_audit_event(db, principal, "agent_run_completed", customer_id=run.customer_id, run_id=run.id, details={"approval_id": approval.id})
    db.commit()
    return None


def new_approval(db: Session, principal: Principal, run: models.AgentRun, **fields: Any) -> models.Approval:
    now = utcnow()
    approval = models.Approval(
        id=str(uuid.uuid4()),
        tenant_id=run.tenant_id,
        run_id=run.id,
        customer_id=run.customer_id,
        status="pending",
        requested_by_agent=principal.actor,
        run_requested_by=run.requested_by,
        expires_at=now + timedelta(hours=get_settings().approval_ttl_hours),
        created_at=now,
        **fields,
    )
    db.add(approval)
    return approval


def expire_if_due(db: Session, approval: models.Approval) -> bool:
    if approval.status == "pending" and as_aware(approval.expires_at) <= utcnow():
        approval.status = "expired"
        return True
    return False
