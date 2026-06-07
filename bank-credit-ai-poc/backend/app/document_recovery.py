from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.document_cache import document_memory_cache


SUPPORTED_SUFFIXES = {".pdf", ".txt", ".csv", ".xlsx", ".xls", ".docx"}


def _customer_id_from_dir(path: Path) -> int | None:
    try:
        return int(path.name)
    except ValueError:
        return None


def _sync_customer_sequence(db: Session) -> None:
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    db.execute(
        text(
            """
            select setval(
                pg_get_serial_sequence('customers', 'id'),
                greatest(coalesce((select max(id) from customers), 1), 1),
                true
            )
            """
        )
    )


def recover_uploaded_files_from_disk(db: Session) -> dict[str, Any]:
    """Re-register files from the persistent upload directory if DB rows are missing."""
    upload_root = Path(get_settings().upload_dir)
    recovered_customers = 0
    recovered_documents = 0
    existing_documents = 0
    skipped_files = 0

    if not upload_root.exists():
        return {
            "upload_dir": str(upload_root),
            "recovered_customers": 0,
            "recovered_documents": 0,
            "existing_documents": 0,
            "skipped_files": 0,
            "cache": document_memory_cache.summary(),
        }

    for customer_dir in sorted(upload_root.iterdir(), key=lambda item: item.name):
        if not customer_dir.is_dir():
            continue
        customer_id = _customer_id_from_dir(customer_dir)
        if customer_id is None:
            skipped_files += sum(1 for item in customer_dir.rglob("*") if item.is_file())
            continue

        customer = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
        if not customer:
            db.add(models.Customer(id=customer_id, name=f"Recovered Customer {customer_id}", customer_type="business"))
            recovered_customers += 1

        for file_path in sorted(customer_dir.iterdir(), key=lambda item: item.name.casefold()):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in SUPPORTED_SUFFIXES:
                skipped_files += 1
                continue

            existing = (
                db.query(models.Document)
                .filter(
                    models.Document.customer_id == customer_id,
                    models.Document.filename == file_path.name,
                )
                .order_by(models.Document.id.desc())
                .first()
            )
            if existing:
                existing.file_path = str(file_path)
                existing_documents += 1
                continue

            db.add(
                models.Document(
                    customer_id=customer_id,
                    filename=file_path.name,
                    file_path=str(file_path),
                    document_type="financial_statement",
                    status="uploaded",
                    source_type="manual_upload",
                    source_metadata={"recovered_from_disk": True},
                )
            )
            recovered_documents += 1

    _sync_customer_sequence(db)
    db.commit()
    cache = document_memory_cache.warm_from_db(db)
    return {
        "upload_dir": str(upload_root),
        "recovered_customers": recovered_customers,
        "recovered_documents": recovered_documents,
        "existing_documents": existing_documents,
        "skipped_files": skipped_files,
        "cache": cache,
    }
