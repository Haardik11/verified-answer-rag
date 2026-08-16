"""
Loaders turn a file on disk into plain text. This is intentionally the
simplest possible version: one function per format, one dispatcher.
"""

from pathlib import Path

import pandas as pd
import pymupdf
from pypdf import PdfReader

from app.ingestion.vision import ocr_image

# Pages with less extracted text than this are treated as scanned/image-only
# and routed to OCR instead - a real text page from these sample documents
# has hundreds of characters; a scanned page pypdf can't read returns ~0.
SCANNED_PAGE_TEXT_THRESHOLD = 20


def load_pdf(path: str) -> str:
    reader = PdfReader(path)
    fitz_doc = None  # opened lazily, only if a page actually needs OCR
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if len(text.strip()) < SCANNED_PAGE_TEXT_THRESHOLD:
            if fitz_doc is None:
                fitz_doc = pymupdf.open(path)
            image_bytes = fitz_doc[i].get_pixmap(dpi=200).tobytes("png")
            text = ocr_image(image_bytes)
        pages.append(text)
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
