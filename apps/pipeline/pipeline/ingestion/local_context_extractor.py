"""Local-context document extraction.

Uses text/layout packages produced locally from PDFs as the primary AI context.
Provider PDF reads remain fallback behavior in ``gemini_extractor``.
"""

from __future__ import annotations

import logging

from pipeline.ai_provider import generate_text
from pipeline.ingestion.gemini_extractor import (
    CONTENT_WITH_IMAGES_PROMPT,
    _dedup_overlapping_boundaries,
    _parse_json_response,
)
from pipeline.ingestion.local_pdf_package import (
    PdfPackage,
    package_for_prompt,
    range_text,
)

logger = logging.getLogger(__name__)


LOCAL_BOUNDARY_PROMPT = """You are analyzing locally extracted text from a municipal council agenda/minutes PDF.

The text is grouped by page and may include quality flags such as good_text, sparse_text,
image_dominant, table_like, or scanned_or_ocr_needed. Image IDs indicate visual assets
extracted locally from that page.

Identify every distinct document in this PDF and return a JSON array. For each document:

{{
  "title": "Document title/heading as it appears",
  "page_start": 1,
  "page_end": 5,
  "type": "staff_report",
  "agenda_item": "6.1a",
  "summary": "1-2 sentence summary of what this document is about",
  "key_facts": ["dollar amounts", "addresses", "dates", "decisions"]
}}

Rules:
- type must be one of agenda, minutes, staff_report, delegation, correspondence, appendix, bylaw, presentation, form, other.
- agenda_item is the agenda item number this document relates to, or null.
- Page ranges must be precise and must not overlap.
- Prefer granular child documents over one parent that spans many attachments.
- If the PDF is a standalone agenda, minutes, or cover page, return one boundary covering the whole PDF.
- Use quality flags to avoid over-trusting weak OCR-like pages, but still return best-effort ranges.
- Return ONLY a valid JSON array, no commentary.

LOCAL PDF PACKAGE:
{package_text}
"""


LOCAL_CONTENT_PROMPT = """Convert locally extracted PDF text into clean, structured Markdown for this document.

Document title: {title}
Page range: {page_start}-{page_end}

Instructions:
- Use ## for main headings and ### for sub-headings.
- Preserve staff recommendations verbatim when present.
- Preserve dollar amounts, dates, addresses, bylaw numbers, names, and motion text exactly.
- Render table-like text as readable markdown where possible.
- Skip repeated headers, footers, page numbers, and watermarks when obvious.
- Where an image is referenced by the page package, insert [Image N: brief description] if the surrounding text makes its purpose clear.
- Do not invent facts that are not present in the local text.
- Return ONLY Markdown, no commentary.

LOCAL PAGE TEXT:
{page_text}

LOCAL PAGE/IMAGE CONTEXT:
{package_text}
"""


def detect_boundaries_from_package(package: PdfPackage) -> list[dict]:
    """Detect document boundaries from local text/page context."""
    if not package.has_usable_text:
        logger.info("Local package has insufficient text for boundary detection")
        return []

    prompt = LOCAL_BOUNDARY_PROMPT.format(
        package_text=package_for_prompt(
            package,
            max_page_chars=1600,
            max_total_chars=70000,
        )
    )
    try:
        text = generate_text(prompt, scope="document")
    except Exception as exc:
        logger.warning("Local boundary detection failed: %s", exc)
        return []
    if not text:
        return []
    return _dedup_overlapping_boundaries(_parse_json_response(text))


def extract_content_from_package(
    package: PdfPackage,
    page_start: int,
    page_end: int,
    doc_title: str = "",
    images: list[dict] | None = None,
) -> str:
    """Extract Markdown content from local page text and image context."""
    pages = package.pages_in_range(page_start, page_end)
    page_text = range_text(package, page_start, page_end)
    if not page_text:
        logger.info(
            "Local package has no page text for content pages %d-%d",
            page_start,
            page_end,
        )
        return ""

    # Very large documents are better inserted as local markdown than sent as a
    # giant prompt that recreates the old context-window problem.
    if len(page_text) > 90000:
        logger.info(
            "Local page text for '%s' is %d chars; using direct local markdown",
            doc_title[:50] if doc_title else "untitled",
            len(page_text),
        )
        return _local_markdown_fallback(doc_title, page_text, images)

    package_text = package_for_prompt(
        package,
        page_start=page_start,
        page_end=page_end,
        max_page_chars=2200,
        max_total_chars=50000,
    )
    if images:
        image_instruction = CONTENT_WITH_IMAGES_PROMPT.format(
            page_start=page_start,
            page_end=page_end,
            n_images=len(images),
        )
        package_text = f"{package_text}\n\nIMAGE INSTRUCTIONS:\n{image_instruction}"

    prompt = LOCAL_CONTENT_PROMPT.format(
        title=doc_title or "Untitled document",
        page_start=page_start,
        page_end=page_end,
        page_text=page_text,
        package_text=package_text,
    )
    try:
        text = generate_text(prompt, scope="document")
    except Exception as exc:
        logger.warning("Local content extraction failed for '%s': %s", doc_title, exc)
        return _local_markdown_fallback(doc_title, page_text, images)

    return (text or "").strip() or _local_markdown_fallback(doc_title, page_text, images)


def package_needs_pdf_fallback(
    package: PdfPackage,
    page_start: int,
    page_end: int,
) -> bool:
    """Return True when local text quality is weak for a page range."""
    pages = package.pages_in_range(page_start, page_end)
    if not pages:
        return True
    words = sum(page.quality.word_count for page in pages)
    if words < 20:
        return True
    weak_pages = [
        page
        for page in pages
        if page.quality.label in {"scanned_or_ocr_needed", "empty"}
    ]
    return bool(weak_pages) and len(weak_pages) >= max(1, len(pages) // 2)


def _local_markdown_fallback(
    doc_title: str,
    page_text: str,
    images: list[dict] | None,
) -> str:
    heading = doc_title.strip() or "Document Content"
    image_note = ""
    if images:
        image_note = "\n\n" + "\n".join(
            f"[Image {idx}: extracted visual asset on page {img.get('page', '?')}]"
            for idx, img in enumerate(images, 1)
        )
    return f"## {heading}\n\n{page_text.strip()}{image_note}".strip()
