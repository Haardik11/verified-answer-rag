"""
Measures whether retrieval actually surfaces the fact needed to answer each
case, comparing hybrid (dense + BM25 + RRF) against dense-only (Qdrant alone).

This is a "Hit Rate@k" over the 33 answerable cases that have expected_keywords
(simple_lookup, paraphrased, multi_hop, exact_figure) - NOT precision/recall in
the strict IR sense, since we don't have a full relevance judgment (which of
every chunk in the corpus is "relevant" to each question). What we do have is
ground truth on which fact must appear for the answer to be correct, so this
checks: does that fact's exact text show up somewhere in the top-k retrieved
chunks, before the LLM ever sees them? A case counts as a hit only if every
expected keyword for that case is present in the retrieved chunk set.

Unanswerable cases (6) are excluded - there's no keyword to check retrieval
against, since by design nothing in the corpus should support them.

Run with: PYTHONPATH=. python3 scripts/retrieval_metrics.py
"""

import sys

from app.eval.cases import CASES
from app.retrieval.hybrid import hybrid_search
from app.retrieval.vector_store import dense_search
from app.text_utils import normalize_text

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

eligible = [c for c in CASES if c.should_be_answerable and c.expected_keywords]
print(f"{len(eligible)} eligible cases (answerable, with expected_keywords) out of {len(CASES)} total\n")


def hit(search_fn, case, top_k) -> bool:
    chunks = search_fn(case.question, top_k=top_k)
    blob = normalize_text(" ".join(c.text for c in chunks).lower())
    return all(normalize_text(kw.lower()) in blob for kw in case.expected_keywords)


for TOP_K in (1, 2, 3, 5):
    results = {"hybrid": [], "dense_only": []}
    diffs = []
    for case in eligible:
        h_hybrid = hit(hybrid_search, case, TOP_K)
        h_dense = hit(dense_search, case, TOP_K)
        results["hybrid"].append(h_hybrid)
        results["dense_only"].append(h_dense)
        if h_hybrid != h_dense:
            diffs.append((case.category, case.question, h_hybrid, h_dense))

    print(f"=== Hit Rate@{TOP_K} ===")
    for method in ("hybrid", "dense_only"):
        n = len(results[method])
        hits = sum(results[method])
        print(f"  {method:12s} {hits}/{n} = {hits/n*100:.1f}%")
    if diffs:
        print("  Cases where methods differ:")
        for category, question, h, d in diffs:
            print(f"    [{category}] hybrid={int(h)} dense_only={int(d)}  {question}")
    print()
