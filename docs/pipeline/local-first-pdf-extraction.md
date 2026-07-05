# Local-First PDF Extraction

## Goal

Replace the current default "send the PDF to the model" extraction path with a local-first pipeline that preserves visual assets, lowers API cost, avoids context-window failures, and keeps the existing `extracted_documents`, `document_sections`, and `document_images` database contract.

The model should still be used for judgment: boundary decisions, section naming, summaries, and visual interpretation when needed. It should not be the first tool asked to read every byte of every PDF.

## Current Flow

`extract_and_store_documents()` currently does this for each agenda/minutes PDF:

1. Send the whole PDF to the configured AI provider for boundary detection.
2. For each detected boundary, send the PDF or page-range PDF back to the provider for Markdown content extraction.
3. Extract embedded images locally with PyMuPDF.
4. Upload images to R2.
5. Insert extracted documents, sections, and image metadata.

This works, but it is expensive and slow on large agenda packages. It can also fail when a PDF or page chunk exceeds the model context window.

## Proposed Flow

The new flow should build a local document package first:

1. Read PDF structure locally with PyMuPDF.
2. Extract per-page text locally.
3. Extract embedded images locally and upload them to R2.
4. Compute a per-page quality score.
5. Render selected pages only when local text is weak or visual context matters.
6. Ask the model to work from structured local context by default.
7. Fall back to PDF/vision requests only for pages or ranges that need it.

In short:

```text
PDF
 -> local pages/text/images/tables/quality
 -> model boundary + section decisions from structured context
 -> targeted vision/PDF fallback only where needed
 -> existing DB rows + R2 assets + embeddings
```

## Local Document Package

Create a deterministic local representation for each PDF before AI calls:

```text
document_package = {
  pdf_path,
  page_count,
  pages: [
    {
      page_number,
      width,
      height,
      text,
      text_blocks,
      image_refs,
      table_candidates,
      rendered_page_key?,
      quality
    }
  ],
  images: [
    {
      local_id,
      page_number,
      bbox,
      width,
      height,
      format,
      r2_key?,
      description?
    }
  ]
}
```

This package can be cached next to the PDF later, but the first implementation can build it in memory.

## Extraction Tools

Use PyMuPDF first:

- `page.get_text("dict")` for text blocks and rough layout.
- `page.get_images()` / `doc.extract_image()` for embedded images.
- `page.get_pixmap()` for page rendering when a visual fallback is needed.

Add `pdfplumber` only if PyMuPDF text is insufficient for table-heavy pages. It is useful, but it should not become the default dependency until we prove table extraction is a real blocker.

## Quality Scoring

Each page should get a simple quality score:

- `good_text`: enough extractable text, normal character distribution, few replacement characters.
- `sparse_text`: little text but not necessarily scanned.
- `image_dominant`: large images or rendered drawings dominate the page.
- `table_like`: many aligned short text blocks or detected ruling lines.
- `scanned_or_ocr_needed`: no useful text but page has visible content.

The first pass can use heuristics:

- text character count;
- word count;
- ratio of text area to page area;
- number and size of images;
- odd/repeated characters;
- line/block density.

## Model Responsibilities

The model should receive a compact prompt containing:

- PDF/document title;
- page count;
- page-level extracted text;
- page-level image summaries or image IDs;
- page quality flags;
- any rendered page/image attachments only for selected pages.

The model should return the same high-level outputs the current extractor expects:

- document boundaries;
- title;
- document type;
- page range;
- agenda item link;
- summary;
- key facts;
- section Markdown.

## Visual Asset Handling

Visual asset preservation remains local-first:

1. Extract all meaningful embedded images locally with existing PyMuPDF logic.
2. Upload optimized WebP images to R2.
3. Store metadata in `document_images`.
4. Link images to sections after the model has produced section boundaries.

For pages where the meaningful visual is not an embedded image, render the page or cropped page region and upload that as a visual asset too. Examples:

- scanned correspondence;
- maps/site plans embedded as page artwork;
- tables whose text extraction is unreliable;
- architectural drawings;
- renderings.

The model can be given selected image/page renderings for description, but R2 upload should not depend on model success.

## Fallback Rules

Default path:

```text
local text package -> model JSON/Markdown
```

Fallback to selected rendered pages/images when:

- page has `scanned_or_ocr_needed`;
- page is `image_dominant`;
- local text is too sparse for a boundary range;
- a section references a figure, map, drawing, or table;
- model output says local context is insufficient.

Fallback to whole-PDF provider reading should be the last resort, not the default.

## Database Compatibility

Keep the existing tables:

- `extracted_documents`
- `document_sections`
- `document_images`

The new extractor should still return:

```text
{
  boundaries_found,
  documents_extracted,
  sections_created,
  images_extracted
}
```

This keeps `Archiver.extract_documents_for_meeting()` and embedding generation mostly unchanged.

## Implementation Plan

1. Add `local_pdf_package.py`.
   - Build the per-page package with PyMuPDF.
   - Extract text blocks, images, dimensions, and quality flags.
   - Reuse existing image upload behavior where possible.

2. Add a local-context prompt path.
   - Boundary detection from page summaries/text instead of whole PDF bytes.
   - Content extraction from page text plus selected visual references.

3. Update `document_extractor.py`.
   - Keep cleanup and DB insertion logic.
   - Replace default `detect_boundaries(pdf_path)` with local-package boundary detection.
   - Replace default `extract_content(pdf_path, page_start, page_end, ...)` with local-package content extraction.
   - Keep provider PDF calls as fallback.

4. Add page rendering fallback.
   - Render only selected pages.
   - Upload rendered pages/crops to R2 with a distinct key prefix.
   - Store them as `document_images` with an `image_type` such as `page_render`.

5. Add tests around package creation and fallback routing.
   - Digital PDF with good text.
   - Image-heavy PDF.
   - Empty/scanned page.
   - Oversized agenda package that should avoid whole-PDF AI calls.

6. Add a queue flag before re-running the archive batch.
   - The remaining archive jobs should use the new extractor.
   - Optionally add `skip_diarization` so document extraction can run without audio transcription.

## Open Questions

- Should document jobs skip diarization by default for archive backfills?
- Should rendered page assets be stored in `document_images` or a new asset table?
- Do we want `pdfplumber` immediately, or should we start with PyMuPDF and add `pdfplumber` only for table failures?
- Should local extraction cache files be committed to the archive directory, or treated as regenerable cache?

## Initial Recommendation

Start with PyMuPDF only. It already exists in the project, already supports image extraction, and can produce enough page text and layout data to eliminate most whole-PDF model calls.

Add `pdfplumber` after the first implementation if tables are poor in practice. That keeps the first branch smaller and gives us a cleaner before/after test against the Langford queue.
