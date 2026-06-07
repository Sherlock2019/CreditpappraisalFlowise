from __future__ import annotations

from sqlalchemy.orm import Session

from app import models


def ensure_customer(db: Session, customer_id: str | int) -> models.Customer:
    """Resolve numeric UI ids and Flowise string ids to an internal customer row."""
    raw = str(customer_id or "").strip()
    if not raw:
        raise ValueError("customer_id is required")

    if raw.isdigit():
        existing = db.query(models.Customer).filter(models.Customer.id == int(raw)).first()
        if existing:
            return existing

    existing_by_name = db.query(models.Customer).filter(models.Customer.name == raw).first()
    if existing_by_name:
        return existing_by_name

    customer = models.Customer(
        name=raw,
        customer_type="flowise_customer",
        industry="Credit appraisal",
        country=None,
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def optional_numeric_customer_id(customer_id: str | int | None) -> int | None:
    raw = str(customer_id or "").strip()
    return int(raw) if raw.isdigit() else None


def external_document_id(document_id: int | str) -> str:
    return f"doc_{document_id}"


def parse_external_document_id(document_id: int | str) -> int | None:
    raw = str(document_id or "").strip()
    if raw.startswith("doc_"):
        raw = raw[4:]
    return int(raw) if raw.isdigit() else None
