from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.flowise_compat import ensure_customer, external_document_id
from app.services.retrieval_service import retrieve_customer_context

router = APIRouter(tags=["retrieval"])


class RetrievalQueryRequest(BaseModel):
    customer_id: str
    session_id: str | None = None
    question: str
    top_k: int = Field(default=8, ge=1, le=20)
    filters: dict[str, Any] = Field(default_factory=dict)


def _missing_documents_from_context(context: dict[str, Any]) -> list[str]:
    text = f"{context.get('context', '')} {context.get('question', '')}".lower()
    required = {
        "financial statements": ["financial", "statement"],
        "tax returns": ["tax"],
        "bank statements": ["bank"],
        "collateral valuation": ["collateral", "valuation"],
    }
    missing: list[str] = []
    for label, markers in required.items():
        if not any(marker in text for marker in markers):
            missing.append(label)
    return missing


@router.post("/retrieval/query")
def retrieval_query(payload: RetrievalQueryRequest, db: Session = Depends(get_db)) -> dict:
    try:
        customer = ensure_customer(db, payload.customer_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not crud.get_customer(db, customer.id):
        raise HTTPException(status_code=404, detail="Customer not found")
    context = retrieve_customer_context(db, customer.id, payload.question, payload.top_k)
    evidence = []
    for chunk in context.get("retrieved_chunks", []):
        evidence.append(
            {
                "chunk_id": f"chunk_{chunk.get('document_id', '')}_{chunk.get('chunk_index', '')}",
                "document_id": external_document_id(chunk.get("document_id", "")),
                "document_name": chunk.get("filename") or "Unknown document",
                "page": chunk.get("page_number"),
                "text": chunk.get("chunk_text") or "",
                "score": float(chunk.get("score") or 0),
                "source_type": chunk.get("source_type") or "customer_document",
            }
        )
    return {
        **context,
        "customer_id": str(payload.customer_id),
        "internal_customer_id": customer.id,
        "session_id": payload.session_id,
        "filters": payload.filters,
        "evidence": evidence,
        "missing_documents": _missing_documents_from_context(context),
    }
