"""
Times the router's classification call (app.agent.graph.route) in isolation,
separate from the full retrieve/synthesize/verify pipeline - this is the
"added routing latency" a message pays before anything else happens. No
labeled test set is needed for this measurement (unlike classification
accuracy, which needs real ground-truth labels this repo doesn't have yet -
see DEVLOG/conversation) since we're only timing the call, not checking
whether its answer was correct.

Run with: PYTHONPATH=. python3 scripts/router_latency.py
"""

import sys
import time

from app.agent.graph import route

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# A mix pulled from real eval cases plus a couple of chitchat messages, so this
# isn't only timing one route type - covers all 3 classes the router assigns.
MESSAGES = [
    "What was Q3 revenue?",
    "How much money did the company make in Q3?",
    "Why was the database migration delayed from its original Q2 target?",
    "What is 1+1?",
    "How many trophies has CSK won?",
    "Who is the CEO of the company?",
    "hi",
    "thanks!",
    "What month did the security incident occur?",
    "tell me about q2",
]

timings = []
for msg in MESSAGES:
    start = time.perf_counter()
    result = route({"question": msg})
    elapsed = time.perf_counter() - start
    timings.append(elapsed)
    print(f"{elapsed:6.2f}s  -> {result['route_type']:18s}  {msg!r}")

avg = sum(timings) / len(timings)
print(f"\nAverage router-only latency: {avg:.2f}s  (n={len(timings)}, min={min(timings):.2f}s, max={max(timings):.2f}s)")
