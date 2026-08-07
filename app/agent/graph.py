"""
The baseline retrieve -> synthesize RAG loop, wired as a LangGraph state
graph. This is deliberately the simplest working version - no verification
or re-retrieval yet. That self-correction loop gets added as its own step
once this proves out end to end, so there's a known-working baseline to
compare it against.
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.models.llm_router import call_llm
from app.retrieval.hybrid import hybrid_search
from app.retrieval.vector_store import RetrievedChunk

SYSTEM_PROMPT = (
    "Answer the user's question using only the provided context. "
    "If the context doesn't contain the answer, say so instead of guessing."
)


class AgentState(TypedDict):
    question: str
    chunks: list[RetrievedChunk]
    answer: str


def retrieve(state: AgentState) -> dict:
    return {"chunks": hybrid_search(state["question"], top_k=5)}


def synthesize(state: AgentState) -> dict:
    context = "\n\n".join(f"[{c.source}#{c.chunk_index}] {c.text}" for c in state["chunks"])
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {state['question']}"},
    ]
    return {"answer": call_llm(role="synthesizer", messages=messages)}


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("synthesize", synthesize)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "synthesize")
    graph.add_edge("synthesize", END)
    return graph.compile()


def answer_question(question: str) -> AgentState:
    """Run the full retrieve -> synthesize loop for a single question."""
    app = build_graph()
    return app.invoke({"question": question, "chunks": [], "answer": ""})
