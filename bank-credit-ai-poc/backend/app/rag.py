from typing import Any
import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.document_cache import document_memory_cache
from app.embeddings import create_embedding


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def _synthetic_customer_code(value: str | None) -> str | None:
    match = re.search(r"\bCUST-(\d{3,})\b", value or "", flags=re.IGNORECASE)
    return match.group(0).upper() if match else None


def _filter_synthetic_customer_docs(chunks: list[dict[str, Any]], customer_id: int) -> list[dict[str, Any]]:
    """Keep demo CUST-### folders scoped to the selected numeric customer id."""
    target_code = f"CUST-{customer_id:03d}"
    codes = {
        code
        for chunk in chunks
        for code in (
            _synthetic_customer_code(chunk.get("filename")),
            _synthetic_customer_code(chunk.get("chunk_text")),
        )
        if code
    }
    if not codes:
        return chunks
    return [
        chunk
        for chunk in chunks
        if _synthetic_customer_code(chunk.get("filename")) in {None, target_code}
        and _synthetic_customer_code(chunk.get("chunk_text")) in {None, target_code}
    ]


def retrieve_relevant_chunks(db: Session, customer_id: int, question: str, top_k: int = 8) -> list[dict[str, Any]]:
    embedding = create_embedding(question)
    cached_chunks = document_memory_cache.search_customer_chunks(customer_id, embedding, top_k)
    if cached_chunks:
        return _filter_synthetic_customer_docs(cached_chunks, customer_id)

    vector = _vector_literal(embedding)
    query = text(
        """
        SELECT
          c.chunk_text,
          COALESCE(c.metadata->>'filename', d.filename) AS filename,
          COALESCE(c.metadata->>'document_type', d.document_type) AS document_type,
          c.page_number,
          c.chunk_index,
          1 - (c.embedding <=> CAST(:embedding AS vector)) AS score
        FROM document_chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.customer_id = :customer_id
          AND c.embedding IS NOT NULL
        ORDER BY c.embedding <=> CAST(:embedding AS vector)
        LIMIT :top_k
        """
    )
    rows = db.execute(query, {"embedding": vector, "customer_id": customer_id, "top_k": top_k}).mappings().all()
    return _filter_synthetic_customer_docs([dict(row) for row in rows], customer_id)


def retrieve_relevant_chunks_all_customers(db: Session, question: str, top_k: int = 12) -> list[dict[str, Any]]:
    embedding = create_embedding(question)
    vector = _vector_literal(embedding)
    query = text(
        """
        SELECT
          c.customer_id,
          c.chunk_text,
          COALESCE(c.metadata->>'filename', d.filename) AS filename,
          COALESCE(c.metadata->>'document_type', d.document_type) AS document_type,
          c.page_number,
          c.chunk_index,
          1 - (c.embedding <=> CAST(:embedding AS vector)) AS score
        FROM document_chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.embedding IS NOT NULL
        ORDER BY c.embedding <=> CAST(:embedding AS vector)
        LIMIT :top_k
        """
    )
    rows = db.execute(query, {"embedding": vector, "top_k": top_k}).mappings().all()
    return [dict(row) for row in rows]


def build_context(chunks: list[dict[str, Any]]) -> str:
    parts = []
    for index, chunk in enumerate(chunks, start=1):
        page = chunk.get("page_number") or "n/a"
        citation = f"[{index}] {chunk['filename']} page {page}"
        parts.append(f"{citation}\n{chunk['chunk_text']}")
    return "\n\n".join(parts)


def citations_from_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "filename": chunk["filename"],
            "document_type": chunk["document_type"],
            "page_number": chunk.get("page_number"),
            "chunk_index": chunk.get("chunk_index"),
            "score": float(chunk.get("score") or 0),
        }
        for chunk in chunks
    ]
