from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.flowise_compat import optional_numeric_customer_id
from app.services.audit_service import write_audit_event

router = APIRouter(tags=["audit"])


class AuditEventRequest(BaseModel):
    event_type: str | None = None
    customer_id: str | int | None = None
    actor: str = "system"
    source: str = "fastapi"
    details: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None
    user_id: str | None = None
    workflow_id: str | None = None
    workflow_name: str | None = None
    question: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    policy_score: dict[str, Any] = Field(default_factory=dict)
    final_answer: dict[str, Any] | str | None = None
    human_review_required: bool = True


@router.post("/audit")
def audit_event(payload: AuditEventRequest, db: Session = Depends(get_db)) -> dict:
    event_type = payload.event_type or "flowise_workflow_audit"
    details = dict(payload.details)
    details.update(
        {
            "customer_id": payload.customer_id,
            "session_id": payload.session_id,
            "user_id": payload.user_id,
            "workflow_id": payload.workflow_id,
            "workflow_name": payload.workflow_name,
            "question": payload.question,
            "llm_provider": payload.llm_provider,
            "llm_model": payload.llm_model,
            "evidence_ids": payload.evidence_ids,
            "policy_score": payload.policy_score,
            "final_answer": payload.final_answer,
            "human_review_required": True,
        }
    )
    record = write_audit_event(
        db,
        event_type=event_type,
        customer_id=optional_numeric_customer_id(payload.customer_id),
        details=details,
        actor=payload.actor,
        source=payload.source,
    )
    return {"audit_id": f"audit_{record['id']}", "status": "logged", **record}
