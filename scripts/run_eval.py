"""
Evaluation harness: runs every case in app/eval/cases.py through the full
agent, scores each answer against its ground truth, and reports a
hallucination rate - the actual number backing this project's core claim,
not just an assertion. Reports a per-category breakdown as well as the
overall rate, since a system that aces simple lookups can still fail
badly on paraphrased or multi-hop questions - one flat number would hide
that.

Run with: PYTHONPATH=. python3 scripts/run_eval.py [limit]
An optional integer limit runs only the first N cases (useful for
validating the harness itself without spending a full run's worth of
tokens - see DEVLOG.md for why that matters here).

Writes a full report to eval_results.json alongside the console summary.
"""

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone

from app.agent.graph import answer_question
from app.eval.cases import CASES
from app.eval.scorer import score_case

limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(CASES)
cases = CASES[:limit]

results = []
errored_questions = []
for i, case in enumerate(cases, 1):
    print(f"[{i}/{len(cases)}] ({case.category}) {case.question}")
    try:
        agent_result = answer_question(case.question)
    except Exception as e:
        # Don't let one failure (e.g. hitting the daily quota mid-run) throw away
        # every result collected so far - record it and keep going, so a partial
        # run still produces a usable report instead of nothing at all.
        print(f"    ERROR - skipping: {type(e).__name__}: {str(e)[:150]}")
        errored_questions.append(case.question)
        continue
    result = score_case(case, agent_result)
    results.append(result)
    status = "HALLUCINATED" if result.hallucinated else "ok"
    print(f"    {status}  route={result.route_type}  attempts={result.attempts}")
    if result.hallucinated:
        print(f"    reason: {result.failure_reason}")
        print(f"    answer: {result.answer}")

if errored_questions:
    print(f"\n{len(errored_questions)} case(s) failed to run (not scored, excluded from the rate below):")
    for q in errored_questions:
        print(f"  - {q}")

hallucinated_count = sum(r.hallucinated for r in results)
hallucination_rate = hallucinated_count / len(results) * 100 if results else 0.0

by_category: dict[str, list] = defaultdict(list)
for r in results:
    by_category[r.case.category].append(r)

print(f"\n=== Results: {len(results)} cases ===")
print(f"Overall hallucination rate: {hallucination_rate:.1f}% ({hallucinated_count}/{len(results)})")
print("\nBy category:")
category_summary = {}
for category, cat_results in by_category.items():
    cat_hallucinated = sum(r.hallucinated for r in cat_results)
    cat_rate = cat_hallucinated / len(cat_results) * 100
    category_summary[category] = {
        "total": len(cat_results),
        "hallucinated": cat_hallucinated,
        "rate_percent": round(cat_rate, 1),
    }
    print(f"  {category:20s} {cat_rate:5.1f}%  ({cat_hallucinated}/{len(cat_results)})")

report = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "total_cases": len(results),
    "hallucinated_count": hallucinated_count,
    "hallucination_rate_percent": round(hallucination_rate, 1),
    "errored_questions": errored_questions,
    "by_category": category_summary,
    "cases": [
        {
            "question": r.case.question,
            "category": r.case.category,
            "should_be_answerable": r.case.should_be_answerable,
            "hallucinated": r.hallucinated,
            "failure_reason": r.failure_reason,
            "route_type": r.route_type,
            "attempts": r.attempts,
            "answer": r.answer,
        }
        for r in results
    ],
}
with open("eval_results.json", "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)
print("\nFull report written to eval_results.json")
