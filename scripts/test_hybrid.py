"""
Sanity-checks hybrid search against the index built by build_index.py.
Each query below is written to match content specific to one of the two
sample documents, so a working index should mostly surface the right
source for each.

Run build_index.py first, then: PYTHONPATH=. python3 scripts/test_hybrid.py
"""

from app.retrieval.hybrid import hybrid_search

QUERIES = [
    "What was Q3 revenue?",
    "What are the risk factors around revenue recognition timing?",
    "How did the SMB segment perform this quarter?",
    "What were operating expenses driven by?",
]

for query in QUERIES:
    print(f"\n=== {query} ===")
    for r in hybrid_search(query, top_k=3):
        print(f"  [{r.score:.4f}] {r.source}#{r.chunk_index}  {r.text[:100]}")
