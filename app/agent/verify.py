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

VERIFIER_PROMPT = """You are a strict fact-checker. Given a CONTEXT and an ANSWER, you \
must verify the ANSWER one claim at a time - never judge it as a whole at a glance, \
since that misses individually wrong claims hiding in an otherwise-plausible answer.

Step 1 - List every distinct claim the ANSWER makes, numbered, even if there is only \
one. For an ANSWER that is a single sentence, that is still one claim to check, not a \
reason to skip this step.

Step 2 - For each claim, check three things against the CONTEXT:
(a) Is the fact itself present in the CONTEXT, not invented or added?
(b) If the claim is a comparison ("up/down X percent", "higher/lower than", "compared \
to Y quarter/period"), does it use the same DIRECTION (increase vs decrease) and the \
same reference point (which specific period) as the CONTEXT? An inverted direction or \
wrong reference period is NOT SUPPORTED even when the numbers mentioned are real.
(c) If the claim states which specific source it came from (a bracketed label like \
[data/sample.pdf#0], or a description like "the PDF" or "the text file"), does that \
citation match which chunk the fact actually appears in? A true fact attributed to the \
wrong source is NOT SUPPORTED.
Mark each claim SUPPORTED or NOT SUPPORTED with a brief reason.

Exception: an ANSWER is only covered by the honest-refusal exception if refusing is ALL \
it does - stating the CONTEXT lacks the information, with nothing else. The moment the \
ANSWER supplies any actual value, number, or fact beyond that refusal - even something \
true, even something as basic as general knowledge like "1+1 is 2" - it no longer \
qualifies for this exception, and that added claim must be checked against the CONTEXT \
like any other claim in Step 2, where it will fail as NOT SUPPORTED since the CONTEXT \
doesn't contain it. "Answered honestly that the context lacks X, then answered anyway \
using outside knowledge" is NOT a pass - it is exactly the kind of unsupported claim \
this check exists to catch, regardless of how obviously true that outside fact is.

Worked example of check (c), since this one is easy to gloss over: if CONTEXT contains \
[data/report.pdf#0] "Expenses were flat due to stable headcount" and [data/notes.txt#0] \
"Revenue grew 10%", and the ANSWER says "According to the text file, expenses were flat \
due to stable headcount" - the fact itself is real, but it is attributed to the wrong \
source (that sentence is in the pdf, not the txt file). This claim is NOT SUPPORTED, \
even though every word of the underlying fact is accurate.

Step 3 - The ANSWER is GROUNDED only if every claim from Step 1 was marked SUPPORTED \
in Step 2. One NOT SUPPORTED claim makes the whole ANSWER NOT_GROUNDED, even if every \
other claim was correct.

Respond in exactly this format, nothing else:
CLAIMS: your numbered list from Step 1, each with SUPPORTED or NOT SUPPORTED and why
REASON: one sentence summarizing your overall judgment
VERDICT: GROUNDED or NOT_GROUNDED - must directly follow from CLAIMS and REASON above"""


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
