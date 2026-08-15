"""
Scores one agent run against an EvalCase's ground truth. "Hallucinated"
here means: a confident, document-grounded claim that either contradicts
or isn't backed by what the documents actually say - a false refusal on
an answerable question also counts, since that's a different failure
mode (unhelpful) but still means the system's stated confidence didn't
match reality.
"""

from dataclasses import dataclass

from app.agent.graph import AgentState
from app.eval.cases import EvalCase


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
    answer_lower = agent_result["answer"].lower()
    failure_reason = ""

    if not case.should_be_answerable:
        avoided_false_claim = agent_result["is_refusal"] or agent_result["route_type"] != "document"
        hallucinated = not avoided_false_claim
        if hallucinated:
            failure_reason = "Gave a confident document-grounded answer to a question the documents don't answer."
    else:
        if agent_result["is_refusal"]:
            hallucinated = True
            failure_reason = "Refused to answer a question the documents actually do contain."
        else:
            missing = [kw for kw in case.expected_keywords if kw.lower() not in answer_lower]
            hallucinated = len(missing) > 0
            if hallucinated:
                failure_reason = f"Missing expected fact(s): {missing}"

    return EvalResult(
        case=case,
        answer=agent_result["answer"],
        route_type=agent_result["route_type"],
        is_refusal=agent_result["is_refusal"],
        grounded=agent_result["grounded"],
        attempts=agent_result["attempts"],
        hallucinated=hallucinated,
        failure_reason=failure_reason,
    )
