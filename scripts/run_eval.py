"""
Evaluation harness: runs every case in app/eval/cases.py through the full
agent, scores each answer against its ground truth, and reports a
hallucination rate - the actual number backing this project's core claim,
not just an assertion. Reports a per-category breakdown as well as the
overall rate, since a system that aces simple lookups can still fail
badly on paraphrased or multi-hop questions - one flat number would hide
that.

Run with: PYTHONPATH=. python3 scripts/run_eval.py [limit]
An optional integer limit runs at most N cases that don't already have a
successful result from a previous run. This is a resumable harness, not
a fresh-every-time one: if eval_results.json already has a real result
for a question, this run skips it and only spends quota on cases not yet
scored - built after repeatedly hitting the free-tier daily token quota
mid-run (see DEVLOG.md) and not wanting to re-spend tokens re-answering
questions we already have good data for.

Writes the merged (old + new) report to eval_results.json.
"""

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app.agent.graph import answer_question
from app.eval.cases import CASES
from app.eval.scorer import score_case

RESULTS_PATH = Path("eval_results.json")

previous_cases = {}
if RESULTS_PATH.exists():
    previous = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    previous_cases = {c["question"]: c for c in previous.get("cases", [])}

pending = [c for c in CASES if c.question not in previous_cases]
limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(pending)
cases = pending[:limit]

print(f"{len(previous_cases)} case(s) already scored from a previous run, {len(pending)} remaining.")
print(f"Running {len(cases)} case(s) this pass.\n")

new_results = []
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
    new_results.append(result)
    status = "HALLUCINATED" if result.hallucinated else "ok"
    print(f"    {status}  route={result.route_type}  attempts={result.attempts}")
    if result.hallucinated:
        print(f"    reason: {result.failure_reason}")
        print(f"    answer: {result.answer}")

if errored_questions:
    print(f"\n{len(errored_questions)} case(s) failed to run this pass (still pending for next time):")
    for q in errored_questions:
        print(f"  - {q}")

all_cases = list(previous_cases.values()) + [
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
    for r in new_results
]

hallucinated_count = sum(c["hallucinated"] for c in all_cases)
hallucination_rate = hallucinated_count / len(all_cases) * 100 if all_cases else 0.0

by_category: dict[str, list] = defaultdict(list)
for c in all_cases:
    by_category[c["category"]].append(c)

still_pending = len(CASES) - len(all_cases)

print(f"\n=== Cumulative results: {len(all_cases)}/{len(CASES)} cases scored ===")
if still_pending:
    print(f"({still_pending} case(s) still not yet run - rate below is over what's been scored so far)")
print(f"Overall hallucination rate: {hallucination_rate:.1f}% ({hallucinated_count}/{len(all_cases)})")
print("\nBy category:")
category_summary = {}
for category, cat_cases in by_category.items():
    cat_hallucinated = sum(c["hallucinated"] for c in cat_cases)
    cat_rate = cat_hallucinated / len(cat_cases) * 100
    category_summary[category] = {
        "total": len(cat_cases),
        "hallucinated": cat_hallucinated,
        "rate_percent": round(cat_rate, 1),
    }
    print(f"  {category:20s} {cat_rate:5.1f}%  ({cat_hallucinated}/{len(cat_cases)})")

report = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "total_cases_defined": len(CASES),
    "total_cases_scored": len(all_cases),
    "hallucinated_count": hallucinated_count,
    "hallucination_rate_percent": round(hallucination_rate, 1),
    "by_category": category_summary,
    "cases": all_cases,
}
RESULTS_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(f"\nMerged report written to {RESULTS_PATH}")
