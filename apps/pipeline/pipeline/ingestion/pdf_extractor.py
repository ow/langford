"""
Two-pass document extraction from agenda PDFs (provider PDF reading).

Pass 1 (boundary detection): Send the agenda PDF, get structured document
boundaries, types, agenda item links, summaries, and key facts.

Pass 2 (content extraction): For each document boundary, extract clean
structured markdown content for those pages.

Local text packages (``local_context_extractor``) are tried first; this is
the fallback for PDFs whose local text is missing or weak.
"""

import logging
import os
from typing import Literal

from pydantic import BaseModel

from pipeline import ai

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────

MAX_PDF_MB = 50  # Provider limit for one inline PDF; larger files are split


# ── Schema ───────────────────────────────────────────────────────────────

DocumentType = Literal[
    "agenda", "minutes", "staff_report", "delegation", "correspondence",
    "appendix", "bylaw", "presentation", "form", "other",
]


class DocumentBoundary(BaseModel):
    title: str
    page_start: int
    page_end: int
    type: DocumentType
    agenda_item: str | None
    summary: str
    key_facts: list[str]


class DocumentBoundaries(BaseModel):
    documents: list[DocumentBoundary]


def boundaries_from_result(result: DocumentBoundaries) -> list[dict]:
    """Plain dicts (the shape extraction consumers store), dropping impossible ranges."""
    out = []
    for doc in result.documents:
        if doc.page_start < 1 or doc.page_end < doc.page_start:
            logger.warning("Dropping boundary '%s' with bad page range %d-%d", doc.title, doc.page_start, doc.page_end)
            continue
        out.append(doc.model_dump())
    return out


# ── Prompts ──────────────────────────────────────────────────────────────

BOUNDARY_PROMPT = """You are analyzing a municipal council meeting agenda package PDF.
This PDF contains a table of contents/agenda listing at the start, followed by the actual
documents referenced by the agenda (staff reports, delegations, correspondence, minutes, etc.).

Your task: Identify every distinct document in this PDF and return one entry in `documents` for each:

{
  "title": "Document title/heading as it appears",
  "page_start": 1,
  "page_end": 5,
  "type": "staff_report",
  "agenda_item": "6.1a",
  "summary": "1-2 sentence summary of what this document is about",
  "key_facts": ["dollar amounts", "addresses", "dates", "decisions"]
}

Guidelines:
- type: one of agenda, minutes, staff_report, delegation, correspondence, appendix, bylaw, presentation, form, other
- agenda_item: the agenda item number this document relates to (from the TOC/agenda pages), or null
- Be precise about page boundaries — where does each document start and end?
- CRITICAL: Page ranges MUST NOT overlap. Every page belongs to exactly one document. Do NOT create a parent entry spanning pages 4-22 AND separate child entries within that range. Choose the most specific/granular boundaries.
- Each distinct document should be its own entry (don't merge separate staff reports)
- The agenda/TOC pages at the start count as one "agenda" type document
- Delegation request forms should be type "form"
- key_facts: capture dollar amounts, addresses, dates, specific decisions/recommendations
- If a staff report spans pages 4-11 and has attached appendices on pages 12-15, the staff report is pages 4-11 and each appendix is a separate entry"""

CONTENT_PROMPT_TEMPLATE = """Extract the full content of the document on pages {page_start} to {page_end} from this PDF.

Output clean, well-structured markdown:
- Use ## for main headings, ### for sub-headings
- Render tables as markdown tables
- Preserve numbered/bulleted lists
- Include staff recommendations verbatim
- Skip headers/footers, page numbers, and watermarks
- Skip any images but note where they appear as [Image: brief description]
- Preserve all dollar amounts, dates, addresses, and bylaw numbers exactly

Return ONLY the markdown content, no commentary."""

# Image-numbering instructions, appended to local-package content prompts when
# locally extracted images are available.
CONTENT_WITH_IMAGES_PROMPT = """Extract the full content of the document on pages {page_start} to {page_end} from this PDF.

I have provided {n_images} extracted images from these pages, numbered Image 1 through Image {n_images}.

Output clean, well-structured markdown:
- Use ## for main headings, ### for sub-headings
- Render tables as markdown tables
- Preserve numbered/bulleted lists
- Include staff recommendations verbatim
- Skip headers/footers, page numbers, and watermarks
- Where an image appears in the document, insert [Image N: brief description] matching the numbered image
- Reference EVERY meaningful image (maps, charts, diagrams, photos, renderings)
- Do NOT reference logos, signatures, letterheads, headers/footers, crests, watermarks, stamps, or seals
- If multiple images form a collage or visual group, reference each one individually at the location where the group appears
- Preserve all dollar amounts, dates, addresses, and bylaw numbers exactly

Return ONLY the markdown content, no commentary."""


# ── Helper: split large PDFs ────────────────────────────────────────────

