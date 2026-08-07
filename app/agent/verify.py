"""
Checks whether a synthesized answer is actually supported by the retrieved
context, rather than trusting the synthesizer's output at face value. This
is the core of the self-correction loop - the thing it's meant to catch is
hallucination (a fact not present anywhere in the context), not cosmetic
issues like citing the wrong specific document for an otherwise real fact.
"""

from dataclasses import dataclass

from app.models.llm_router import call_llm
from app.retrieval.vector_store import RetrievedChunk

VERIFIER_PROMPT = """You are a strict fact-checker focused on catching hallucination: \
does the ANSWER state anything that is not actually supported by the CONTEXT? Do not \
give credit for an answer that adds any fact, number, or detail not present anywhere \
in the CONTEXT.

Do not penalize the ANSWER for citing the wrong specific document (e.g. saying "the \
text file" when the detail was actually in the PDF) as long as the underlying fact \
itself is real and present somewhere in the CONTEXT - that is a minor labeling slip, \
not a hallucination, and should still be marked GROUNDED.

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
