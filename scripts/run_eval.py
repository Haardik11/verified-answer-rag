"""
Evaluation harness: runs every case in app/eval/cases.py through the full
agent, scores each answer against its ground truth, and reports a
hallucination rate - the actual number backing this project's core claim,
not just an assertion.

Run with: PYTHONPATH=. python3 scripts/run_eval.py [limit]
An optional integer limit runs only the first N cases (useful for
validating the harness itself without spending a full run's worth of
tokens - see DEVLOG.md for why that matters here).

Writes a full report to eval_results.json alongside the console summary.
"""

import json
import sys
from datetime import datetime, timezone

from app.agent.graph import answer_question
from app.eval.cases import CASES
from app.eval.scorer import score_case

limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(CASES)
cases = CASES[:limit]

results = []
for i, case in enumerate(cases, 1):
    print(f"[{i}/{len(cases)}] {case.question}")
    agent_result = answer_question(case.question)
    result = score_case(case, agent_result)
    results.append(result)
    status = "HALLUCINATED" if result.hallucinated else "ok"
    print(f"    {status}  route={result.route_type}  attempts={result.attempts}")
    if result.hallucinated:
        print(f"    reason: {result.failure_reason}")
        print(f"    answer: {result.answer}")

hallucinated_count = sum(r.hallucinated for r in results)
hallucination_rate = hallucinated_count / len(results) * 100 if results else 0.0

print(f"\n=== Results: {len(results)} cases ===")
print(f"Hallucination rate: {hallucination_rate:.1f}% ({hallucinated_count}/{len(results)})")

report = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "total_cases": len(results),
    "hallucinated_count": hallucinated_count,
    "hallucination_rate_percent": round(hallucination_rate, 1),
    "cases": [
        {
            "question": r.case.question,
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
print("Full report written to eval_results.json")
