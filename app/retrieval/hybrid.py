"""
Reciprocal Rank Fusion: combines the dense (semantic) and sparse (BM25
keyword) rankings by rank position rather than raw score, since cosine
similarity and BM25 scores live on different scales and aren't directly
comparable. A chunk that ranks well in either list gets a boost; one that
ranks well in both rises to the top.

The BM25 index is rebuilt lazily on first use and cached at module level,
same pattern as the embedding model cache in embeddings.py - avoids
rebuilding it from Qdrant on every single search call.
"""

from app.retrieval.sparse import BM25Index, bm25_search, build_bm25_index
from app.retrieval.vector_store import RetrievedChunk, dense_search

RRF_K = 60  # standard RRF damping constant from the original paper

_bm25_index: BM25Index | None = None


def _get_bm25_index() -> BM25Index:
    global _bm25_index
    if _bm25_index is None:
        _bm25_index = build_bm25_index()
    return _bm25_index


def hybrid_search(query: str, top_k: int = 5) -> list[RetrievedChunk]:
    dense_results = dense_search(query, top_k=top_k * 2)
    sparse_results = bm25_search(_get_bm25_index(), query, top_k=top_k * 2)

    rrf_scores: dict[tuple[str, int], float] = {}
    chunks_by_key: dict[tuple[str, int], RetrievedChunk] = {}
    for results in (dense_results, sparse_results):
        for rank, chunk in enumerate(results):
            key = (chunk.source, chunk.chunk_index)
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (RRF_K + rank + 1)
            chunks_by_key[key] = chunk

    ranked_keys = sorted(rrf_scores, key=lambda k: rrf_scores[k], reverse=True)[:top_k]
    return [
        RetrievedChunk(
            text=chunks_by_key[key].text,
            source=key[0],
            chunk_index=key[1],
            score=rrf_scores[key],
        )
        for key in ranked_keys
    ]
