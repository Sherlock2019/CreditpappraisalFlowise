from __future__ import annotations

from app.document_cache import CachedChunk, DocumentMemoryCache


def test_cached_search_returns_document_id_so_chunk_ids_are_unique():
    cache = DocumentMemoryCache()
    cache._chunks_by_customer[7] = [
        CachedChunk(id=1, document_id=10, customer_id=7, chunk_text="income", chunk_index=0, page_number=1, metadata={"filename": "a.pdf"}, embedding=[1.0, 0.0]),
        CachedChunk(id=2, document_id=11, customer_id=7, chunk_text="collateral", chunk_index=0, page_number=1, metadata={"filename": "b.pdf"}, embedding=[0.9, 0.1]),
    ]
    results = cache.search_customer_chunks(7, [1.0, 0.0], top_k=5)
    chunk_ids = {f"chunk_{r['document_id']}_{r['chunk_index']}" for r in results}
    assert chunk_ids == {"chunk_10_0", "chunk_11_0"}
