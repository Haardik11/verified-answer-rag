"""
Loaders turn a file on disk into plain text. This is intentionally the
simplest possible version: one function per format, one dispatcher.

Scanned/image-only PDF pages (no extractable text layer) still need a
vision-model OCR path - that's a separate piece, not yet added here.
"""

from pathlib import Path

import pandas as pd
from pypdf import PdfReader


def load_pdf(path: str) -> str:
    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


def load_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def load_spreadsheet(path: str) -> str:
    ext = Path(path).suffix.lower()
    df = pd.read_csv(path) if ext == ".csv" else pd.read_excel(path)
    # One line per row, "column: value" pairs - readable prose for chunking/
    # embedding, rather than a raw table dump that would chunk badly.
    lines = [", ".join(f"{col}: {row[col]}" for col in df.columns) for _, row in df.iterrows()]
    return "\n".join(lines)


def load_document(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return load_pdf(path)
    elif ext in (".txt", ".md"):
        return load_text(path)
    elif ext in (".csv", ".xlsx", ".xls"):
        return load_spreadsheet(path)
    else:
        raise ValueError(f"No loader yet for '{ext}' files - we'll add more as we go")
