from collections import defaultdict
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.audit import log_event
from app.config import get_settings
from app.database import get_db
from app.document_cache import document_memory_cache
from app.document_recovery import recover_uploaded_files_from_disk
from app.document_parser import chunk_sections, parse_document
from app.embeddings import create_embedding

router = APIRouter(tags=["documents"])

SUPPORTED_SUFFIXES = {".pdf", ".txt", ".csv", ".xlsx", ".xls", ".docx"}
DOCUMENT_STATUS_RANK = {"ingested": 3, "uploaded": 2, "processing": 1, "error": 0}


def _safe_filename(filename: str) -> str:
    raw_filename = (filename or "uploaded_file").replace("\\", "/")
    parts = [part for part in raw_filename.split("/") if part not in {"", ".", ".."}]
    flat_filename = "__".join(parts) or "uploaded_file"
    return "".join("_" if char in '<>:"|?*' else char for char in flat_filename)


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


@router.post("/documents/upload", response_model=schemas.DocumentOut)
def upload_document(
    customer_id: int = Form(...),
    document_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> schemas.DocumentOut:
    customer = crud.get_customer(db, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    filename = _safe_filename(file.filename or "uploaded_file")
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    settings = get_settings()
    customer_dir = Path(settings.upload_dir) / str(customer_id)
    customer_dir.mkdir(parents=True, exist_ok=True)
    file_path = customer_dir / filename

    with file_path.open("wb") as output:
        shutil.copyfileobj(file.file, output)

    existing_document = (
        db.query(models.Document)
        .filter(
            models.Document.customer_id == customer_id,
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
        existing_document.source_type = "manual_upload"
        existing_document.source_uri = None
        existing_document.external_document_id = None
        existing_document.source_metadata = {}
        db.commit()
        db.refresh(existing_document)
        log_event(db, "document_reuploaded", customer_id, {"document_id": existing_document.id, "filename": filename})
        document_memory_cache.upsert_document(db, existing_document.id)
        return existing_document

    document = models.Document(
        customer_id=customer_id,
        filename=filename,
        file_path=str(file_path),
        document_type=document_type,
        status="uploaded",
        source_type="manual_upload",
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    log_event(db, "document_uploaded", customer_id, {"document_id": document.id, "filename": filename})
    document_memory_cache.upsert_document(db, document.id)
    return document


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
