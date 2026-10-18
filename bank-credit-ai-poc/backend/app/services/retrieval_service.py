from __future__ import annotations

from sqlalchemy.orm import Session

from app.rag import build_context, citations_from_chunks, retrieve_relevant_chunks


def _plain_json(value):
    if isinstance(value, dict):
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain_json(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return value


REQUIRED_DOCUMENT_MARKERS = {
    "financial statements": ["financial", "statement"],
    "tax returns": ["tax"],
    "bank statements": ["bank"],
    "collateral valuation": ["collateral", "valuation"],
}


def missing_documents_from_context(context: dict) -> list[str]:
    text = f"{context.get('context', '')} {context.get('question', '')}".lower()
    return [label for label, markers in REQUIRED_DOCUMENT_MARKERS.items() if not any(marker in text for marker in markers)]


def retrieve_customer_context(db: Session, customer_id: int, question: str, top_k: int = 8) -> dict:
    chunks = retrieve_relevant_chunks(db, customer_id, question, top_k=top_k)
    return {
        "customer_id": customer_id,
        "question": question,
        "top_k": top_k,
        "retrieval_mode": "pgvector_or_text_fallback",
        "context": build_context(chunks),
        "citations": _plain_json(citations_from_chunks(chunks)),
        "retrieved_chunks": _plain_json(chunks),
    }
