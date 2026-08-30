"""
Follow-up to scripts/retrieval_metrics.py: that test found hybrid and
dense-only tied at 100% hit rate@5 on the main 39-case eval set, with no
consistent winner even at smaller k. The question this script answers is
whether that's because the corpus genuinely doesn't contain queries where
BM25 should matter, or because hybrid isn't contributing even where it
theoretically should.

data/sample_expenses.csv indexes as a single chunk (see conversation) of
14 near-identical templated rows ("Month: X, Category: Y, Amount USD: Z,
Department: W") - Cloud Infrastructure and Marketing Campaigns each appear
three times, once per month, differing only in the exact month token and
number. Meanwhile data/sample_large.pdf's Infrastructure Report separately
discusses "cloud infrastructure spend...340,000...298,000" in prose that is
semantically very close to "how much was spent on cloud infrastructure" -
without ever naming a specific month. This is exactly the setup where a
dense embedding might prefer the more prototypical prose paragraph over the
terse, exact-match-only CSV row, while BM25 should latch onto the literal
month name. Every query below has its answer ONLY in the CSV chunk.

The corpus only has 14 chunks total (top_k=5 already retrieves over a
third of everything), so this checks top_k=1 and top_k=2, where winning
the top slot actually means something.

Run with: PYTHONPATH=. python3 scripts/retrieval_hybrid_targeted.py
"""

import sys

from app.retrieval.hybrid import hybrid_search
from app.retrieval.vector_store import dense_search

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CSV_SOURCE = "data/sample_expenses.csv"

QUERIES = [
    ("How much was spent on cloud infrastructure in July?", "102000"),
    ("How much was spent on cloud infrastructure in September?", "120000"),
    ("What was the marketing campaign spend in August?", "140000"),
    ("What was the marketing campaign spend in September?", "58000"),
    ("How much were sales salaries in July?", "290000"),
    ("How much did engineering salaries cost in August?", "412000"),
    ("How much was the office equipment expense?", "22000"),
]


def hit(search_fn, query, top_k) -> bool:
    chunks = search_fn(query, top_k=top_k)
    return any(c.source == CSV_SOURCE for c in chunks)


for top_k in (1, 2, 3, 5):
    print(f"=== top_k={top_k} ===")
    h_hits = d_hits = 0
    for query, expected_number in QUERIES:
        h = hit(hybrid_search, query, top_k)
        d = hit(dense_search, query, top_k)
        h_hits += h
        d_hits += d
        flag = "" if h == d else "  <-- DIFFERS"
        print(f"  hybrid={int(h)} dense_only={int(d)}  {query!r} (expects {expected_number}){flag}")
    n = len(QUERIES)
    print(f"  -> hybrid {h_hits}/{n} = {h_hits/n*100:.1f}%   dense_only {d_hits}/{n} = {d_hits/n*100:.1f}%\n")
