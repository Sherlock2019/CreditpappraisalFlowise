import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog

logger = logging.getLogger(__name__)

SENSITIVE_KEY_PARTS = ("password", "secret", "token", "api_key", "access_key", "private_key", "client_secret")


def redact_sensitive_config(config: dict) -> dict:
    redacted = {}
    for key, value in (config or {}).items():
        lowered = str(key).lower()
        if any(part in lowered for part in SENSITIVE_KEY_PARTS):
            redacted[key] = "***REDACTED***"
        elif isinstance(value, dict):
            redacted[key] = redact_sensitive_config(value)
        else:
            redacted[key] = value
    return redacted


def log_event(db: Session, event_type: str, customer_id: int | None = None, details: dict[str, Any] | None = None) -> None:
    entry = AuditLog(event_type=event_type, customer_id=customer_id, details=details or {})
    db.add(entry)
    db.commit()
    logger.info("audit event=%s customer_id=%s", event_type, customer_id)
