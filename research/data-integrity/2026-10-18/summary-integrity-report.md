# Meeting summary and recent-ingestion repair

## Confirmed live problem

Six meetings have transcripts but no summary, agenda items, motions or documents. These are failed enrichment jobs, not an ordinary processing backlog.

| Meeting | Date | Source inventory ID | Transcript rows | Failed ingest job |
|---|---|---|---:|---|
| 394 Regular Council | 2026-07-20 | 353 | 2,044 | 759 |
| 393 Advisory Committee | 2026-07-28 | 352 | 373 | 758 |
| 392 Special Council | 2026-08-17 | 351 | 1,205 | 757 |
| 391 Regular Council | 2026-09-08 | 348 | 2,186 | 756 |
| 390 Regular Council | 2026-09-21 | 347 | 1,579 | 755 |
| 389 Special Council | 2026-09-28 | 346 | 1,517 | 754 |

All six jobs failed on October 1 at PDF agenda extraction (`No agenda PDFs found`). All six source inventory rows nevertheless read `ingested`. Source discovery correctly retained agenda/minute URLs, but no official documents were present locally. Current requests to those PDF URLs return HTTP403 and an eSCRIBE “Verifying your browser” page. Equivalent public official HTML agendas and minutes return HTTP200 and contain substantive meeting records.

`recovered-summary-sources.json` records original URL, saved local path, byte count and SHA256 for all12 recovered official pages. No existing files were overwritten. `missing-summary-meetings.json` is the pre-repair meeting-row snapshot.

## Durable changes

- eSCRIBE PDF downloads must have a PDF signature and complete successfully before they become reusable archive files. Interrupted downloads and HTTP200 HTML error pages cannot poison retries.
- Invalid existing PDFs, including legacy interrupted files with a PDF header but unreadable content, are quarantined under a non-PDF suffix with original bytes preserved.
- A cover sheet cannot stand in for a full agenda. When the PDF is unavailable, the scraper tries official HTML links from the source meeting record, validates eSCRIBE agenda-header/item structure, saves source URL and content hash, and preserves the same Agenda/Minutes archive layout.
- Worker ingestion stops early if an advertised official document category remains absent. It cannot report download success based solely on unrelated files. Targeted ingestion now propagates persistence/refinement failures; an existing public meeting ID is insufficient for job success. The worker verifies a persisted summary and downloaded source flags before completion, while permitting legitimate planned agenda-only cached skips. Newly available minutes trigger fresh decision extraction without replacing existing transcripts.
- Official HTML documents are ingested into `documents` with full text, URL and file hash. PDF attachment extraction skips HTML and explicitly reports `html_only_agenda` plus `incomplete_attachment_extraction=true`; source status is not promoted to `extracted`.
- Both full-refinement and summary-regeneration prompts now request a plain-text paragraph beginning with an outcome, without repeating the adjacent meeting title/date. Legacy Markdown is normalized at both fresh and cached ingestion boundaries.
- Full refinement formerly silently cut agenda at15,000 characters and minutes at20,000 characters. Standalone summaries cut minutes at25,000. These limits could exclude late decisions. Official documents now remain complete; only the auxiliary transcript excerpt in standalone summaries is bounded.
- Document refresh and transcript replacement now have separate intent. Regular worker `force` defaults to false; new documents can refresh metadata without deleting/reinserting existing corrected acoustic records. Replacement requires explicit `replace_transcript` or a freshly diarized recording.
- `regenerate_meeting_summary(..., dry_run=True)` returns a reviewable proposal without changing Supabase or refinement files.

## Repair workload and safeguards

Mechanical formatting repairs were applied and independently verified for267 existing summaries (266 contain explicit bullet lines). This required no model calls; all267 matching local refinement caches were synchronized. `summary-format-proposals.json` retains exact before/after values; the apply script uses an old-value guard, writes a rollback journal, and syncs a local refinement cache only when its summary matches the old value.

Six new summary proposals were generated with the configured `gpt-5-mini` text model. July20 was regenerated once after identifying the old minutes truncation. The specifically reported repeated-title example, meeting50, was separately regenerated once and applied with an old-value guard; exact first/second/third-reading wording was checked against its official minutes. In total this used eight standalone summary requests, plus six structured requests. A further six structured extractions use official agendas/minutes only, with no transcript sent to the model. No audio download, ASR, diarization, broad embedding run, or historical re-ingestion is required. API usage is not returned by the existing text-provider wrapper, so no exact billing amount is claimed.

Prepared six-meeting ingestion uses precomputed structured refinements and reviewed summary prose with `force_update=False`. It requires existing agenda/motion/document counts to remain zero, snapshots meeting and transcript evidence before writes, and compares ordered transcript IDs/person assignments/times/text/verification fields afterward. Full acoustic attribution is preserved. The controlled application completed all six meetings. It restored137 agenda items,88 motions,12 official HTML documents and all six missing summaries. The strict source gate verified67 motion outcomes and held21 as pending; one individual vote had explicit source evidence. Every one of the8,904 transcript rows retained its ID, person assignment, timing, text and verification state. Per-meeting receipts and independent query results are in `six-meeting-applied.json` and `six-meeting-verification.json`.

Attachment packet extraction remains incomplete because PDF downloads are browser-protected. Recovering the official HTML decision records does not manufacture unavailable PDF attachment sections or images. Historical failed queue jobs should remain audit records; any repair job/result should clearly identify this remaining limitation.

## Validation

- Focused AI-refiner, eSCRIBE downloader and public attachment-fallback suite:35 tests passed before the final transcript-preservation extension. The expanded49-contract owner suite passed, followed by all8 PDF-validation cases after strengthening cached-file validation. The final21-test worker/orchestrator/ingestion subset passed, including error propagation, legitimate cached planned skips, missing-source refusal and newly published minutes. Seven selected regressions fail against HEAD for the intended baseline defects (run through in-memory module loading, without modifying the shared checkout).
- New regressions fail on the HEAD implementation for Markdown storage, invalid/empty PDF admission, interrupted download reuse, and missing official HTML recovery.
- Long official-document prompt contract now checks the last agenda item and final decision beyond the old truncation limits.
- All12 recovered HTML pages pass the source-structure validation.
- Final live application results are recorded in `summary-format-applied.json` and, after controlled ingestion, `six-meeting-applied.json`.

## Ownership update after user clarification

The six-meeting source/structured-data/transcript repair above remains verified. Summary prose-format receipts describe an earlier intermediate state only. The user subsequently confirmed a separate agent intentionally owns a new summary prompt and bulk regeneration using canonical Markdown bullets. That producer code and its newer summary contents are preserved. Our superseded 168-summary restoration was fully reversed by exact-value comparisons; 261 matching cache summaries were restored and 12 later cache changes preserved. See `SUMMARY_CODE_OWNERSHIP.md` and `summary-restoration-undone.json`. No further summary prompt, format or content changes belong to this lane.

Final relevant owner checks passed 73 tests, including the other agent's bullet-format contract. The durable official-source recovery, target-job failure propagation, document refresh and transcript-preservation changes remain in place independently of summary presentation.
