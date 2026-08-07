"""
Persists chunk embeddings in Qdrant running in local embedded mode
(QdrantClient(path=...)) - an on-disk vector index with no separate server
process to run, which keeps local dev and eventual Docker deployment
simple. Qdrant is treated as the single source of truth for the chunk
corpus - sparse.py rebuilds its BM25 index from get_all_chunks() instead
of keeping a second copy of the documents.
"""

import uuid
from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.ingestion.chunker import Chunk
from app.retrieval.embeddings import embed_query, embed_texts

PERSIST_DIR = "data/qdrant"
COLLECTION_NAME = "verifiedrag"
VECTOR_SIZE = 384  # output dimension of BAAI/bge-small-en-v1.5, see embeddings.py

_client: QdrantClient | None = None


@dataclass
class RetrievedChunk:
    text: str
    source: str
    chunk_index: int
    score: float


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(path=PERSIST_DIR)
        if not _client.collection_exists(COLLECTION_NAME):
            _client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )
    return _client


def _point_id(source: str, chunk_index: int) -> str:
    # Qdrant point IDs must be an int or UUID, not an arbitrary string - derive a
    # stable UUID from source+chunk_index so re-indexing the same chunk upserts
    # it in place instead of creating a duplicate point.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source}::{chunk_index}"))


def add_chunks(chunks: list[Chunk]) -> None:
    """Embed chunks and upsert them into the persistent vector store."""
    if not chunks:
        return
    client = _get_client()
    vectors = embed_texts([c.text for c in chunks])
    points = [
        PointStruct(
            id=_point_id(c.source, c.chunk_index),
            vector=vector,
            payload={"text": c.text, "source": c.source, "chunk_index": c.chunk_index},
        )
        for c, vector in zip(chunks, vectors)
    ]
    client.upsert(collection_name=COLLECTION_NAME, points=points)


def dense_search(query: str, top_k: int = 5) -> list[RetrievedChunk]:
    """Semantic search: embed the query and return the closest stored chunks."""
    client = _get_client()
    results = client.query_points(
        collection_name=COLLECTION_NAME, query=embed_query(query), limit=top_k
    ).points
    return [
        RetrievedChunk(
            text=r.payload["text"],
            source=r.payload["source"],
            chunk_index=r.payload["chunk_index"],
            score=r.score,  # cosine similarity - higher is better, already comparable
        )
        for r in results
    ]


def get_all_chunks() -> list[dict]:
    """Every chunk currently stored, for sparse.py to build a BM25 index from."""
    client = _get_client()
    points, _ = client.scroll(
        collection_name=COLLECTION_NAME, limit=100_000, with_payload=True, with_vectors=False
    )
    return [
        {"text": p.payload["text"], "source": p.payload["source"], "chunk_index": p.payload["chunk_index"]}
        for p in points
    ]
