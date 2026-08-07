"""
The self-correcting RAG loop: retrieve -> synthesize -> verify, and if the
verifier says the answer isn't grounded in the retrieved context, rewrite
the search query and try again (bounded by max_attempts so it can't loop
forever). This is the Corrective RAG / Self-RAG pattern - the thing that
differentiates this project from a basic retrieve-then-generate chatbot.

See DEVLOG.md for why this exists: a real test run produced a correct fact
attributed to the wrong source, and the plain retrieve->synthesize loop had
no way to catch that. This graph is what catches it.
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.verify import verify_answer
from app.models.llm_router import call_llm
from app.retrieval.hybrid import hybrid_search
from app.retrieval.vector_store import RetrievedChunk

SYNTHESIZER_PROMPT = (
    "Answer the user's question using only the provided context. "
    "If the context doesn't contain the answer, say so instead of guessing."
)

QUERY_REWRITE_PROMPT = (
    "A previous search and answer attempt failed fact-checking for the reason given below. "
    "Rewrite the search query to find better supporting evidence for the original question. "
    "Respond with only the rewritten query, nothing else."
)


class AgentState(TypedDict):
    question: str  # the original question - never rewritten, used for the final answer
    search_query: str  # what actually gets searched - may get rewritten on retry
    chunks: list[RetrievedChunk]
    answer: str
    grounded: bool
    verification_reason: str
    attempts: int
    max_attempts: int


def retrieve(state: AgentState) -> dict:
    return {"chunks": hybrid_search(state["search_query"], top_k=5)}


def synthesize(state: AgentState) -> dict:
    context = "\n\n".join(f"[{c.source}#{c.chunk_index}] {c.text}" for c in state["chunks"])
    messages = [
        {"role": "system", "content": SYNTHESIZER_PROMPT},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {state['question']}"},
    ]
    return {"answer": call_llm(role="synthesizer", messages=messages)}


def verify(state: AgentState) -> dict:
    result = verify_answer(state["question"], state["chunks"], state["answer"])
    return {"grounded": result.grounded, "verification_reason": result.reason}


def rewrite_query(state: AgentState) -> dict:
    messages = [
        {"role": "system", "content": QUERY_REWRITE_PROMPT},
        {
            "role": "user",
            "content": (
                f"Original question: {state['question']}\n"
                f"Previous search query: {state['search_query']}\n"
                f"Why the last answer failed fact-checking: {state['verification_reason']}"
            ),
        },
    ]
    new_query = call_llm(role="query_rewrite", messages=messages, temperature=0.3)
    return {"search_query": new_query.strip(), "attempts": state["attempts"] + 1}


def route_after_verify(state: AgentState) -> str:
    if state["grounded"] or state["attempts"] >= state["max_attempts"]:
        return "end"
    return "retry"


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("synthesize", synthesize)
    graph.add_node("verify", verify)
    graph.add_node("rewrite_query", rewrite_query)

    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "synthesize")
    graph.add_edge("synthesize", "verify")
    graph.add_conditional_edges("verify", route_after_verify, {"end": END, "retry": "rewrite_query"})
    graph.add_edge("rewrite_query", "retrieve")

    return graph.compile()


def answer_question(question: str, max_attempts: int = 2) -> AgentState:
    """Run the full self-correcting loop for a single question."""
    app = build_graph()
    initial_state: AgentState = {
        "question": question,
        "search_query": question,
        "chunks": [],
        "answer": "",
        "grounded": False,
        "verification_reason": "",
        "attempts": 0,
        "max_attempts": max_attempts,
    }
    return app.invoke(initial_state)
