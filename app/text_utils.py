"""
Normalizes "smart" typography (narrow/non-breaking spaces, curly quotes,
special hyphens/dashes) to plain ASCII equivalents. Needed because exact-
string checks - refusal detection, eval keyword matching - would
otherwise silently fail to match text a human reader would consider
identical: found via a real eval run where openai/gpt-oss-120b's answers
used a narrow no-break space in numbers ("1.3 million") and a curly
apostrophe in "don't", breaking substring/prefix checks that assumed
plain ASCII punctuation.
"""

_REPLACEMENTS = {
    " ": " ",  # narrow no-break space
    " ": " ",  # non-breaking space
    "‘": "'",  # left single quote
    "’": "'",  # right single quote / apostrophe
    "“": '"',  # left double quote
    "”": '"',  # right double quote
    "‑": "-",  # non-breaking hyphen
    "–": "-",  # en dash
    "—": "-",  # em dash
}


def normalize_text(text: str) -> str:
    for special, plain in _REPLACEMENTS.items():
        text = text.replace(special, plain)
    return text
