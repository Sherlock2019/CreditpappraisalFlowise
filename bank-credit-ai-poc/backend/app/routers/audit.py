from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.audit_service import write_audit_event

router = APIRouter(tags=["audit"])


class AuditEventRequest(BaseModel):
    event_type: str
    customer_id: int | None = None
    actor: str = "system"
    source: str = "fastapi"
    details: dict[str, Any] = Field(default_factory=dict)


@router.post("/audit")
def audit_event(payload: AuditEventRequest, db: Session = Depends(get_db)) -> dict:
    return write_audit_event(
        db,
        event_type=payload.event_type,
        customer_id=payload.customer_id,
        details=payload.details,
        actor=payload.actor,
        source=payload.source,
    )
