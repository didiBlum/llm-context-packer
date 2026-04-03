"""Extract markdown from PDF content."""

from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

MAX_PDF_BYTES = 10 * 1024 * 1024  # 10MB


def extract_pdf_to_markdown(pdf_bytes: bytes) -> str:
    """Convert PDF bytes to markdown using pymupdf4llm."""
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise ValueError(f"PDF too large: {len(pdf_bytes)} bytes (max {MAX_PDF_BYTES})")

    import pymupdf4llm
    import pymupdf

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        md_text = pymupdf4llm.to_markdown(doc)
    finally:
        doc.close()

    return md_text
