"""
Re-scores already-collected eval answers in eval_results.json against the
current scorer logic, without calling any LLM. Useful when the scoring
logic itself was fixed (e.g. the Unicode-normalization fix in
app/text_utils.py) but the underlying answers didn't need to change - no
reason to re-spend quota re-answering questions we already have real
answers for.

Run with: PYTHONPATH=. python3 scripts/rescore_eval.py
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

from app.eval.cases import CASES
from app.eval.scorer import score_case

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RESULTS_PATH = Path("eval_results.json")
report = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
cases_by_question = {c.question: c for c in CASES}

rescored = []
for saved in report["cases"]:
    case = cases_by_question.get(saved["question"])
    if case is None:
        continue  # question no longer in cases.py (e.g. wording changed) - skip
    agent_result = {
        "answer": saved["answer"],
        "route_type": saved["route_type"],
        "grounded": saved["grounded"] if "grounded" in saved else False,
        "attempts": saved["attempts"],
    }
    result = score_case(case, agent_result)
    old_hallucinated = saved["hallucinated"]
    if old_hallucinated != result.hallucinated:
        print(f"CHANGED: {case.question}")
        print(f"  was: hallucinated={old_hallucinated} ({saved['failure_reason']})")
        print(f"  now: hallucinated={result.hallucinated} ({result.failure_reason})")
    rescored.append(
        {
            "question": case.question,
            "category": case.category,
            "should_be_answerable": case.should_be_answerable,
            "hallucinated": result.hallucinated,
            "failure_reason": result.failure_reason,
            "route_type": result.route_type,
            "attempts": result.attempts,
            "answer": result.answer,
        }
    )

hallucinated_count = sum(c["hallucinated"] for c in rescored)
hallucination_rate = hallucinated_count / len(rescored) * 100 if rescored else 0.0

by_category: dict[str, list] = defaultdict(list)
for c in rescored:
    by_category[c["category"]].append(c)

print(f"\n=== Re-scored: {len(rescored)}/{len(CASES)} cases ===")
print(f"Overall hallucination rate: {hallucination_rate:.1f}% ({hallucinated_count}/{len(rescored)})")
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

report["total_cases_scored"] = len(rescored)
report["hallucinated_count"] = hallucinated_count
report["hallucination_rate_percent"] = round(hallucination_rate, 1)
report["by_category"] = category_summary
report["cases"] = rescored
RESULTS_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(f"\nRe-scored report written to {RESULTS_PATH}")
