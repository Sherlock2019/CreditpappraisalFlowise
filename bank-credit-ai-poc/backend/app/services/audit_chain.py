"""Hash-chained audit events, written inside the caller's transaction (flush, never commit)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.audit import redact_sensitive_config
from app.auth.principal import Principal
from app.correlation import current_correlation_id
from app.models import AuditEvent

GENESIS_HASH = "0" * 64


def _canonical(event: AuditEvent) -> str:
    return json.dumps(
        {
            "tenant_id": event.tenant_id,
            "event_type": event.event_type,
            "actor": event.actor,
            "actor_kind": event.actor_kind,
            "customer_id": event.customer_id,
            "run_id": event.run_id,
            "correlation_id": event.correlation_id,
            "details": event.details,
            "occurred_at": event.occurred_at,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )


def _digest(prev_hash: str, event: AuditEvent) -> str:
    return hashlib.sha256((prev_hash + _canonical(event)).encode("utf-8")).hexdigest()


def _lock_tenant_chain(db: Session, tenant_id: str) -> None:
    # Serialise appends per tenant so two writers cannot fork the chain.
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"audit:{tenant_id}"})


def append_audit_event(
    db: Session,
    principal: Principal,
    event_type: str,
    *,
    customer_id: int | None = None,
    run_id: str | None = None,
    details: dict[str, Any] | None = None,
    tenant_id: str | None = None,
) -> AuditEvent:
    tenant = tenant_id or principal.tenant_id
    _lock_tenant_chain(db, tenant)
    last = db.execute(
        select(AuditEvent.hash).where(AuditEvent.tenant_id == tenant).order_by(AuditEvent.id.desc()).limit(1)
    ).scalar_one_or_none()
    event = AuditEvent(
        tenant_id=tenant,
        event_type=event_type,
        actor=principal.actor,
        actor_kind=principal.kind,
        customer_id=customer_id,
        run_id=run_id or principal.run_id,
        correlation_id=current_correlation_id() or None,
        # Round-trip through JSON so the hashed form equals what the database returns later.
        details=json.loads(json.dumps(redact_sensitive_config(details or {}), default=str)),
        occurred_at=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        prev_hash=last or GENESIS_HASH,
    )
    event.hash = _digest(event.prev_hash, event)
    db.add(event)
    db.flush()
    return event


def verify_chain(db: Session, tenant_id: str) -> dict[str, Any]:
    events = db.execute(select(AuditEvent).where(AuditEvent.tenant_id == tenant_id).order_by(AuditEvent.id)).scalars().all()
    expected_prev = GENESIS_HASH
    for event in events:
        if event.prev_hash != expected_prev or _digest(event.prev_hash, event) != event.hash:
            return {"valid": False, "events_checked": len(events), "first_invalid_event_id": event.id, "head_hash": None}
        expected_prev = event.hash
    return {"valid": True, "events_checked": len(events), "first_invalid_event_id": None, "head_hash": expected_prev}
