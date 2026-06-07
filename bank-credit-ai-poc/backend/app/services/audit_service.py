from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.audit import redact_sensitive_config
from app.config import get_settings
from app.models import AuditLog


def write_audit_event(
    db: Session,
    event_type: str,
    customer_id: int | None,
    details: dict[str, Any] | None = None,
    actor: str = "system",
    source: str = "fastapi",
) -> dict:
    safe_details = redact_sensitive_config(details or {})
    record = AuditLog(event_type=event_type, customer_id=customer_id, details=safe_details)
    db.add(record)
    db.commit()
    db.refresh(record)

    event = {
        "id": record.id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "customer_id": customer_id,
        "actor": actor,
        "source": source,
        "details": safe_details,
    }
    settings = get_settings()
    log_dir = Path(settings.audit_log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{datetime.now(timezone.utc).date().isoformat()}.jsonl"
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=True, sort_keys=True) + "\n")
    return event
