"""
BM25 keyword search over the chunk corpus. Unlike the vector store, BM25
has no persistent index of its own - it's rebuilt in memory from whatever
chunks are already stored in Qdrant, which stays the single source of
truth for the corpus. Rebuilding is cheap enough at this project's scale
and avoids keeping two copies of the documents in sync.
"""

from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from app.retrieval.vector_store import RetrievedChunk, get_all_chunks


@dataclass
class BM25Index:
    bm25: BM25Okapi
    chunks: list[dict]


def build_bm25_index() -> BM25Index:
    chunks = get_all_chunks()
    tokenized = [c["text"].lower().split() for c in chunks]
    return BM25Index(bm25=BM25Okapi(tokenized), chunks=chunks)


def bm25_search(index: BM25Index, query: str, top_k: int = 5) -> list[RetrievedChunk]:
    scores = index.bm25.get_scores(query.lower().split())
    ranked = sorted(zip(scores, index.chunks), key=lambda x: x[0], reverse=True)[:top_k]
    return [
        RetrievedChunk(text=c["text"], source=c["source"], chunk_index=c["chunk_index"], score=score)
        for score, c in ranked
    ]
