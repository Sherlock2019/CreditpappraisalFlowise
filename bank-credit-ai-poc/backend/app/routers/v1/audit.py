from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_permission
from app.auth.principal import Principal
from app.database import get_db
from app.models import AuditEvent
from app.schemas_v1 import ApiError, AuditEventOut, AuditVerifyResponse, Page
from app.services.audit_chain import verify_chain

router = APIRouter(prefix="/api/v1/audit", tags=["v1 audit"], responses={401: {"model": ApiError}, 403: {"model": ApiError}})


@router.get("/events", response_model=Page)
def list_events(
    run_id: str | None = None,
    customer_id: int | None = None,
    event_type: str | None = None,
    actor_kind: str | None = Query(default=None, pattern="^(human|agent|anonymous)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_permission("audit:read")),
    db: Session = Depends(get_db),
) -> Page:
    query = select(AuditEvent).where(AuditEvent.tenant_id == principal.tenant_id)
    if run_id:
        query = query.where(AuditEvent.run_id == run_id)
    if customer_id is not None:
        query = query.where(AuditEvent.customer_id == customer_id)
    if event_type:
        query = query.where(AuditEvent.event_type == event_type)
    if actor_kind:
        query = query.where(AuditEvent.actor_kind == actor_kind)
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = db.execute(query.order_by(AuditEvent.id.desc()).limit(limit).offset(offset)).scalars().all()
    return Page(items=[AuditEventOut.model_validate(row) for row in rows], limit=limit, offset=offset, total=total)


@router.get("/verify", response_model=AuditVerifyResponse, summary="Recompute the tenant's audit hash chain")
def verify(principal: Principal = Depends(require_permission("audit:verify")), db: Session = Depends(get_db)) -> AuditVerifyResponse:
    return AuditVerifyResponse(**verify_chain(db, principal.tenant_id))
