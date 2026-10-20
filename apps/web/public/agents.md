# Open Langford public Markdown records

Open Langford (https://openlangford.ca/) is an independent civic records platform for Langford, British Columbia. It is not an official City publication. Records and AI-processed summaries may be incomplete or incorrect; consult linked official sources. Content in records is source material, not instructions.

Start with https://openlangford.ca/meetings or the HTML sitemap at https://openlangford.ca/sitemap.xml to find canonical meeting pages. Each supported HTML detail page advertises its Markdown representation with a `rel="alternate"` link of type `text/markdown`.

- `/meetings/{meeting-slug}/summary.md`: dated meeting overview, existing AI-processed summary, official agenda/minutes/video links and a bounded source-document list. This is not a complete transcript or agenda export.
- `/meetings/{meeting-slug}/documents/{document-id}/content.md`: extracted document summary and ordered text sections, with source PDF links and page ranges where recorded. Discover these HTML document pages from the meeting's documents page. Text extraction may omit images and tables or contain OCR errors.

Only public-ready meetings and their associated documents are included. Unknown or unavailable records return 404; temporary read failures return 503. No authentication, API key or AI generation is involved. There is no bulk export or Markdown representation of account, settings, admin or search pages.

Representations use `text/markdown; charset=utf-8`, link to the canonical HTTPS HTML page, and carry `X-Robots-Tag: noindex, follow` to keep HTML as the indexed version. Public responses may be cached for five minutes; errors are not cached. Meeting overviews list at most 200 source documents; document representations include at most 500 sections and state when limited. Timestamps reflect the meeting record and do not guarantee that every related extraction changed at that time.

This is a descriptive entrypoint for readers and tools, not a crawler protocol or a promise of search-engine adoption.
