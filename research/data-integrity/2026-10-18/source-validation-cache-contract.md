# Source-validation cache contract (v2)

A completed source receipt may skip ingestion only when the selected source binary **and the validation inputs** still match. Legacy receipts and interrupted attempts refresh documentary facts using cached refinement; they do not purchase new AI enrichment.

The receipt records:

- A digest of the actual loaded Python function bytecode, nested constants, defaults, regexes, and rule constants across the canonical/source/ballot/policy/OCR modules. It does not hash newer Python files on disk and mislabel an old worker as using them. Restart the worker to adopt newly deployed Python code. Swift asset bytes are included because the OCR subprocess reads that asset at execution time.
- A deterministic inventory of all direct `Minutes` PDF, HTML, and URL sidecar filenames and content hashes, including unchosen candidates. Adding a second source can change selection or make it ambiguous. Inventory is checked before and after context preparation to reject a concurrent source change.
- The actual derived source text hash, selected file/URL/format, native date/classification, roster identities/unknowns, extraction errors, and OCR proof hashes/quotes. A changed extraction environment or newly available local OCR can therefore retry the same PDF. OCR cache paths are excluded.
- Actual stored catalog identity (date, title, type, organization/classification, archive path, minutes URL), person IDs/full names, Council membership roles/date bounds/classification, and the current verified policy evidence/status. Daily check timestamps and growing policy end dates are represented by whether the policy covers this meeting date; unrelated avatars, editorial summaries, update timestamps, and non-source extraction caches do not invalidate the receipt. CAC identity-section evidence is used rather than the full page hash, which changes for unrelated bios/theme content.
- Completed ballot count, held ballot count, and hold reasons, alongside the canonical mapping report. An unchanged completed attempt can skip even if some ballots remain held; changed inputs retry those holds. `in_progress` never skips.

The initial context is reused for source planning and ballot validation. After choice persistence/readback, a final no-AI context re-read must match the captured attempt inputs before the completed receipt is published; concurrent input changes leave an interrupted receipt for retry. A fact-only pass uses the stored catalog identity and excludes those identity columns from its update payload, preserving corrections rather than deriving them again from old folder names. Existing source receipts in the database become stale once, then acquire v2 metadata on the next ordinary processing pass. This change does not itself enqueue or apply a database backfill.

## Fact-only side effects

`process_meeting` returns `source_only_refresh=true` for the cached documentary repair branch. It preserves cached summaries, attendance, aliases, transcripts, agenda enrichment, and existing choices. Orchestrator does not queue alerts or profile regeneration for that result. Worker does not run attachment extraction, embeddings, or profile generation for it.

An ordinary full-worker job that finds an unchanged meeting (`result=None`) retains its existing attachment/embedding catch-up behavior, but does **not** generate another paid profile draft. A successful new/refined meeting retains the normal profile hooks. Explicit attachment/profile jobs are unchanged.

## Verification

Meaningful pre-fix failures reproduced: a legacy completed receipt incorrectly skipped; fact-only successful jobs invoked attachment/profile follow-ons; orchestrator queued alerts/profiles; an unchanged worker skip regenerated profiles. The repaired ingestion/worker/orchestrator owner cases pass, including normal enriched-job controls. Receipt tests cover unchosen source PDF/HTML/URL changes, identity/membership/policy/loaded-code/regex changes, stable volatile-only updates, and a running worker whose Python file path points at newer code. The ingestion test persists the finished v2 receipt and confirms an actual second processing call skips without enrichment.

Focused cache/ingestion/worker/orchestrator set: 69 passed. Combined source/ballot/ingestion/worker/orchestrator set: 168 passed. Further owner cases first failed for folder-derived date/org identity, a mid-attempt membership change, and unchanged binaries with changed extracted text/date/roster/error/OCR proof; all pass after the fixes. No live database mutations were made by this cache implementation.


## Integrated checkpoint

The parent ran 235 combined source/ballot/cache/worker/profiling tests successfully. The frozen `post-presence-all1104-replay.json` replays every one of 1,104 existing complete ballots and all 7,423 stored complete-ballot choices, with zero choice/date conflicts. It identified 91 additional candidate ballots/607 missing choices; these were subsequently independently reviewed, applied by the separate guarded maintenance script and fully read back (see physical91-applied-receipt.json and physical91-independent-postcommit-verification.json). The cache fix itself performs no bulk database writes. The separate explicit CLI embedding/backlog phase remains unchanged.
