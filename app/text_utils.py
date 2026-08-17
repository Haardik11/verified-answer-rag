"""
Maps "smart" typography (narrow/non-breaking spaces, curly quotes,
special hyphens/dashes) back to plain ASCII. I needed this because my
exact-string checks (refusal detection, eval keyword matching) were
silently failing on text a human wouldn't even notice was different -
turned out openai/gpt-oss-120b writes numbers with a narrow no-break
space ("1.3 million") and a curly apostrophe in "don't", both of which
broke checks I'd written assuming plain ASCII punctuation.

Using escape sequences for the special characters below on purpose, not
the literal characters - they're invisible in an editor, and a copy/paste
or encoding hiccup can silently corrupt them into something else (which
is exactly what happened once while editing this file - two different
space characters got collapsed into one literal ASCII space, quietly
breaking the fix this file exists for). Escapes make that mistake
impossible to make silently again.
"""

_REPLACEMENTS = {
    " ": " ",  # narrow no-break space
    " ": " ",  # non-breaking space
    "‘": "'",  # left single quote
    "’": "'",  # right single quote / apostrophe
    '“': '"',  # left double quote
    '”': '"',  # right double quote
    "‑": "-",  # non-breaking hyphen
    "–": "-",  # en dash
    "—": "-",  # em dash
}


def normalize_text(text: str) -> str:
    for special, plain in _REPLACEMENTS.items():
        text = text.replace(special, plain)
    return text