def _split_large_pdf(pdf_path: str, max_pages: int = 500) -> list[tuple[str, int]]:
    """Split a PDF into chunks that each stay under MAX_PDF_MB.

    Includes the first 4 pages (agenda/TOC) in every chunk so the model can
    always reference agenda items.

    Uses adaptive chunking: starts with estimated page count, validates
    actual file size, and halves if a chunk exceeds the limit (PDF shared
    resources make file size unpredictable from page count alone).

    Returns list of (temp_file_path, page_offset) tuples.
    The caller is responsible for cleaning up temp files.
    """
    import tempfile

    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error("PyMuPDF (fitz) required for splitting large PDFs")
        return []

    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    # Estimate initial chunk size from average MB/page
    file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
    if file_size_mb > MAX_PDF_MB and total_pages > 0:
        bytes_per_page = file_size_mb / total_pages
        # Target 30% of limit — very conservative because PDF shared
        # resources (fonts, images) inflate extracted chunks unpredictably
        target_mb = MAX_PDF_MB * 0.3
        size_based_max = max(5, int(target_mb / bytes_per_page))
        if size_based_max < max_pages:
            logger.info(
                "PDF is %.1fMB (%.1fMB/page avg) — targeting %d pages/chunk",
                file_size_mb, bytes_per_page, size_based_max,
            )
            max_pages = size_based_max

    if total_pages <= max_pages and file_size_mb <= MAX_PDF_MB:
        doc.close()
        return [(pdf_path, 0)]

    overlap_pages = min(4, total_pages)
    chunks = []

    chunk_start = overlap_pages
    while chunk_start < total_pages:
        # Try creating a chunk, validate size, halve if too large
        pages_to_take = min(max_pages - overlap_pages, total_pages - chunk_start)
        chunk_path = None

        while pages_to_take >= 5:
            chunk_end = chunk_start + pages_to_take

            new_doc = fitz.open()
            new_doc.insert_pdf(doc, from_page=0, to_page=overlap_pages - 1)
            new_doc.insert_pdf(doc, from_page=chunk_start, to_page=chunk_end - 1)

            # Downsample images to 72 DPI — the model only needs text readability
            try:
                new_doc.rewrite_images(dpi=72)
            except Exception:
                pass  # Some PDFs may not support this; continue anyway

            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            new_doc.ez_save(tmp.name)
            new_doc.close()
            tmp.close()

            chunk_mb = os.path.getsize(tmp.name) / (1024 * 1024)

            if chunk_mb <= MAX_PDF_MB:
                chunk_path = tmp.name
                logger.info(
                    "  Chunk: pages %d-%d → %.1fMB (%d pages + %d overlap)",
                    chunk_start + 1, chunk_end, chunk_mb,
                    pages_to_take, overlap_pages,
                )
                break
            else:
                # Too large — clean up and try fewer pages
                os.unlink(tmp.name)
                old_count = pages_to_take
                pages_to_take = pages_to_take // 2
                logger.info(
                    "  Chunk too large (%.1fMB) — reducing from %d to %d pages",
                    chunk_mb, old_count, pages_to_take,
                )

        if chunk_path:
            chunks.append((chunk_path, chunk_start))
            chunk_start += pages_to_take
        else:
            # Could not create a small enough chunk — skip these pages
            logger.warning(
                "  Skipping pages %d-%d: cannot reduce below 50MB",
                chunk_start + 1, chunk_start + pages_to_take,
            )
            chunk_start += pages_to_take

    doc.close()
    logger.info("Split into %d chunks", len(chunks))
    return chunks


def _extract_page_range_file(pdf_path: str, page_start: int, page_end: int) -> str | None:
    """Extract a page range from a PDF into a temp PDF file.

    The caller is responsible for deleting the returned temp file.
    """
    import tempfile

    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error("PyMuPDF required for page extraction")
        return None

    try:
        doc = fitz.open(pdf_path)
        new_doc = fitz.open()
        new_doc.insert_pdf(doc, from_page=page_start - 1, to_page=page_end - 1)

        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        new_doc.save(tmp.name)
        new_doc.close()
        doc.close()
        tmp.close()
        return tmp.name
    except Exception as e:
        logger.error("Failed to extract pages %d-%d: %s", page_start, page_end, e)
        return None


# ── Helper: merge boundaries from chunked PDFs ──────────────────────────

def _merge_chunk_boundaries(
    all_chunk_results: list[tuple[list[dict], int]],
    overlap_pages: int = 4,
) -> list[dict]:
    """Merge boundary results from multiple PDF chunks.

    Adjusts page numbers based on the chunk's page_offset and removes
    duplicates from the overlap pages.
    """
    merged = []
    seen_titles = set()

    for boundaries, page_offset in all_chunk_results:
        for entry in boundaries:
            # Entries from the overlap pages (1-4) — only keep from first chunk
            original_start = entry.get("page_start", 0)
            original_end = entry.get("page_end", 0)

            if page_offset > 0 and original_start <= overlap_pages:
                # This is a duplicate from the overlap — skip
                continue

            if page_offset > 0:
                # Adjust page numbers: subtract overlap pages, add offset
                entry["page_start"] = original_start - overlap_pages + page_offset
                entry["page_end"] = original_end - overlap_pages + page_offset

            # Deduplicate by title + page range
            key = f"{entry.get('title', '')}|{entry['page_start']}"
            if key not in seen_titles:
                seen_titles.add(key)
                merged.append(entry)

    # Sort by page_start
    merged.sort(key=lambda x: x.get("page_start", 0))
    return _dedup_overlapping_boundaries(merged)


