"""
Checks whether a synthesized answer is actually supported by the retrieved
context, rather than trusting the synthesizer's output at face value. This
is the core of the self-correction loop - it's what should catch cases
like a correct fact attributed to the wrong source (see DEVLOG step 9).
"""

from dataclasses import dataclass

from app.models.llm_router import call_llm
from app.retrieval.vector_store import RetrievedChunk

VERIFIER_PROMPT = """You are a strict fact-checker. Given a CONTEXT and an ANSWER, \
decide whether every claim in the ANSWER - including which specific source it is \
attributed to - is directly supported by the CONTEXT. Do not give credit for an \
answer that is directionally correct but misattributes a claim to the wrong part \
of the context, or adds any detail not present in the context.

Respond in exactly this format, nothing else:
VERDICT: GROUNDED or NOT_GROUNDED
REASON: one sentence explaining why"""


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
