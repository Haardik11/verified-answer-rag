"""
Fixed-size word-window chunking with overlap. This is the simplest chunking
strategy that works - good enough to get retrieval working. Once the RAG
loop is proven end to end, this is a good place to come back and compare
against semantic chunking (splitting on meaning boundaries instead of a
fixed word count) since that's a legitimate thing to benchmark and mention
in a resume bullet later.
"""

from dataclasses import dataclass


@dataclass
class Chunk:
    text: str
    source: str
    chunk_index: int


def chunk_text(text: str, source: str, chunk_size: int = 250, overlap: int = 50) -> list[Chunk]:
    words = text.split()
    chunks = []
    start = 0
    idx = 0
    while start < len(words):
        end = start + chunk_size
        piece = " ".join(words[start:end])
        if piece.strip():
            chunks.append(Chunk(text=piece, source=source, chunk_index=idx))
            idx += 1
        start += chunk_size - overlap
    return chunks
