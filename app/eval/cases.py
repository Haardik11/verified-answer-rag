"""
Hand-written test cases with ground truth verified directly against the
indexed documents (see the source files in data/), not guessed. Kept to
11 cases rather than a much larger set deliberately - each real question
can cost thousands of tokens once retries are counted, and a large batch
risks blowing through the free-tier daily quota in a single run (see
DEVLOG.md). Scale this up once quota isn't a constraint.
"""

from dataclasses import dataclass, field


@dataclass
class EvalCase:
    question: str
    should_be_answerable: bool  # True if the indexed documents actually contain the answer
    expected_keywords: list[str] = field(default_factory=list)  # only used when should_be_answerable=True


CASES: list[EvalCase] = [
    # Answerable - the documents genuinely contain these facts.
    EvalCase("What was Q3 revenue?", True, ["4.2 million"]),
    EvalCase("What is driving the operating expenses this quarter?", True, ["headcount"]),
    EvalCase("Was there a security incident this quarter?", True, ["40 minutes"]),
    EvalCase("What was the enterprise revenue growth percentage?", True, ["22 percent"]),
    EvalCase("How much was cloud infrastructure spend this quarter?", True, ["340,000"]),
    EvalCase("What was net revenue retention this quarter?", True, ["108 percent"]),
    EvalCase("How many total employees does the company have?", True, ["142"]),
    # Not answerable - either genuinely absent from the documents, or general knowledge
    # unrelated to them. A correct system refuses or routes to general knowledge here,
    # not fabricates a confident document-grounded answer.
    EvalCase("What was Q2 revenue?", False),
    EvalCase("What is 1+1?", False),
    EvalCase("How many trophies has CSK won?", False),
    EvalCase("What is the company's current stock price?", False),
]
