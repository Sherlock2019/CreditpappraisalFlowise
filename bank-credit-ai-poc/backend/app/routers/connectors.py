from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.audit import log_event, redact_sensitive_config
from app.config import get_settings
from app.connectors.factory import get_connector, get_connector_options, normalize_source_type
from app.database import get_db
from app.routers.documents import _safe_filename, ingest_document_record

router = APIRouter(prefix="/connectors", tags=["connectors"])


@router.get("/options", response_model=schemas.ConnectorOptionsResponse)
def connector_options() -> schemas.ConnectorOptionsResponse:
    return schemas.ConnectorOptionsResponse(connectors=get_connector_options())


@router.post("/test", response_model=schemas.ConnectorTestResponse)
def test_connector(payload: schemas.ConnectorTestRequest, db: Session = Depends(get_db)) -> schemas.ConnectorTestResponse:
    source_type = normalize_source_type(payload.source_type)
    connector = get_connector(source_type)
    result = connector.test_connection(payload.config)
    log_event(
        db,
        "connector_test",
        details={
            "source_type": source_type,
            "success": bool(result.get("success")),
            "config": redact_sensitive_config(payload.config),
        },
    )
    return schemas.ConnectorTestResponse(
        source_type=source_type,
        success=bool(result.get("success")),
        message=str(result.get("message", "")),
        details=result.get("details", {}),
    )


@router.post("/list-documents", response_model=schemas.ConnectorListDocumentsResponse)
def list_connector_documents(
    payload: schemas.ConnectorListDocumentsRequest,
    db: Session = Depends(get_db),
) -> schemas.ConnectorListDocumentsResponse:
    source_type = normalize_source_type(payload.source_type)
    connector = get_connector(source_type)
    config = dict(payload.config or {})
    if payload.prefix and "prefix" not in config:
        config["prefix"] = payload.prefix
    if payload.folder_path and "folder_path" not in config:
        config["folder_path"] = payload.folder_path

    try:
        documents = connector.list_documents(config)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    log_event(
        db,
        "connector_list_documents",
        payload.customer_id,
        {
            "source_type": source_type,
            "document_count": len(documents),
            "config": redact_sensitive_config(config),
        },
    )
    return schemas.ConnectorListDocumentsResponse(
        source_type=source_type,
        documents=documents,
        message=f"Found {len(documents)} document(s).",
    )


@router.post("/ingest", response_model=schemas.ConnectorIngestResponse)
def ingest_connector_document(
    payload: schemas.ConnectorIngestRequest,
    db: Session = Depends(get_db),
) -> schemas.ConnectorIngestResponse:
    source_type = normalize_source_type(payload.source_type)
    if source_type == "manual_upload":
        return schemas.ConnectorIngestResponse(
            source_type=source_type,
            customer_id=payload.customer_id,
            status="not_applicable",
            message="Use /documents/upload for manual upload.",
        )

    customer = crud.get_customer(db, payload.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    connector = get_connector(source_type)
    try:
        file_bytes, metadata = connector.download_document(
            external_document_id=payload.external_document_id,
            source_uri=payload.source_uri,
            config=payload.config,
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    filename = _safe_filename(payload.filename or metadata.get("filename") or "external_document")
    settings = get_settings()
    customer_dir = Path(settings.upload_dir) / str(payload.customer_id)
    customer_dir.mkdir(parents=True, exist_ok=True)
    file_path = customer_dir / filename
    file_path.write_bytes(file_bytes)

    document = models.Document(
        customer_id=payload.customer_id,
        filename=filename,
        file_path=str(file_path),
        document_type=metadata.get("document_type") or "external_import",
        status="uploaded",
        source_type=source_type,
        source_uri=metadata.get("source_uri") or payload.source_uri,
        external_document_id=metadata.get("external_document_id") or payload.external_document_id,
        source_metadata=metadata,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    status = "uploaded"
    message = "Document imported. Ingestion was not run."
    try:
        chunks_created = ingest_document_record(db, document)
        db.commit()
        status = "ingested"
        message = f"Document imported and ingested with {chunks_created} chunk(s)."
    except Exception as exc:
        db.rollback()
        document = crud.get_document(db, document.id)
        if document:
            document.status = "uploaded"
            db.commit()
        message = f"Document imported but ingestion failed: {exc}"

    log_event(
        db,
        "connector_document_ingested",
        payload.customer_id,
        {
            "source_type": source_type,
            "document_id": document.id,
            "source_uri": document.source_uri,
            "external_document_id": document.external_document_id,
            "config": redact_sensitive_config(payload.config),
        },
    )
    return schemas.ConnectorIngestResponse(
        source_type=source_type,
        customer_id=payload.customer_id,
        document_id=document.id,
        filename=filename,
        status=status,
        message=message,
    )
