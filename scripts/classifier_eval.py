"""
Hand-labeled test set for the router's 3-way classification
(app.agent.graph.route), built the same way app/eval/cases.py was: ground
truth assigned by hand against the router's own defined categories (see
ROUTER_PROMPT), not generated or guessed.

Trimmed to 10 examples per class (30 total) rather than the originally
planned 54 - the daily Groq quota got tight partway through the larger run,
and 10/class is still enough that one lucky or unlucky call doesn't swing
the per-class number much, just with coarser resolution than 18/class would
give (each case is worth ~3.3 points instead of ~1.85).

The 10 "document" cases below were already run once (all 10 came back
correct) before this file was trimmed down - their results are recorded
directly rather than re-spent from the quota, same reasoning as the
resumable pattern in scripts/run_eval.py: don't re-buy an answer we already
paid for and verified.

Resumable like run_eval.py: writes to classifier_eval_results.json after
every case, skips questions already scored on a re-run, and catches a
mid-run quota error without losing progress collected so far.

Run with: PYTHONPATH=. python3 scripts/classifier_eval.py
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

from app.agent.graph import route

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RESULTS_PATH = Path("classifier_eval_results.json")

# Already run for real against the live router - not re-called on future runs.
ALREADY_SCORED: list[dict] = [
    {"question": "What was Q3 revenue?", "expected": "document", "predicted": "document"},
    {"question": "How many employees does the company have?", "expected": "document", "predicted": "document"},
    {"question": "Tell me about the security incident", "expected": "document", "predicted": "document"},
    {"question": "What's the NPS score?", "expected": "document", "predicted": "document"},
    {"question": "How much did we spend on cloud infrastructure?", "expected": "document", "predicted": "document"},
    {"question": "What's driving up operating expenses?", "expected": "document", "predicted": "document"},
    {"question": "Is the platform reliable?", "expected": "document", "predicted": "document"},
    {"question": "How's customer retention trending?", "expected": "document", "predicted": "document"},
    {"question": "What happened with the database migration?", "expected": "document", "predicted": "document"},
    {"question": "Give me the SMB numbers", "expected": "document", "predicted": "document"},
]

CASES: list[tuple[str, str]] = [
    # --- chitchat (10) ---
    ("hi", "chitchat"),
    ("hello there", "chitchat"),
    ("thanks!", "chitchat"),
    ("thank you so much", "chitchat"),
    ("good morning", "chitchat"),
    ("how are you", "chitchat"),
    ("what can you do", "chitchat"),
    ("who are you", "chitchat"),
    ("bye", "chitchat"),
    ("see you later", "chitchat"),
    # --- general_knowledge (10) ---
    ("What is 1+1?", "general_knowledge"),
    ("How many trophies has CSK won?", "general_knowledge"),
    ("What's the capital of France?", "general_knowledge"),
    ("Who wrote Romeo and Juliet?", "general_knowledge"),
    ("What's the boiling point of water?", "general_knowledge"),
    ("How many continents are there?", "general_knowledge"),
    ("What year did WW2 end?", "general_knowledge"),
    ("Who is the president of the United States?", "general_knowledge"),
    ("What's the speed of light?", "general_knowledge"),
    ("How tall is Mount Everest?", "general_knowledge"),
]

previous = {}
if RESULTS_PATH.exists():
    previous = {r["question"]: r for r in json.loads(RESULTS_PATH.read_text(encoding="utf-8"))}
for r in ALREADY_SCORED:
    previous.setdefault(r["question"], r)

pending = [(q, e) for q, e in CASES if q not in previous]
print(f"{len(previous)} case(s) already scored, {len(pending)} remaining this run.\n")

for question, expected in pending:
    try:
        predicted = route({"question": question})["route_type"]
    except Exception as e:
        print(f"STOPPED - {type(e).__name__}: {str(e)[:200]}")
        break
    previous[question] = {"question": question, "expected": expected, "predicted": predicted}
    status = "OK" if predicted == expected else "MISS"
    print(f"{status:4s} expected={expected:18s} got={predicted:18s}  {question!r}")
    RESULTS_PATH.write_text(json.dumps(list(previous.values()), indent=2), encoding="utf-8")

all_results = list(previous.values())
correct = sum(r["expected"] == r["predicted"] for r in all_results)
print(f"\n=== Cumulative: {len(all_results)}/{len(CASES) + len(ALREADY_SCORED)} planned cases scored ===")
print(f"Overall accuracy: {correct}/{len(all_results)} = {correct/len(all_results)*100:.1f}%")

by_class: dict[str, list] = defaultdict(list)
for r in all_results:
    by_class[r["expected"]].append(r)
print("\nPer-class:")
for label, rows in sorted(by_class.items()):
    right = sum(r["predicted"] == label for r in rows)
    print(f"  {label:18s} {right}/{len(rows)} = {right/len(rows)*100:.1f}%")

misses = [r for r in all_results if r["expected"] != r["predicted"]]
if misses:
    print(f"\n{len(misses)} miss(es):")
    for r in misses:
        print(f"  expected={r['expected']} got={r['predicted']}  {r['question']!r}")
