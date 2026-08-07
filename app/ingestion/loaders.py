"""
Loaders turn a file on disk into plain text. This is intentionally the
simplest possible version: one function per format, one dispatcher.

We'll extend load_document() later with a real router (detects scanned
pages / charts and sends them to a vision model instead of this text path)
but starting simple lets us get a working RAG loop end to end first.
"""

from pathlib import Path
from pypdf import PdfReader


def load_pdf(path: str) -> str:
    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


def load_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def load_document(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return load_pdf(path)
    elif ext in (".txt", ".md"):
        return load_text(path)
    else:
        raise ValueError(f"No loader yet for '{ext}' files - we'll add more as we go")
