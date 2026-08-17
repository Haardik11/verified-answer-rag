"""
Scores one agent run against an EvalCase's ground truth. "Hallucinated"
here means: a confident, document-grounded claim that either contradicts
or isn't backed by what the documents actually say - a false refusal on
an answerable question also counts, since that's a different failure
mode (unhelpful) but still means the system's stated confidence didn't
match reality.

Text is normalized (see app/text_utils.py) before any comparison - found
necessary after a real eval run where a model's "smart" typography
(narrow spaces, curly apostrophes) caused answers that plainly contained
the right facts to be scored as missing them. The refusal check is
recomputed fresh from the normalized answer text rather than trusting a
stored is_refusal flag, so previously-collected answers can be re-scored
correctly without spending more tokens re-answering them.
"""

from dataclasses import dataclass

from app.agent.graph import REFUSAL_PREFIX, AgentState
from app.eval.cases import EvalCase
from app.text_utils import normalize_text


@dataclass
class EvalResult:
    case: EvalCase
    answer: str
    route_type: str
    is_refusal: bool
    grounded: bool
    attempts: int
    hallucinated: bool
    failure_reason: str


def score_case(case: EvalCase, agent_result: AgentState) -> EvalResult:
    normalized_answer = normalize_text(agent_result["answer"]).strip().lower()
    is_refusal = normalized_answer.startswith(REFUSAL_PREFIX)
    failure_reason = ""

    if not case.should_be_answerable:
        avoided_false_claim = is_refusal or agent_result["route_type"] != "document"
        hallucinated = not avoided_false_claim
        if hallucinated:
            failure_reason = "Gave a confident document-grounded answer to a question the documents don't answer."
    else:
        if is_refusal:
            hallucinated = True
            failure_reason = "Refused to answer a question the documents actually do contain."
        else:
            missing = [kw for kw in case.expected_keywords if normalize_text(kw.lower()) not in normalized_answer]
            hallucinated = len(missing) > 0
            if hallucinated:
                failure_reason = f"Missing expected fact(s): {missing}"

    return EvalResult(
        case=case,
        answer=agent_result["answer"],
        route_type=agent_result["route_type"],
        is_refusal=is_refusal,
        grounded=agent_result["grounded"],
        attempts=agent_result["attempts"],
        hallucinated=hallucinated,
        failure_reason=failure_reason,
    )
