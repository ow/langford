# Exact-source full-transcription receipt adapter contract

**Design only.** No implementation, parser change, source recovery, rekey, database write, mutation rehearsal, OCR or ML call is authorized. Initial evidence scope is the four independently reviewed complete transcriptions for1478/1479/1480/1879; no broader identity or text admission follows. This adapter proves an exact transcription of a previously identified raw occurrence. It does not decide which legacy row owns that occurrence, or certify any ballot.

## Trusted authority and receipt schema

Use a versioned, reviewed repository store, proposed `pipeline/ingestion/data/native-transcriptions/`, with a versioned manifest and immutable receipt JSON files. Discovery uses original PDF SHA plus the exact raw occurrence, never motion ID. The manifest binds the approved receipt filenames/content hashes, schema version and root/independent public source-review receipt hashes. Arbitrary DB metadata, model output, input documents or a caller-supplied path cannot register or approve a receipt. DB metadata may reference an approved receipt hash; it cannot supply authority for its contents. A missing manifest entry, duplicate conflicting receipt or unsupported version holds.

A receipt contains:

- Schema/rule version and approval-review hashes; complete manifest membership.
- Original public PDF SHA, original URL, source format and page dimensions; the ordinary cleaned source-text SHA and cleanup-contract/runtime version.
- Exact raw source block and raw operative-body hashes; current raw source offset/order and recomputable canonical occurrence key; whole own formal-envelope hash and raw outcome quote/offsets. Raw strings may be retained when useful for review, but hashes never replace occurrence verification.
- The complete accepted full-body UTF-8 text and hash, including every condition and subclause. A zero-change receipt is permitted for the two accepted bodies that already equal the ordinary raw full body.
- An ordered list of exact consumed substitutions. Each identifies its coordinate system, raw body start/end offsets, exact consumed literal, exact replacement literal and associated native/pixel evidence. Insertions/deletions need explicitly reviewed zero-width or deleted spans; they are never implicit whitespace normalization.
- Original PDF page and native word/block/line coordinates for every consumed source span, with complete native words and bboxes, plus the entire operative body's and governing heading's geometry evidence. Wrapped lines must be complete; clipped next-line fragments cannot prove a whole heading.
- Render recipe/version, renderer binary/dependency hashes, page/clip geometry, resolution/color settings and expected rendered page/crop pixel hashes. Approved pixel evidence must bind directly to the same original PDF bytes. Review hashes bind each glyph correction and all unchanged runs.

The store contains only public civic-document evidence and review receipts: no raw voice, private vectors, credentials, private local paths or model-derived authority. If an existing private receipt is needed at runtime, first publish a separately reviewed public-source-only receipt with all required evidence. Do not point a worker at private research artifacts.

## Fail-closed loading and validation

The ordinary source loader first produces the same raw PDF/text/roster/blocks/operative offsets it produces today. The adapter never edits those objects. It can then discover candidate receipts by original SHA and validate them against the actual loaded source.

1. Verify store manifest/version/content hashes and approval-review membership. Hash the actual original PDF and verify URL/source format/date/organization provenance independently. No unknown receipt is treated as an alias.
2. Verify cleaned-text SHA, exact source offset/order, raw block/body hashes and literals. Recompute the existing canonical key from the original meeting/source identity fields; do not use receipt values as a replacement identity or change source_order.
3. Re-prove the complete original own formal envelope, including raw mover/seconder or independently supported formal frame, full body and its own outcome. Reconcile the full original/parsed source inventory, including missed introductions, pending mains, amendments and resumptions. The receipt cannot invent an introduction or explain away an unparsed twin. If source inventory differs from the reviewed fingerprint, hold until reviewed again.
4. Verify every consumed span is in the declared raw-body coordinate system, within bounds, ordered and nonoverlapping, with the exact expected literal. Distinct page/cleaned-text/body offsets must never be interchanged. Verify full native geometry/pixel provenance against the same original artifact and approved render recipe. A missing/cropped/changed word or render hash cannot be ignored. No OCR or model invocation is a fallback.
5. Apply the exact reviewed substitutions only to a separate full-body view. Require every unconsumed character to remain identical, and require the resulting complete body and hash to equal the receipt's approved output. No fuzzy, compact, containment, punctuation or whitespace equivalence is accepted by this adapter. Extra text, changed conditions, reordered clauses or an unlisted glyph change holds.
6. Cache only the validated evidence view, keyed by source identity, raw text/block/body/envelope hashes, complete source-inventory fingerprint, adapter/runtime digest, render dependencies and complete store digest. Revalidation after drift must fail closed rather than reuse an earlier candidate.

