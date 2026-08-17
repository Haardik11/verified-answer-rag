"""
The self-correcting RAG loop: route -> retrieve -> synthesize -> verify, and
if the verifier says the answer isn't grounded in the retrieved context,
rewrite the search query and try again (bounded by max_attempts so it can't
loop forever). This is the Corrective RAG / Self-RAG pattern - the thing
that differentiates this project from a basic retrieve-then-generate
chatbot.

See DEVLOG.md for why this exists: a real test run produced a correct fact
attributed to the wrong source, and the plain retrieve->synthesize loop had
no way to catch that. This graph is what catches it.

The routing step exists because a real test asking a plain greeting ("hi")
still ran full retrieval and showed 5 unrelated source chunks marked
"Verified" - retrieval and verification only make sense for actual
questions about the documents, not conversational messages. The third
route (general knowledge) exists for the same reason a strict refusal for
something like "what is 1+1" felt wrong: the fix isn't to let the verifier
be lenient about ungrounded answers (that would dilute what "Verified"
means for everything else) - it's to honestly label an answer as *not*
grounded in the documents rather than either refusing pointlessly or
falsely calling it "Verified".
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.verify import verify_answer
from app.models.llm_router import call_llm
from app.retrieval.hybrid import hybrid_search
from app.retrieval.vector_store import RetrievedChunk
from app.text_utils import normalize_text

ROUTER_PROMPT = (
    "Classify the user's message as exactly one word.\n"
    "DOCUMENT_QUESTION - a real question that could plausibly be answered by the indexed business "
    "documents (financial reports, quarterly metrics, company operations, etc.) - this includes vague "
    "or short references to business topics (a quarter like 'Q2', revenue, headcount, expenses, and "
    "similar), even if the phrasing doesn't explicitly say 'in our documents' or name the company. "
    "When a message is ambiguous but has any plausible connection to business/company topics, choose "
    "this - it's much better to search the documents and correctly report nothing relevant was found "
    "than to skip a question that might actually be answerable.\n"
    "CHITCHAT - a greeting, thanks, or general conversation that doesn't need document lookup.\n"
    "GENERAL_KNOWLEDGE - a real question that is CLEARLY unrelated to business/company documents, with "
    "no plausible connection to the kind of content these documents contain (basic arithmetic, sports "
    "trivia, general facts about the world).\n"
    "Respond with only that one word, nothing else."
)

CHITCHAT_PROMPT = (
    "You are the assistant for a document Q&A tool. Respond naturally and briefly to "
    "the user's message. If relevant, mention that you can answer questions about the "
    "indexed documents."
)

GENERAL_KNOWLEDGE_PROMPT = (
    "Answer the user's question directly and briefly using your own general knowledge. "
    "Do not mention documents or context - this question doesn't need them."
)

SYNTHESIZER_PROMPT = (
    "Answer the user's question using only the provided context, in clear, natural "
    "prose. If the context doesn't contain the answer, your entire response must be a "
    "short, direct statement that you don't have that information in the indexed "
    "documents - one sentence, nothing more. In that case, do not: guess or supply an "
    "answer from outside general knowledge (not even something simple like basic "
    "arithmetic); describe or summarize what the context IS about instead of answering; "
    "or explain why the context doesn't cover it. Just say you don't know and stop. "
    "Do not name or cite which specific document a fact came from, and do not include "
    "bracketed labels like [data/sample.pdf#0] in your answer - the exact source is "
    "tracked separately and shown to the user automatically, so just state the answer "
    "directly without narrating where it came from."
)

QUERY_REWRITE_PROMPT = (
    "A previous search and answer attempt failed fact-checking for the reason given below. "
    "Rewrite the search query to find better supporting evidence for the original question. "
    "Respond with only the rewritten query, nothing else."
)

REFUSAL_PREFIX = "i don't have that information"


class AgentState(TypedDict):
    question: str  # the original question - never rewritten, used for the final answer
    search_query: str  # what actually gets searched - may get rewritten on retry
    route_type: str  # "document" | "chitchat" | "general_knowledge"
    chunks: list[RetrievedChunk]
    answer: str
    is_refusal: bool  # true if the synthesizer's answer was a plain "I don't have that information"
    grounded: bool
    verification_reason: str
    attempts: int
    max_attempts: int


def route(state: AgentState) -> dict:
    messages = [
        {"role": "system", "content": ROUTER_PROMPT},
        {"role": "user", "content": state["question"]},
    ]
    response = call_llm(role="router", messages=messages, temperature=0.0).upper()
    if "GENERAL_KNOWLEDGE" in response:
        route_type = "general_knowledge"
    elif "CHITCHAT" in response:
        route_type = "chitchat"
    else:
        route_type = "document"
    return {"route_type": route_type}


def chitchat_reply(state: AgentState) -> dict:
    messages = [
        {"role": "system", "content": CHITCHAT_PROMPT},
        {"role": "user", "content": state["question"]},
    ]
    answer = call_llm(role="synthesizer", messages=messages)
    return {
        "answer": answer,
        "chunks": [],
        "grounded": True,
        "verification_reason": "Conversational message - no document lookup was needed.",
    }


def general_knowledge_reply(state: AgentState) -> dict:
    messages = [
        {"role": "system", "content": GENERAL_KNOWLEDGE_PROMPT},
        {"role": "user", "content": state["question"]},
    ]
    answer = call_llm(role="synthesizer", messages=messages)
    return {
        "answer": answer,
        "chunks": [],
        "grounded": False,  # not grounded in the documents by definition - this is the point
        "verification_reason": "Answered from general knowledge, not verified against your documents.",
    }


def retrieve(state: AgentState) -> dict:
    return {"chunks": hybrid_search(state["search_query"], top_k=5)}


def synthesize(state: AgentState) -> dict:
    context = "\n\n".join(f"[{c.source}#{c.chunk_index}] {c.text}" for c in state["chunks"])
    messages = [
        {"role": "system", "content": SYNTHESIZER_PROMPT},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {state['question']}"},
    ]
    answer = call_llm(role="synthesizer", messages=messages)
    is_refusal = normalize_text(answer).strip().lower().startswith(REFUSAL_PREFIX)
    return {"answer": answer, "is_refusal": is_refusal}


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


def route_after_classify(state: AgentState) -> str:
    return state["route_type"]


def route_after_verify(state: AgentState) -> str:
    if state["is_refusal"] or state["grounded"] or state["attempts"] >= state["max_attempts"]:
        return "end"
    return "retry"


def build_graph(with_verification: bool = True):
    """
    with_verification=False builds the bare baseline (route -> retrieve ->
    synthesize -> stop, no verify, no retry) - a real ablation for
    measuring what the verifier/self-correction loop actually contributes,
    not a simulation of it. Same route/retrieve/synthesize nodes either
    way, so the only difference is whether the self-check-and-retry step
    exists at all.
    """
    graph = StateGraph(AgentState)
    graph.add_node("route", route)
    graph.add_node("chitchat_reply", chitchat_reply)
    graph.add_node("general_knowledge_reply", general_knowledge_reply)
    graph.add_node("retrieve", retrieve)
    graph.add_node("synthesize", synthesize)

    graph.add_edge(START, "route")
    graph.add_conditional_edges(
        "route",
        route_after_classify,
        {"chitchat": "chitchat_reply", "general_knowledge": "general_knowledge_reply", "document": "retrieve"},
    )
    graph.add_edge("chitchat_reply", END)
    graph.add_edge("general_knowledge_reply", END)
    graph.add_edge("retrieve", "synthesize")

    if with_verification:
        graph.add_node("verify", verify)
        graph.add_node("rewrite_query", rewrite_query)
        graph.add_edge("synthesize", "verify")
        graph.add_conditional_edges("verify", route_after_verify, {"end": END, "retry": "rewrite_query"})
        graph.add_edge("rewrite_query", "retrieve")
    else:
        graph.add_edge("synthesize", END)

    return graph.compile()


def answer_question(question: str, max_attempts: int = 2, with_verification: bool = True) -> AgentState:
    """Run the self-correcting loop for a single question. Set
    with_verification=False to run the bare baseline instead, for
    measuring the verifier's real contribution via ablation."""
    app = build_graph(with_verification=with_verification)
    initial_state: AgentState = {
        "question": question,
        "search_query": question,
        "route_type": "document",
        "chunks": [],
        "answer": "",
        "is_refusal": False,
        "grounded": False,
        "verification_reason": "",
        "attempts": 0,
        "max_attempts": max_attempts,
    }
    return app.invoke(initial_state)
