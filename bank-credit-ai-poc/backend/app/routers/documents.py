from collections import defaultdict
import re
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.audit import log_event
from app.config import get_settings
from app.database import get_db
from app.document_cache import document_memory_cache
from app.document_recovery import recover_uploaded_files_from_disk
from app.document_parser import chunk_sections, parse_document
from app.embeddings import create_embedding
from app.flowise_compat import ensure_customer, external_document_id, parse_external_document_id

router = APIRouter(tags=["documents"])

SUPPORTED_SUFFIXES = {".pdf", ".txt", ".csv", ".xlsx", ".xls", ".docx", ".png", ".jpg", ".jpeg"}
DOCUMENT_STATUS_RANK = {"ingested": 3, "uploaded": 2, "processing": 1, "error": 0}
GENERIC_CUSTOMER_NAMES = {"", "abc", "abc trading co", "example: abc trading co"}


def _safe_filename(filename: str) -> str:
    raw_filename = (filename or "uploaded_file").replace("\\", "/")
    parts = [part for part in raw_filename.split("/") if part not in {"", ".", ".."}]
    flat_filename = "__".join(parts) or "uploaded_file"
    return "".join("_" if char in '<>:"|?*' else char for char in flat_filename)


def _synthetic_customer_id(filename: str) -> int | None:
    match = re.search(r"\bCUST-(\d{3,})\b", filename or "", flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


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


def _ensure_upload_customer(db: Session, requested_customer_id: str, filename: str) -> models.Customer:
    synthetic_id = _synthetic_customer_id(filename)
    if synthetic_id is not None:
        customer = db.query(models.Customer).filter(models.Customer.id == synthetic_id).first()
        if not customer:
            customer = models.Customer(
                id=synthetic_id,
                name=f"CUST-{synthetic_id:03d}",
                customer_type="business",
                industry="Credit appraisal",
                country=None,
            )
            db.add(customer)
            db.commit()
            _sync_customer_sequence(db)
            db.commit()
            db.refresh(customer)
        return customer
    return ensure_customer(db, requested_customer_id)


def _candidate_customer_name(text_value: str) -> str | None:
    compact = " ".join((text_value or "").split())
    patterns = [
        r"(?:Taxpayer\s*/\s*Entity|Borrower|Customer|Entity|Applicant)\s+(.+?)(?:\s+Tax Year|\s+Industry|\s+Business Type|\s+Country|\s+Loan|\s+Revenue|\s+Field Value|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, compact, flags=re.IGNORECASE)
        if not match:
            continue
        name = match.group(1).strip(" :-|")
        if 2 <= len(name) <= 80 and not re.search(r"\b(CUST-\d+|Field|Value)\b", name, flags=re.IGNORECASE):
            return name
    return None


def _maybe_update_customer_name_from_chunks(db: Session, customer_id: int, chunks: list[dict[str, Any]]) -> None:
    customer = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    if not customer:
        return
    current_name = (customer.name or "").strip()
    should_update = (
        current_name.casefold() in GENERIC_CUSTOMER_NAMES
        or current_name.casefold().startswith("cust-")
        or current_name.casefold().startswith("recovered customer")
    )
    if not should_update:
        return
    for chunk in chunks:
        candidate = _candidate_customer_name(chunk.get("text") or "")
        if candidate:
            customer.name = candidate
            db.add(customer)
            return


def _dedupe_rank(document: models.Document) -> tuple[int, int]:
    return (DOCUMENT_STATUS_RANK.get((document.status or "").lower(), 1), document.id)


@router.get("/documents", response_model=list[schemas.DocumentOut])
def list_documents(customer_id: int | None = None, db: Session = Depends(get_db)) -> list[schemas.DocumentOut]:
    query = db.query(models.Document)
    if customer_id is not None:
        query = query.filter(models.Document.customer_id == customer_id)
    return query.order_by(
        func.lower(models.Document.filename).asc(),
        func.lower(models.Document.document_type).asc(),
        models.Document.id.asc(),
    ).all()


@router.post("/documents/deduplicate")
def deduplicate_documents(customer_id: int | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    query = db.query(models.Document)
    if customer_id is not None:
        query = query.filter(models.Document.customer_id == customer_id)

    groups: dict[tuple[int, str, str], list[models.Document]] = defaultdict(list)
    for document in query.order_by(models.Document.id.asc()).all():
        key = (
            document.customer_id,
            (document.filename or "").casefold(),
            (document.document_type or "").casefold(),
        )
        groups[key].append(document)

    removed_document_ids: list[int] = []
    kept_document_ids: list[int] = []
    duplicate_groups = 0

    for documents in groups.values():
        if len(documents) < 2:
            continue
        duplicate_groups += 1
        keep = max(documents, key=_dedupe_rank)
        kept_document_ids.append(keep.id)
        removed_document_ids.extend(document.id for document in documents if document.id != keep.id)

    chunks_removed = 0
    if removed_document_ids:
        chunks_removed = (
            db.query(models.DocumentChunk)
            .filter(models.DocumentChunk.document_id.in_(removed_document_ids))
            .delete(synchronize_session=False)
        )
        db.query(models.Document).filter(models.Document.id.in_(removed_document_ids)).delete(synchronize_session=False)
        log_event(
            db,
            "documents_deduplicated",
            customer_id,
            {
                "duplicate_groups": duplicate_groups,
                "duplicates_removed": len(removed_document_ids),
                "chunks_removed": chunks_removed,
                "kept_document_ids": kept_document_ids,
                "removed_document_ids": removed_document_ids,
            },
        )
    else:
        db.commit()

    cache_summary = document_memory_cache.warm_from_db(db)
    return {
        "duplicate_groups": duplicate_groups,
        "duplicates_removed": len(removed_document_ids),
        "chunks_removed": chunks_removed,
        "kept_document_ids": kept_document_ids,
        "removed_document_ids": removed_document_ids,
        "cache": cache_summary,
    }


@router.post("/documents/recover-from-disk")
def recover_documents_from_disk(db: Session = Depends(get_db)) -> dict[str, Any]:
    return recover_uploaded_files_from_disk(db)


def ingest_document_record(db: Session, document: models.Document) -> int:
    sections = parse_document(document.file_path)
    chunks = chunk_sections(sections)
    if not chunks:
        raise ValueError("No text content could be extracted")

    _maybe_update_customer_name_from_chunks(db, document.customer_id, chunks)

    db.query(models.DocumentChunk).filter(models.DocumentChunk.document_id == document.id).delete()
    for index, chunk in enumerate(chunks):
        embedding = create_embedding(chunk["text"])
        db.add(
            models.DocumentChunk(
                customer_id=document.customer_id,
                document_id=document.id,
                page_number=chunk["page_number"],
                chunk_index=index,
                chunk_text=chunk["text"],
                chunk_metadata={
                    "filename": document.filename,
                    "document_type": document.document_type,
                    "source_type": document.source_type,
                    "source_uri": document.source_uri,
                    "external_document_id": document.external_document_id,
                },
                embedding=embedding,
            )
        )

    document.status = "ingested"
    return len(chunks)


def _ingestion_status(document: models.Document, chunks_count: int = 0) -> schemas.IngestionStatus:
    if document.status == "ingested":
        return schemas.IngestionStatus(parser="done", chunker="done", embeddings="done", postgresql="done", pgvector="done")
    if document.status == "error":
        return schemas.IngestionStatus(parser="failed", chunker="failed", embeddings="failed", postgresql="failed", pgvector="failed")
    if chunks_count:
        return schemas.IngestionStatus(parser="done", chunker="done", embeddings="done", postgresql="done", pgvector="done")
    return schemas.IngestionStatus(parser="pending", chunker="pending", embeddings="pending", postgresql="pending", pgvector="pending")


def _upload_response(document: models.Document, session_id: str | None = None, chunks_count: int = 0) -> schemas.DocumentUploadResponse:
    payload = schemas.DocumentOut.model_validate(document).model_dump()
    return schemas.DocumentUploadResponse(
        **payload,
        document_id=external_document_id(document.id),
        session_id=session_id,
        ingestion_status=_ingestion_status(document, chunks_count),
    )


@router.post("/documents/upload", response_model=schemas.DocumentUploadResponse)
def upload_document(
    customer_id: str = Form(...),
    session_id: str | None = Form(None),
    source: str = Form("manual_upload"),
    document_type: str = Form("credit_document"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> schemas.DocumentUploadResponse:
    filename = _safe_filename(file.filename or "uploaded_file")
    try:
        customer = _ensure_upload_customer(db, customer_id, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    settings = get_settings()
    customer_dir = Path(settings.upload_dir) / str(customer.id)
    customer_dir.mkdir(parents=True, exist_ok=True)
    file_path = customer_dir / filename

    with file_path.open("wb") as output:
        shutil.copyfileobj(file.file, output)

    existing_document = (
        db.query(models.Document)
        .filter(
            models.Document.customer_id == customer.id,
            models.Document.filename == filename,
            models.Document.document_type == document_type,
        )
        .order_by(models.Document.id.desc())
        .first()
    )
    if existing_document:
        db.query(models.DocumentChunk).filter(models.DocumentChunk.document_id == existing_document.id).delete()
        existing_document.file_path = str(file_path)
        existing_document.status = "uploaded"
        existing_document.source_type = source or "manual_upload"
        existing_document.source_uri = None
        existing_document.external_document_id = None
        existing_document.source_metadata = {"session_id": session_id} if session_id else {}
        db.commit()
        db.refresh(existing_document)
        log_event(db, "document_reuploaded", customer.id, {"document_id": existing_document.id, "filename": filename, "source": source})
        document_memory_cache.upsert_document(db, existing_document.id)
        return _upload_response(existing_document, session_id=session_id)

    document = models.Document(
        customer_id=customer.id,
        filename=filename,
        file_path=str(file_path),
        document_type=document_type,
        status="uploaded",
        source_type=source or "manual_upload",
        source_metadata={"session_id": session_id} if session_id else {},
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    log_event(db, "document_uploaded", customer.id, {"document_id": document.id, "filename": filename, "source": source})
    document_memory_cache.upsert_document(db, document.id)
    return _upload_response(document, session_id=session_id)


@router.get("/documents/{document_id}/status", response_model=schemas.DocumentStatusResponse)
def document_status(document_id: str, db: Session = Depends(get_db)) -> schemas.DocumentStatusResponse:
    internal_id = parse_external_document_id(document_id)
    if internal_id is None:
        raise HTTPException(status_code=400, detail="Invalid document_id")
    document = crud.get_document(db, internal_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    chunks_count = db.query(models.DocumentChunk).filter(models.DocumentChunk.document_id == document.id).count()
    status = _ingestion_status(document, chunks_count)
    return schemas.DocumentStatusResponse(
        document_id=external_document_id(document.id),
        customer_id=str(document.customer_id),
        parser=status.parser,
        chunker=status.chunker,
        embeddings=status.embeddings,
        postgresql=status.postgresql,
        pgvector=status.pgvector,
        chunks_count=chunks_count,
        indexed_at=document.uploaded_at if document.status == "ingested" else None,
        error="Document ingestion failed" if document.status == "error" else None,
    )


@router.post("/ingest/{document_id}", response_model=schemas.IngestResponse)
def ingest_document(document_id: int, db: Session = Depends(get_db)) -> schemas.IngestResponse:
    document = crud.get_document(db, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        chunks_created = ingest_document_record(db, document)
        db.commit()
        document_memory_cache.upsert_document(db, document.id)
        log_event(db, "document_ingested", document.customer_id, {"document_id": document.id, "chunks": chunks_created})
        return schemas.IngestResponse(document_id=document.id, status=document.status, chunks_created=chunks_created)
    except Exception as exc:
        db.rollback()
        document = crud.get_document(db, document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found") from exc
        document.status = "error"
        db.commit()
        document_memory_cache.upsert_document(db, document.id)
        log_event(db, "document_ingested", document.customer_id, {"document_id": document.id, "error": str(exc)})
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc
