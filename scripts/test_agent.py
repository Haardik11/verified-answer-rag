"""
Runs a real question through the full retrieve -> synthesize agent loop.
Requires build_index.py to have been run first, and Ollama running locally
with the model configured in app/config.py pulled.

Run with: PYTHONPATH=. python3 scripts/test_agent.py
"""

from app.agent.graph import answer_question

QUESTION = "What was Q3 revenue and how did it compare to the prior year?"

result = answer_question(QUESTION)

print(f"Question: {QUESTION}\n")
print("Retrieved chunks:")
for c in result["chunks"]:
    print(f"  [{c.score:.4f}] {c.source}#{c.chunk_index}  {c.text[:80]}")
print(f"\nAnswer:\n{result['answer']}")
