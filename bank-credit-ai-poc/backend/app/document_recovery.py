from __future__ import annotations

import re
import shutil
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


def _customer_code_from_dir(path: Path) -> str | None:
    match = re.fullmatch(r"CUST-(\d{3,})", path.name, flags=re.IGNORECASE)
    return f"CUST-{int(match.group(1)):03d}" if match else None


def _safe_preload_filename(source_root: Path, file_path: Path) -> str:
    relative = file_path.relative_to(source_root).as_posix()
    parts = [part for part in relative.split("/") if part not in {"", ".", ".."}]
    flat_filename = "__".join(parts) or file_path.name
    return "".join("_" if char in '<>:"|?*' else char for char in flat_filename)


def _document_type_from_filename(filename: str) -> str:
    value = filename.casefold()
    if "bank_statement" in value:
        return "bank_statement"
    if "tax_return" in value:
        return "tax_return"
    if "income_statement" in value:
        return "income_statement"
    if "collateral_valuation" in value:
        return "collateral_valuation"
    if "loan_application" in value:
        return "loan_application"
    if "financial" in value:
        return "financial_statement"
    return "credit_document"


def _find_or_create_demo_customer(db: Session, customer_code: str) -> tuple[models.Customer, bool]:
    customer = db.query(models.Customer).filter(models.Customer.name.ilike(customer_code)).first()
    if customer:
        return customer, False

    customer = models.Customer(
        name=customer_code,
        customer_type="business",
        industry="Credit appraisal demo dataset",
        country=None,
    )
    db.add(customer)
    db.flush()
    return customer, True


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


def preload_demo_customer_documents(db: Session, source_dir: str | None = None) -> dict[str, Any]:
    """Copy the committed demo customer files into upload storage and register DB rows."""
    settings = get_settings()
    source_root = Path(source_dir or settings.demo_customer_documents_dir)
    upload_root = Path(settings.upload_dir)
    recovered_customers = 0
    recovered_documents = 0
    existing_documents = 0
    copied_files = 0
    skipped_files = 0

    if not source_root.exists():
        return {
            "source_dir": str(source_root),
            "upload_dir": str(upload_root),
            "recovered_customers": 0,
            "recovered_documents": 0,
            "existing_documents": 0,
            "copied_files": 0,
            "skipped_files": 0,
            "cache": document_memory_cache.summary(),
        }

    upload_root.mkdir(parents=True, exist_ok=True)

    for customer_dir in sorted(source_root.iterdir(), key=lambda item: item.name.casefold()):
        if not customer_dir.is_dir():
            continue
        customer_code = _customer_code_from_dir(customer_dir)
        if not customer_code:
            skipped_files += sum(1 for item in customer_dir.rglob("*") if item.is_file())
            continue

        customer, created_customer = _find_or_create_demo_customer(db, customer_code)
        if created_customer:
            recovered_customers += 1

        customer_upload_dir = upload_root / str(customer.id)
        customer_upload_dir.mkdir(parents=True, exist_ok=True)

        for file_path in sorted(customer_dir.iterdir(), key=lambda item: item.name.casefold()):
            if not file_path.is_file():
                continue
            if file_path.name.endswith(":Zone.Identifier") or file_path.suffix.lower() not in SUPPORTED_SUFFIXES:
                skipped_files += 1
                continue

            filename = _safe_preload_filename(source_root, file_path)
            destination = customer_upload_dir / filename
            shutil.copy2(file_path, destination)
            copied_files += 1

            document_type = _document_type_from_filename(file_path.name)
            existing = (
                db.query(models.Document)
                .filter(
                    models.Document.customer_id == customer.id,
                    models.Document.filename == filename,
                    models.Document.document_type == document_type,
                )
                .order_by(models.Document.id.desc())
                .first()
            )
            if existing:
                existing.file_path = str(destination)
                existing.status = existing.status or "uploaded"
                existing.source_type = "demo_dataset"
                existing.source_metadata = {
                    "preloaded_demo_dataset": True,
                    "source_path": file_path.relative_to(source_root).as_posix(),
                }
                existing_documents += 1
                continue

            db.add(
                models.Document(
                    customer_id=customer.id,
                    filename=filename,
                    file_path=str(destination),
                    document_type=document_type,
                    status="uploaded",
                    source_type="demo_dataset",
                    source_metadata={
                        "preloaded_demo_dataset": True,
                        "source_path": file_path.relative_to(source_root).as_posix(),
                    },
                )
            )
            recovered_documents += 1

    _sync_customer_sequence(db)
    db.commit()
    cache = document_memory_cache.warm_from_db(db)
    return {
        "source_dir": str(source_root),
        "upload_dir": str(upload_root),
        "recovered_customers": recovered_customers,
        "recovered_documents": recovered_documents,
        "existing_documents": existing_documents,
        "copied_files": copied_files,
        "skipped_files": skipped_files,
        "cache": cache,
    }
