"""
Run with: PYTHONPATH=. python3 scripts/test_ingestion.py
Loads both sample files, chunks them, and prints a preview so you can see
the pipeline actually works before we wire it into retrieval.
"""

from app.ingestion.loaders import load_document
from app.ingestion.chunker import chunk_text

for path in ["data/sample.txt", "data/sample.pdf"]:
    text = load_document(path)
    chunks = chunk_text(text, source=path, chunk_size=40, overlap=10)  # small chunk_size just so the demo produces >1 chunk
    print(f"\n=== {path} ===")
    print(f"{len(text.split())} words loaded -> {len(chunks)} chunks")
    for c in chunks:
        print(f"  [{c.chunk_index}] {c.text[:90]}...")