Missing, overlapping, out-of-bounds, duplicated or mismatched consumed spans; mutated source/transcription; unknown raw prefix; wrong format/date/body; ambiguous own occurrence; altered pixels; conflicting receipts; and failed whole-body reconstruction all remain holds. An unknown mover prefix may be documented as an original lead, but this adapter cannot recognize it as a parsed occurrence or repair its key.

## Consistent views without an unbound alias

The existing `operative_view(source, block)` must keep its raw-block identity, existing operative-body/boundary classification and existing geometry result. A validated receipt may be exposed in a **separate** `reviewed_full_transcription` evidence field, with accepted full body, receipt hash and exact raw-occurrence binding. Merely loading this field cannot change an existing held operative status or make an arbitrary legacy summary match.

The current default `source_motion_match_keys(source, block)` remains the ordinary raw/proven-view key set. It must not automatically include the new accepted transcription just because a repository receipt exists. In particular, generic `source_motion_candidates`, AI proposal matching and new unbound ingest cannot use it as a broad alias.

A separately named bound comparison, or an explicitly bound mode of the shared match-key function, may include **only exact approved full transcription equality** after a runtime verifier has re-proved the canonical raw identity, own envelope, full relevant source inventory and unique existing-row ownership. That authority must be derived by the verifier from trusted store plus actual source/catalog context, never accepted as an arbitrary dictionary from DB metadata. The adapter contains no motion-ID whitelist.

The same bound verifier must serve all relevant existing-row paths:

- `bound_source_motion`: retain original meeting/PDF/raw body/offset/order/key/own-envelope checks; a verified complete transcription can satisfy only its stored-body equality check.
- Canonical planning: retain complete meeting forward/reverse legacy/source claims, ambiguous/twin holds and the later `source_key_body_conflict` guard. A correctly bound verified transcription may satisfy that same exact body check; the planner must preserve the already reviewed corrected full body on reingestion. It cannot choose an unresolved legacy row or create a new motion from corrected words.
- Ordinary `evaluate_ballot`/merge: choose the same re-proved raw block, retain raw operative identity/outcome/offsets, and propagate a separate full-transcription receipt hash and validation method into proof. Do not replace raw source text or block witnesses with the display transcription.

Full meeting uniqueness is independent of receipt validity. Every source/legacy claimant must be considered, including completed rows and persisted operative claims. The bound verifier therefore needs an authoritative complete relevant meeting-claim inventory in ordinary pipeline context, with a checked inventory fingerprint; a single target row or a caller's selected subset is insufficient. If that context is absent or stale, the new transcription branch holds rather than trusting canonical metadata alone. This requirement must be integrated consistently into ordinary ingestion and direct evaluator/backfill paths before their corrected-body branch can be enabled. A persisted source block's next-heading context after its own outcome is not an operative claim to the following occurrence; distinguish it with exact consumed spans and preserve the stored proof. A genuine competing operative claim holds. Unrelated meeting issues do not veto an independently unique target unless they overlap its item, role, occurrence or claim.

A transcription receipt cannot substitute for legacy record identity approval. Initial assignment of canonical identity to the four rows remains a separate reviewed restoration operation. No corrected unbound text, compact equality or actor-only match can bootstrap that assignment.

## Four-case integration and the separate three-body lane

