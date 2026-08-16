"""
Phase 1: builds the searchable index from the sample documents - loads,
chunks, embeds, and stores them in Qdrant. Run this once (or whenever
documents change) before querying with hybrid_search().

Run with: PYTHONPATH=. python3 scripts/build_index.py
"""

from app.ingestion.chunker import chunk_text
from app.ingestion.loaders import load_document
from app.retrieval.vector_store import add_chunks

for path in [
    "data/sample.txt",
    "data/sample.pdf",
    "data/sample_large.txt",
    "data/sample_large.pdf",
    "data/sample_expenses.csv",
]:
    text = load_document(path)
    chunks = chunk_text(text, source=path)
    add_chunks(chunks)
    print(f"Indexed {path}: {len(text.split())} words -> {len(chunks)} chunks")
