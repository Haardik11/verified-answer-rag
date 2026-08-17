"""
Hand-written test cases with ground truth verified directly against the
indexed documents (see the source files in data/), not guessed or
LLM-generated without checking. Organized into categories that each stress
a different part of the pipeline, rather than one flat list of similar
lookups - a system that aces simple lookups can still fail badly on
paraphrased or multi-hop questions, so reporting hallucination rate per
category is far more informative than one aggregate number.

Kept to ~39 cases rather than 100+: each question can cost thousands of
tokens once retries are counted, and this project runs on a free-tier
daily token quota (see DEVLOG.md) - 30-40 varied cases is large enough to
report a credible percentage from, small enough to actually run.
"""

from dataclasses import dataclass, field


@dataclass
class EvalCase:
    question: str
    category: str  # "simple_lookup" | "paraphrased" | "multi_hop" | "unanswerable" | "exact_figure"
    should_be_answerable: bool
    expected_keywords: list[str] = field(default_factory=list)  # ALL must appear if should_be_answerable=True


CASES: list[EvalCase] = [
    # --- Simple lookups (~15): answer sits directly in one chunk, phrased close to the source. ---
    EvalCase("What was Q3 revenue?", "simple_lookup", True, ["4.2 million"]),
    EvalCase("What is driving the operating expenses this quarter?", "simple_lookup", True, ["headcount"]),
    EvalCase("Was there a security incident this quarter?", "simple_lookup", True, ["40 minutes"]),
    EvalCase("What was the enterprise revenue growth percentage?", "simple_lookup", True, ["22 percent"]),
    EvalCase("How much was cloud infrastructure spend this quarter?", "simple_lookup", True, ["340,000"]),
    EvalCase("What was net revenue retention this quarter?", "simple_lookup", True, ["108"]),
    EvalCase("How many total employees does the company have?", "simple_lookup", True, ["142"]),
    EvalCase("What was SMB revenue this quarter?", "simple_lookup", True, ["1.3 million"]),
    EvalCase("What was self-serve revenue this quarter?", "simple_lookup", True, ["800,000"]),
    EvalCase("What was the cost of goods sold?", "simple_lookup", True, ["620,000"]),
    EvalCase("What was research and development spend?", "simple_lookup", True, ["740,000"]),
    EvalCase("What was the net promoter score?", "simple_lookup", True, ["42"]),
    EvalCase("How much cash did the company have at quarter end?", "simple_lookup", True, ["18.4 million"]),
    EvalCase("What was the core API uptime this quarter?", "simple_lookup", True, ["99.94"]),
    EvalCase("How many events does the analytics pipeline process per day?", "simple_lookup", True, ["40 million"]),
    # --- Paraphrased (~10): same facts as above, worded nothing like the source text. ---
    EvalCase("How much money did the company make in Q3?", "paraphrased", True, ["4.2 million"]),
    EvalCase("Why did expenses stay flat this quarter?", "paraphrased", True, ["headcount"]),
    EvalCase("Did anything go wrong security-wise recently?", "paraphrased", True, ["40 minutes"]),
    EvalCase("How big is the engineering team?", "paraphrased", True, ["58"]),
    EvalCase("How's the company's cash position looking?", "paraphrased", True, ["18.4 million"]),
    EvalCase("Is the platform reliable?", "paraphrased", True, ["99.94"]),
    EvalCase("How satisfied are customers, based on survey data?", "paraphrased", True, ["42"]),
    EvalCase("What's new with the product this quarter?", "paraphrased", True, ["analytics dashboard"]),
    EvalCase("Are there any tech debt concerns?", "paraphrased", True, ["authentication"]),
    EvalCase("How's customer retention trending?", "paraphrased", True, ["108"]),
    # --- Multi-hop (~5): answer requires combining info from two different chunks or documents. ---
    EvalCase(
        "Why was the database migration delayed from its original Q2 target?",
        "multi_hop", True, ["replication", "visa"],
    ),
    EvalCase("Do the two Q3 financial reports agree on total revenue?", "multi_hop", True, ["4.2 million"]),
    EvalCase(
        "Is engineering headcount consistent between the business review and the infrastructure report?",
        "multi_hop", True, ["58"],
    ),
    EvalCase(
        "How does the new analytics feature relate to the rise in cloud infrastructure costs?",
        "multi_hop", True, ["analytics"],
    ),
    EvalCase(
        "Do the operating expense figures match between the financial summary and the business review?",
        "multi_hop", True, ["2.1 million"],
    ),
    # --- Unanswerable / adversarial (~6): genuinely absent from the documents. The system
    # should refuse or route to general knowledge, never confidently invent an answer. ---
    EvalCase("What was Q2 revenue?", "unanswerable", False),
    EvalCase("What is 1+1?", "unanswerable", False),
    EvalCase("How many trophies has CSK won?", "unanswerable", False),
    EvalCase("What is the company's current stock price?", "unanswerable", False),
    EvalCase("Who is the CEO of the company?", "unanswerable", False),
    EvalCase("What was the company's revenue two years ago?", "unanswerable", False),
    # --- Exact figure (~3): a specific number/date, testing whether BM25 keyword
    # matching earns its place over dense-only retrieval. ---
    EvalCase("What month did the security incident occur?", "exact_figure", True, ["september"]),
    EvalCase(
        "How many enterprise customers participated in the analytics dashboard beta?",
        "exact_figure", True, ["40"],
    ),
    EvalCase(
        "What was the average enterprise contract value after the price increase?",
        "exact_figure", True, ["168,000"],
    ),
]