def _dedup_overlapping_boundaries(boundaries: list[dict]) -> list[dict]:
    """Remove boundaries that are fully contained within other boundaries.

    When the model detects both a parent document (p4-22) and sub-documents
    within it (p4-11, p12, p13-19), keep the more granular children and
    drop the parent.
    """
    if len(boundaries) <= 1:
        return boundaries

    sorted_bounds = sorted(boundaries, key=lambda x: (x.get("page_start", 0), -x.get("page_end", 0)))
    to_remove = set()

    for i, parent in enumerate(sorted_bounds):
        if i in to_remove:
            continue
        p_start = parent.get("page_start", 0)
        p_end = parent.get("page_end", 0)
        span = p_end - p_start

        # Single-page entries can't contain children
        if span < 1:
            continue

        # Check if this parent fully contains any other entries
        children = []
        for j, child in enumerate(sorted_bounds):
            if i == j or j in to_remove:
                continue
            c_start = child.get("page_start", 0)
            c_end = child.get("page_end", 0)
            if c_start >= p_start and c_end <= p_end and (c_start, c_end) != (p_start, p_end):
                children.append(j)

        # If this parent contains any children, remove the parent
        if len(children) >= 1:
            to_remove.add(i)
            logger.debug(
                "Removing parent boundary '%s' p%d-%d (contains %d children)",
                parent.get("title", "?")[:50], p_start, p_end, len(children),
            )

    result = [b for i, b in enumerate(sorted_bounds) if i not in to_remove]
    if to_remove:
        logger.info(
            "Deduped %d overlapping parent boundaries (kept %d)",
            len(to_remove), len(result),
        )
    return result


# ── Provider calls ───────────────────────────────────────────────────────


def _pdf_boundaries(pdf_path: str) -> list[dict]:
    result = ai.pdf(pdf_path, BOUNDARY_PROMPT, stage="document", schema=DocumentBoundaries)
    return boundaries_from_result(result)


# ══════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════


def detect_boundaries(pdf_path: str) -> list[dict]:
    """Pass 1: Send the agenda PDF to the document model.

    For PDFs > MAX_PDF_MB, splits into chunks and merges results.
    Raises ai.AIError when the provider call fails.

    Returns list of dicts with keys:
        title, page_start, page_end, type, agenda_item, summary, key_facts
    """
    file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)

    logger.info("Detecting boundaries in %s (%.1fMB)", os.path.basename(pdf_path), file_size_mb)

    if file_size_mb > MAX_PDF_MB:
        logger.info("PDF exceeds %dMB — splitting for boundary detection", MAX_PDF_MB)
        chunks = _split_large_pdf(pdf_path)
        if not chunks:
            return []

        all_results = []
        try:
            for chunk_path, page_offset in chunks:
                all_results.append((_pdf_boundaries(chunk_path), page_offset))
        finally:
            for chunk_path, _ in chunks:
                if chunk_path != pdf_path:
                    try:
                        os.unlink(chunk_path)
                    except OSError:
                        pass

        return _merge_chunk_boundaries(all_results)

    return _dedup_overlapping_boundaries(_pdf_boundaries(pdf_path))


def extract_content(
    pdf_path: str,
    page_start: int,
    page_end: int,
    doc_title: str = "",
    images: list[dict] | None = None,
) -> str:
    """Pass 2: Extract clean markdown content for a page range from the PDF.

    Sends the full PDF (or, for PDFs over 5MB, just the page range) with a
    page-specific prompt. ``images`` is accepted for interface parity with the
    local-package path; images are not sent to the provider here.
    Raises ai.AIError when the provider call fails.
    """
    logger.info(
        "Extracting content: '%s' (pages %d-%d, %d images)",
        doc_title[:50] if doc_title else "untitled",
        page_start,
        page_end,
        len(images) if images else 0,
    )

    file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)

    # For PDFs over 5MB, extract just the needed pages — avoids uploading
    # a 50MB PDF 45 times for 45 different page ranges.
    if file_size_mb > 5:
        extracted_path = _extract_page_range_file(pdf_path, page_start, page_end)
        if extracted_path is None:
            logger.error("Cannot extract pages %d-%d from PDF", page_start, page_end)
            return ""
        effective_start = 1
        effective_end = page_end - page_start + 1
        pdf_for_request = extracted_path
    else:
        effective_start = page_start
        effective_end = page_end
        pdf_for_request = pdf_path

    try:
        prompt = CONTENT_PROMPT_TEMPLATE.format(page_start=effective_start, page_end=effective_end)
        text = ai.pdf(pdf_for_request, prompt, stage="document")
    finally:
        if pdf_for_request != pdf_path:
            try:
                os.unlink(pdf_for_request)
            except OSError:
                pass

    return text.strip() if text else ""
