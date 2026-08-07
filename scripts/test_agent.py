"""
Runs a real question through the full self-correcting agent loop
(retrieve -> synthesize -> verify -> retry if not grounded), streaming
each step as it happens so a failed first attempt and the retry it
triggers are actually visible, not just the final answer.

Requires build_index.py to have been run first, and Ollama running locally
with the models configured in app/config.py pulled.

Run with: PYTHONPATH=. python3 scripts/test_agent.py
"""

from app.agent.graph import build_graph

QUESTION = "What was Q3 revenue and how did it compare to the prior year?"

initial_state = {
    "question": QUESTION,
    "search_query": QUESTION,
    "chunks": [],
    "answer": "",
    "grounded": False,
    "verification_reason": "",
    "attempts": 0,
    "max_attempts": 2,
}

print(f"Question: {QUESTION}\n")

final_state = dict(initial_state)
app = build_graph()
for step in app.stream(initial_state):
    for node_name, update in step.items():
        print(f"--- {node_name} ---")
        if "answer" in update:
            print(f"  answer: {update['answer']}")
        if "grounded" in update:
            print(f"  grounded: {update['grounded']}")
            print(f"  reason: {update['verification_reason']}")
        if "search_query" in update and node_name == "rewrite_query":
            print(f"  rewrote search query to: {update['search_query']}")
        final_state.update(update)

print("\n=== Final ===")
print(f"Attempts: {final_state['attempts']}")
print(f"Grounded: {final_state['grounded']}")
print(f"\nFinal answer:\n{final_state['answer']}")
