from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any

from sqlalchemy.orm import Session

from app import models


@dataclass(slots=True)
class CachedChunk:
    id: int
    document_id: int
    customer_id: int
    chunk_text: str
    chunk_index: int
    page_number: int | None
    metadata: dict[str, Any]
    embedding: list[float] | None


@dataclass(slots=True)
class CachedDocument:
    id: int
    customer_id: int
    filename: str
    file_path: str
    document_type: str | None
    status: str | None
    source_type: str | None
    source_uri: str | None
    external_document_id: str | None
    source_metadata: dict[str, Any]
    file_bytes: bytes = b""
    chunks: list[CachedChunk] = field(default_factory=list)

    @property
    def file_size(self) -> int:
        return len(self.file_bytes)


class DocumentMemoryCache:
    def __init__(self) -> None:
        self._lock = RLock()
        self._documents_by_id: dict[int, CachedDocument] = {}
        self._document_ids_by_customer: dict[int, set[int]] = {}
        self._chunks_by_customer: dict[int, list[CachedChunk]] = {}

    def warm_from_db(self, db: Session) -> dict[str, int]:
        documents = db.query(models.Document).order_by(models.Document.id.asc()).all()
        next_documents: dict[int, CachedDocument] = {}
        next_document_ids_by_customer: dict[int, set[int]] = {}
        next_chunks_by_customer: dict[int, list[CachedChunk]] = {}

        for document in documents:
            cached_document = self._build_document(db, document)
            next_documents[cached_document.id] = cached_document
            next_document_ids_by_customer.setdefault(cached_document.customer_id, set()).add(cached_document.id)
            if cached_document.chunks:
                next_chunks_by_customer.setdefault(cached_document.customer_id, []).extend(cached_document.chunks)

        with self._lock:
            self._documents_by_id = next_documents
            self._document_ids_by_customer = next_document_ids_by_customer
            self._chunks_by_customer = next_chunks_by_customer

        return self.summary()

    def upsert_document(self, db: Session, document_id: int) -> dict[str, int]:
        document = db.query(models.Document).filter(models.Document.id == document_id).first()
        with self._lock:
            self._remove_locked(document_id)
            if document:
                cached_document = self._build_document(db, document)
                self._documents_by_id[cached_document.id] = cached_document
                self._document_ids_by_customer.setdefault(cached_document.customer_id, set()).add(cached_document.id)
                if cached_document.chunks:
                    self._chunks_by_customer.setdefault(cached_document.customer_id, []).extend(cached_document.chunks)
        return self.summary()

    def summary(self) -> dict[str, int]:
        with self._lock:
            documents = list(self._documents_by_id.values())
            return {
                "customers": len(self._document_ids_by_customer),
                "documents": len(documents),
                "chunks": sum(len(document.chunks) for document in documents),
                "file_bytes": sum(document.file_size for document in documents),
            }

    def documents_for_customer(self, customer_id: int) -> list[CachedDocument]:
        with self._lock:
            document_ids = sorted(self._document_ids_by_customer.get(customer_id, set()))
            return [self._documents_by_id[document_id] for document_id in document_ids if document_id in self._documents_by_id]

    def search_customer_chunks(self, customer_id: int, query_embedding: list[float], top_k: int) -> list[dict[str, Any]]:
        with self._lock:
            chunks = list(self._chunks_by_customer.get(customer_id, []))

        scored: list[tuple[float, CachedChunk]] = []
        for chunk in chunks:
            if not chunk.embedding:
                continue
            scored.append((self._cosine_similarity(query_embedding, chunk.embedding), chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {
                "chunk_text": chunk.chunk_text,
                "filename": chunk.metadata.get("filename", "document"),
                "document_type": chunk.metadata.get("document_type"),
                "page_number": chunk.page_number,
                "chunk_index": chunk.chunk_index,
                "score": score,
            }
            for score, chunk in scored[:top_k]
        ]

    def _remove_locked(self, document_id: int) -> None:
        old = self._documents_by_id.pop(document_id, None)
        if not old:
            return
        customer_docs = self._document_ids_by_customer.get(old.customer_id)
        if customer_docs:
            customer_docs.discard(document_id)
            if not customer_docs:
                self._document_ids_by_customer.pop(old.customer_id, None)
        if old.customer_id in self._chunks_by_customer:
            self._chunks_by_customer[old.customer_id] = [
                chunk for chunk in self._chunks_by_customer[old.customer_id] if chunk.document_id != document_id
            ]
            if not self._chunks_by_customer[old.customer_id]:
                self._chunks_by_customer.pop(old.customer_id, None)

    def _build_document(self, db: Session, document: models.Document) -> CachedDocument:
        chunks = (
            db.query(models.DocumentChunk)
            .filter(models.DocumentChunk.document_id == document.id)
            .order_by(models.DocumentChunk.chunk_index.asc())
            .all()
        )
        return CachedDocument(
            id=document.id,
            customer_id=document.customer_id,
            filename=document.filename,
            file_path=document.file_path,
            document_type=document.document_type,
            status=document.status,
            source_type=document.source_type,
            source_uri=document.source_uri,
            external_document_id=document.external_document_id,
            source_metadata=dict(document.source_metadata or {}),
            file_bytes=self._read_file_bytes(document.file_path),
            chunks=[
                CachedChunk(
                    id=chunk.id,
                    document_id=chunk.document_id,
                    customer_id=chunk.customer_id,
                    chunk_text=chunk.chunk_text,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    metadata=dict(chunk.chunk_metadata or {}),
                    embedding=list(chunk.embedding) if chunk.embedding is not None else None,
                )
                for chunk in chunks
            ],
        )

    @staticmethod
    def _read_file_bytes(file_path: str) -> bytes:
        try:
            return Path(file_path).read_bytes()
        except OSError:
            return b""

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        dot = 0.0
        left_norm = 0.0
        right_norm = 0.0
        for left_value, right_value in zip(left, right):
            dot += left_value * right_value
            left_norm += left_value * left_value
            right_norm += right_value * right_value
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot / ((left_norm**0.5) * (right_norm**0.5))


document_memory_cache = DocumentMemoryCache()
