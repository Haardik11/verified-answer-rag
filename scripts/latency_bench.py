"""
Times real end-to-end answer_question() calls (production config,
with_verification=True) and reports average latency per category. Runs the
full category for small categories (multi_hop, unanswerable, exact_figure)
and a fixed sample for the two large ones (simple_lookup, paraphrased) to
limit how much of the daily Groq quota this costs - sample size is printed
next to every number so nothing here is silently presented as exhaustive.

Run with: PYTHONPATH=. python3 scripts/latency_bench.py
"""

import sys
import time
from collections import defaultdict

from app.agent.graph import answer_question
from app.eval.cases import CASES

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SAMPLE_SIZE = {"simple_lookup": 5, "paraphrased": 5}  # None below = run every case in that category

by_category = defaultdict(list)
for c in CASES:
    by_category[c.category].append(c)

selected = []
for category, cases in by_category.items():
    n = SAMPLE_SIZE.get(category)
    selected.extend(cases if n is None else cases[:n])

print(f"Timing {len(selected)} case(s) across {len(by_category)} categories\n")

timings = defaultdict(list)
errors = []
for i, case in enumerate(selected, 1):
    print(f"[{i}/{len(selected)}] ({case.category}) {case.question}")
    start = time.perf_counter()
    try:
        result = answer_question(case.question)
    except Exception as e:
        elapsed = time.perf_counter() - start
        print(f"    ERROR after {elapsed:.2f}s - {type(e).__name__}: {str(e)[:150]}")
        errors.append(case.question)
        continue
    elapsed = time.perf_counter() - start
    timings[case.category].append(elapsed)
    print(f"    {elapsed:.2f}s  attempts={result['attempts']}  route={result['route_type']}")

print("\n=== Average latency by category ===")
all_times = []
for category in sorted(timings):
    vals = timings[category]
    all_times.extend(vals)
    avg = sum(vals) / len(vals)
    print(f"  {category:14s} avg={avg:6.2f}s  min={min(vals):6.2f}s  max={max(vals):6.2f}s  (n={len(vals)})")

if all_times:
    print(f"\n  {'overall':14s} avg={sum(all_times)/len(all_times):6.2f}s  (n={len(all_times)})")
if errors:
    print(f"\n{len(errors)} case(s) errored and are excluded from the averages above: {errors}")
