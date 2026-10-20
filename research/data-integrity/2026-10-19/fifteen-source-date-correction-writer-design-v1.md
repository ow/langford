# Fifteen source-backed catalog date corrections: writer proposal

Status: design only. No data writes, schema changes, writer implementation or historical-proof edits are authorized by this document. The source evidence is bound by `fifteen-source-date-proposals-aggregate-v1.json`. Actor corrections must finish and receive independent readback before a fresh date-batch capture.

## Exact mutation boundary

For each of the fifteen reviewed meeting IDs, change only `meetings.meeting_date` from the reviewed old date to the source-supported date. Permit the existing timestamp trigger to change `meetings.updated_at`, after verifying its actual live definition. Preserve every other meeting column exactly, including ID, slug, archive path, title, summary, embedding and metadata. Preserve every motion, vote, agenda item, attendance record, transcript row, identity ledger, participant observation, source key and proof exactly. Do not rename archived directories or regenerate summaries/embeddings. Stable old citation URLs remain valid even where their slug contains the old date.

History belongs in immutable durable before/pending/applied receipts with the source evidence, exact old/new rows and review/code hashes. Do not rewrite historical motion `source_date`, `stored_date`, source-date evidence, ballot reconstruction, previous-source history or ingestion receipts. Those describe the validation inputs at the time. A future validation receipt must be separately versioned and explicitly reviewed; it must not pretend that an old proof used the corrected catalog date.

## Fresh preparation and guards

After the actor lane finishes, capture all fifteen full meeting rows in one read-only repeatable-read snapshot. Capture all dependent full rows and references for these meetings, the complete motions/votes protection witness, applicable memberships/policies at both old and new dates, actual live table/index/constraint/trigger/RLS/function identities and definitions, and exact source/PDF/URL-sidecar hashes. Verify expected old dates and exact stable meeting/source GUID and document binding. Reject duplicates, unexpected dates, competing source claims, catalog changes, changed source artifacts or ambiguous references. Existing indexes and uniqueness constraints must be checked from live catalogs; bootstrap SQL is not authority for an apply.

The plan is immutable and binds the source evidence, aggregate review, before snapshot, protected-row fingerprint, writer/reader implementation and runtime dependencies. A row-count or date-only comparison is insufficient. Preparation and application must neither invoke ingestion nor call a model.

## Atomic apply and reverse

Use SERIALIZABLE, bounded lock/statement timeouts and an explicit finite meeting-ID allowlist. Lock target meetings and the dependent row/reference sets needed to make the protected witness stable; use a reviewed, bounded table-lock order where required to prevent insertion phantoms. Recheck exact full-row and catalog/source/runtime CAS under lock. Compare source artifacts again immediately before commit.

Perform parameterized updates for exactly the fifteen expected IDs and old dates. Assert every after row equals its complete before row with only `meeting_date` and the verified trigger timestamp changed. Assert all protected rows, reference sets, motions, votes, proof metadata and source keys are byte-for-byte logically unchanged. Assert no insert/delete/rekey, no slug/archive/summary/vector/meta change, and no other meeting mutation. Persist an exclusive, fsynced pending receipt before COMMIT; atomically finalize applied state after commit. A lost/uncertain commit response blocks retry until independent read-only resolution from the durable pending receipt.

Reverse uses the same update/assertion path and exact complete after-row/context/catalog/source CAS, restoring only the prior date. It records a new reverse receipt and trigger timestamp; it does not blindly restore a stale entire meeting row. Refuse reversal if later legitimate changes conflict. Run shared forward/reverse first inside an outer rolled-back transaction, preserving before/after fingerprints and proving persistent changes are zero. Root reviews measured validation and exact frozen bytes before any permanent apply. An independent frozen reader verifies complete after rows and every preservation witness afterward.

## Existing source-ingestion cache behavior

Read-only source inspection confirms that `canonical_motions.source_validation_inputs` includes `meeting.meeting_date` in the semantic evidence digest. It also binds `source.stored_date`; `official_ballots.load_official_minutes` / `_load_official_minutes` derives that value from the supplied catalog date. `source_receipt_current` requires exact equality of the new validation inputs and stored receipt inputs. The actual ingester catalog selection supplies `meeting_date`, prepares fresh source context and validation inputs, then checks that receipt before deciding to skip.

Therefore a future normal source-ingestion run cannot reuse a previously finished source-authoritative receipt after a date change. It takes the existing refresh path rather than the unchanged-input skip. This proposal does not execute that refresh, clear historical receipts, change ballot choices or claim that every separate cache in the system uses this key. In particular, the historical proof's old `stored_date` stays intact; cache invalidation is not permission to silently rewrite its history.

Corrected meeting dates affect existing date-filtered readers and joins as intended. Any newly prepared ballot evidence must still independently validate source identity, dated roster and policy. Existing source/header dates already use the original local date; correcting the catalog is not authority to admit previously held motion ownership.

## Scope and review boundaries

The cached source comparison covers forty-one of one hundred ninety-three current meetings, with fifteen source-backed mismatches; the remaining one hundred fifty-two have no bound cached calendar record in this review. No additional crawl is authorized here. The separate regular-workflow scraper repair prefers strictly parsed, agreeing explicit official date fields and preserves epoch fallback only when all display fields are absent. Its code/tests remain frozen until the actor writer is complete and root releases the runtime freeze.