| Case | Accepted source transcript | Existing runtime issue | Adapter/restoration consequence |
|---|---|---|---|
|1478|Complete native body with two reviewed glyph spans|Corrected text is outside current raw match keys|Requires separately reviewed exact receipt; preserve original raw key/block/offset/order.|
|1479|Complete unchanged raw native body|Body-string matching can already succeed after an approved restoration|Zero-change receipt may supply uniform provenance; it must not bypass other gates.|
|1480|Complete native body with three reviewed glyph spans|Corrected text is outside current raw match keys|Requires separately reviewed exact receipt; preserve original raw key/block/offset/order.|
|1879|Complete unchanged raw native body, including nontransfer/cessation tail|Body-string matching can already succeed after an approved restoration|Zero-change receipt may supply provenance; shortened tail must never pass.|

The additional1739/2910/3847 source-only geometry/body evidence is outside this four-case implementation proposal. Later original-source approvals do not automatically clear their existing runtime body holds, establish legacy identity or enroll them in a receipt manifest. A separate root-reviewed scope must resolve complete wrapped headings, own occurrence/body geometry and `Option 1` handling; no adapter rule may globally clear native_body_not_uniquely_bound_held or operative_boundary_unknown_held. Accepted glyph evidence alone is insufficient.

## Required validation plan, only after implementation approval

Use the existing210-test focused suite as the recorded baseline, preserving its earlier failure/repair lineage. Add only the meaningful new adapter-owner boundary regressions justified by this contract, following test-audit. Do not claim210 remains the exact future test count after new cases are added.

Required positive proof: the four actual original PDFs/occurrences, exact complete accepted outputs and unchanged raw keys/blocks/offsets/orders; two nonzero-span and two zero-span receipts; identical bound behavior across ordinary evaluation/merge and canonical existing-row reingest. An unbound legacy summary must remain held even when the source has a valid transcript receipt.

Required negative proof: missing/unapproved/tampered manifest or receipt; modified original PDF/raw block/key/order/offset; wrong coordinate system; missing/overlapping/out-of-bounds/literal-mismatched spans; changed pixels/native word boxes/render recipe; unlisted output change or removed1879tail; wrong existing-row owner or competing persisted claim;3457/3459twins; unknown/unparsed raw-prefix occurrences; mismatched source date/roster/arrival/session/policy state. Preserve the same source-supported documentary holds rather than inventing candidate parity.

Freeze the implementation, loader, render dependencies and full trusted store inventory before final checks. Then:

1. Run the focused210 baseline suite plus the approved adapter owner cases once at the frozen hashes. Preserve any failure lineage; do not weaken guards to obtain parity.
2. Re-run every existing complete ballot from a fresh read-only DB/source snapshot through ordinary shared gates. Compare complete per-person choices and IDs, full existing rows, choice provenance, original PDF/date/roster/result/attendance evidence and raw occurrence ownership, not just totals. The earlier1331/8949 result is historical; recapture the actual complete universe after intervening writes. Report any genuine new ambiguity and preserve existing evidence.
3. Re-run the exact four source cases through ordinary loader, canonical existing-row planning, evaluator and merge. Keep identity/body/restoration/ballot decisions distinct. Do not promise four ballots or bypass date, roster, membership, attendance, result/tally or policy gates.
4. Verify the separate three-body scope and the named duplicate/competing/unknown-prefix negatives remain unchanged. No source recovery, new motion, rekey or ID change is part of these checks.

No mutation rehearsal is part of this design. A later restoration plan must follow actor-five independent readback and recapture current full rows/votes and the actual FTS expression/index/trigger contract. Preserve old text/meta/audit/vector in exact before/history evidence and independently verify any eventual approved after state.

## Runtime/cache guard and deployment lifecycle

Add adapter module bytes, loader integration bytes, any new bound-match integration bytes, receipt-manifest bytes, the **complete sorted receipt filename/content inventory**, approval-review files consumed at runtime and render/geometry dependencies to `loaded_ballot_guard_digest` and corresponding derived source/cache dependencies. Added, removed or changed receipts must invalidate cached holds and candidates; hashing only files already listed by an old cache entry is insufficient.

A running worker may retain imported code, a receipt index or cached proof objects. Require a worker/process restart or redeployment after any adapter/store/runtime change, then verify the freshly loaded digest equals the reviewed on-disk digest before processing. On mismatch, hold processing; do not accept hot-reloaded metadata as proof that all imported state changed. Record the loaded digest with receipts and replay results. A code commit alone is not evidence that a long-running worker uses it.
