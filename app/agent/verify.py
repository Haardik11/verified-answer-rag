"""
Checks whether a synthesized answer is actually supported by the retrieved
context, rather than trusting the synthesizer's output at face value. This
is the core of the self-correction loop - it catches both hallucination (a
fact not present anywhere in the context) and citation mislabeling (a real
fact attributed to the wrong specific source). Citation checking was
relaxed for a while (see DEVLOG.md step 12) while the synthesizer itself
was unreliable at citing correctly on the free local model; re-enabled
once both roles moved to a stronger model and the root cause was fixed at
the source (step 14).
"""

from dataclasses import dataclass

from app.models.llm_router import call_llm
from app.retrieval.vector_store import RetrievedChunk

VERIFIER_PROMPT = """You are a strict fact-checker. Given a CONTEXT and an ANSWER, \
decide whether every claim in the ANSWER is directly supported by the CONTEXT. Do not \
give credit for an answer that adds any fact, number, or detail not present anywhere \
in the CONTEXT.

Also check citation accuracy: each CONTEXT chunk is labeled with its exact source, \
like [data/sample.pdf#0]. If the ANSWER states which specific source a fact came from \
(citing a bracketed label, or describing it in words like "the PDF" or "the text \
file"), that citation must correctly match the chunk the fact actually appears in. A \
true fact attributed to the wrong source is NOT_GROUNDED.

If the ANSWER honestly states that the CONTEXT does not contain the information \
needed to answer the QUESTION, and it does not invent an answer anyway, that is \
GROUNDED - an honest "I don't know" is always a pass, never a failure.

Think through your reasoning first, then give your verdict last so it actually
follows from that reasoning. Respond in exactly this format, nothing else:
REASON: one sentence explaining your judgment
VERDICT: GROUNDED or NOT_GROUNDED - must directly follow from the REASON above"""


@dataclass
class VerificationResult:
    grounded: bool
    reason: str


def verify_answer(question: str, chunks: list[RetrievedChunk], answer: str) -> VerificationResult:
    context = "\n\n".join(f"[{c.source}#{c.chunk_index}] {c.text}" for c in chunks)
    messages = [
        {"role": "system", "content": VERIFIER_PROMPT},
        {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}\n\nANSWER: {answer}"},
    ]
    response = call_llm(role="verifier", messages=messages, temperature=0.0)
    return _parse(response)


def _parse(response: str) -> VerificationResult:
    lines = response.splitlines()
    verdict_line = next((l for l in lines if l.strip().upper().startswith("VERDICT")), "")
    reason_line = next((l for l in lines if l.strip().upper().startswith("REASON")), "")

    verdict = verdict_line.upper()
    # Check NOT_GROUNDED first since "GROUNDED" is a substring of it. If the
    # model didn't follow the format at all, default to NOT grounded - an
    # unparseable verdict shouldn't be silently treated as a pass.
    grounded = "NOT_GROUNDED" not in verdict and "GROUNDED" in verdict
    reason = reason_line.split(":", 1)[1].strip() if ":" in reason_line else response.strip()
    return VerificationResult(grounded=grounded, reason=reason)
