# Motion search and RAG read-model plan v1

Read-only proposal, 2026-10-19. No schema, data, RPC, production code or embedding changes have been executed. **Finish the 1505 text writer and its independent readback first**: it is bound to the existing generated expression. Capture new migration evidence only after that work finishes. Root review is the final decision before implementation.

## Verified live state

The read-only catalog snapshots have SHA-256 `de095b69bafc8626d9ff4b35fc3d69cb0f3509e8303f71a0a34136d1d65a357a` and supplemental SHA-256 `be2e88c2d821ee6c025cedf7bfd90460338599f14d8e7e91564bee9e897bbfd7`. Complete definitions, ACLs, constraints and aggregate counts are retained privately.

- PostgreSQL **17.6**, server version number `170006`.
- `public.motions`: 3,727 rows, 3,722 nonnull summaries, 3,727 nonnull bodies, six NULL embeddings. Heap 11,026,432 bytes; total relation size 22,503,424 bytes at capture. These counts are observations, not future write preconditions.
- Stored generated `text_search` is currently `to_tsvector('english'::regconfig, COALESCE(plain_english_summary, text_content, ''::text))`. A nonnull summary suppresses indexing the source body.
- Existing `idx_motions_fts` is GIN on `text_search`, 1,073,152 bytes. The existing embedding HNSW index is 4,734,976 bytes. Both were valid and ready. Capture the complete index inventory again before any migration; account for index work during rehearsal.
- The column dependency inventory contains its generated expression and GIN index. Motion relationships include meeting/agenda/mover/seconder FKs and incoming vote, key-vote and transcript references. No dependency should be dropped or recreated as part of this change.
- Table owner is `postgres`; RLS is enabled. Five motion search RPC overloads exist. All are security invoker, owned by `postgres`, have `search_path=public`, and currently permit execution by PUBLIC, postgres, anon, authenticated and service_role. Preserve these exact properties; do not widen privileges.

## Complete RPC and reader inventory

| Live signature | Search behavior | Repository callers / effect of generated-expression change |
| --- | --- | --- |
| `match_motions(halfvec,double precision,integer)` | Vector distance and threshold | `services/vectorSearch.ts:searchMotions`, indirectly `services/search.ts:vectorSearch`; current `rag.server.ts:search_motions`. No SQL change proposed. NULL-vector rows remain excluded. |
| `match_motions(halfvec,double precision,integer,bigint)` | Same vector search with municipality filter | Available filtered overload; preserve signature/defaults. Used in guarded verification. No SQL change proposed. |
| `hybrid_search_motions(text,halfvec,integer,double precision,double precision,integer)` | GIN full-text branch plus semantic branch, reciprocal-rank fusion | Legacy-compatible overload. Its existing `m.text_search` references automatically use the corrected column. |
| `hybrid_search_motions(text,halfvec,integer,double precision,double precision,integer,date,date,bigint)` | Same, with date and municipality filters | `services/hybrid-search.server.ts:hybridSearchMotions`; proposed RAG retrieval below. Existing FTS references automatically improve. |
| `match_motions_by_person(halfvec,bigint,double precision,integer)` | Vote-linked person-filtered vector search | `pipeline/profiling/profile_agent.py` deep-dive evidence. Preserve its signature, vote join and NULL-vector exclusion. This remains semantic-only; no profile generation or embedding regeneration is part of this plan. |

Other motion readers:

- `app/api/endpoints/search.ts:searchMotions` directly calls `.textSearch("text_search", q, { type: "websearch" })`. Keeping the same column name/type makes it search both fields without an API shape change.
- `services/search.ts` has a legacy substring branch on `text_content` and a separate vector branch. Its substring contract remains unchanged; do not claim that a generated-expression update turns substring search into FTS or changes its summary coverage.
- Existing motion detail/list/meeting/person/site readers retain their fields and relations. UI tally consumers already use `lib/vote-coverage.ts`; the home feed explicitly avoids the zero legacy counters.
- Only the two live hybrid motion functions depend on `motions.text_search` in their function bodies. The five RPC definitions, return shapes, defaults, ACLs, owners, security properties and settings remain **byte-for-byte unchanged** in the proposed database migration. Do not remove legacy overloads to resolve caller dispatch; verify parameter binding through the existing API boundary instead.

## Recommended PostgreSQL 17 migration

Use in-place `ALTER COLUMN ... SET EXPRESSION AS`, retaining the existing column and GIN definition. PostgreSQL 17 supports this directly; dropping the column is unnecessary. It recomputes stored generated values and removes column statistics, so plan a rewrite, a bounded exclusive-lock window and subsequent analysis. [PostgreSQL 17 ALTER TABLE](https://www.postgresql.org/docs/17/sql-altertable.html).

The new expression indexes **both** fields, with null handling per field and explicit English configuration:

```sql
-- DRAFT ONLY. A reviewed guarded migration runner must own pre/post assertions.
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';
ALTER TABLE public.motions
  ALTER COLUMN text_search SET EXPRESSION AS (
    to_tsvector('english'::regconfig,
      COALESCE(text_content, ''::text) || ' '::text ||
      COALESCE(plain_english_summary, ''::text))
  );
-- Verify source-row fingerprints, exact new expression, indexes, constraints,
-- RPC definitions/ACLs, table/column identity and RLS before COMMIT.
COMMIT;
ANALYZE public.motions (text_search);
```

Use equal lexical weighting initially; do not combine this repair with ranking-weight tuning, stemming changes, new embeddings, summary edits or vector index configuration changes. Joining the two fields means phrase ranking/search semantics must be checked at the field boundary, as well as recall for terms unique to either field. PostgreSQL documents multi-column concatenation and explicit configuration for text-search indexes. [PostgreSQL 17 text-search tables and indexes](https://www.postgresql.org/docs/17/textsearch-tables.html).

The `2s` lock and `30s` statement budgets are proposed hard ceilings, not measured estimates. **Rehearse on an isolated PostgreSQL 17 copy with matching rows, extensions, indexes and constraints first**, then choose a production window within those ceilings or return to root with measured evidence. Do not run a production rolled-back table rewrite merely as a casual probe. Drain long-lived transactions around the reviewed window; PostgreSQL notes special snapshot behavior for table rewrites. A failed timeout must roll back and produce a held receipt, with no blind retry or automatic increase of the lock budget.

### Guarded preparation, rehearsal and apply

1. After 1505 is finished, capture actual server version, column attnum/type/generated flag/expression, complete index definitions/validity, constraints, triggers, policies, table/column ACLs, all five RPC definitions/defaults/owners/ACLs/settings, and complete motion/vote source fingerprints. Preserve these in immutable private evidence. No raw vectors or source text belong in a public receipt.
2. Compute sorted per-motion fingerprints from full `to_jsonb(m) - 'text_search'`, **including text, summary, embedding, metadata, IDs and timestamps**. Separately capture the full vote-row fingerprint and relation counts. The only permitted motion-row value delta is generated `text_search`. Retain old generated vectors privately for an independent semantic comparison if useful; do not rewrite the source columns to force recalculation.
3. In the isolated rehearsal, use the real migration path inside an outer rolled-back transaction. Validate every generated vector against the reviewed new expression; prove body-only and summary-only terms resolve; validate GIN results against a sequential expression evaluation; execute both hybrid overload contracts with stored existing vectors; confirm NULL embeddings still have no semantic contribution. Verify all non-FTS motion/vote fingerprints, index validity, FKs, RLS, function signatures/definitions and ACLs. Exercise the same rollback-expression path, then outer rollback and exact original readback. Record timing, lock wait and index/storage impact, including HNSW preservation/rebuild behavior.
4. In a future separately approved live run, bind exact migration/review/before hashes. Acquire the lock within the fixed budget, compare all catalog/source fingerprints under the lock, change only the expression, and repeat all non-FTS and catalog assertions. Persist a durable private pending receipt before COMMIT. A successful or uncertain commit requires independent readback; never blindly retry. Do not modify bootstrap or deploy reader changes before root approves the concrete result.
5. Perform `ANALYZE` after success; an analysis failure is an explicit follow-up status, not permission to reapply DDL. Verify the expression, all indexes ready/valid, row/source fingerprints, unchanged RPC ACLs and concrete query results independently. The public aggregate contains only counts, hashes, timing and limitations.
6. Update the bootstrap expression to match the reviewed deployed expression when implementing the approved migration. No new table, column, trigger, function overload, policy or embedding is needed.

### Reversal

Rollback changes only the generated expression back to the exact captured original:

```sql
-- DRAFT ONLY. Same guarded runner, bounds and current-schema CAS required.
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';
ALTER TABLE public.motions
  ALTER COLUMN text_search SET EXPRESSION AS (
    to_tsvector('english'::regconfig,
      COALESCE(plain_english_summary, text_content, ''::text))
  );
COMMIT;
ANALYZE public.motions (text_search);
```

Require current expression/schema/ACL/index/RPC fingerprints to equal the receipted new state. Recompute old search semantics from the **current** source text/summary; never restore stale whole motion rows or vectors as a search rollback. Verify all non-FTS fields and vote rows remain unchanged during this reversal.

Existing six-text and fourteen-ballot guarded receipts include complete motion rows with the **old** generated `text_search`. The six-text writer additionally binds its original expression in the database contract. Their frozen whole-row rollback will correctly refuse to run while new derived vectors differ. **Reverse this search migration first before invoking an older frozen content/ballot rollback**, or prepare a separate independently reviewed receipt-aware adaptation. Do not edit old receipts or silently ignore arbitrary differences.

### Alternatives considered

| Option | Advantage | Additional risk / why not first choice here |
| --- | --- | --- |
| In-place PostgreSQL 17 expression replacement | Same column/index/API contracts; fixes existing direct FTS and both hybrid overloads together | Requires measured rewrite/lock window; selected only with successful bounded rehearsal. |
| Concurrent additive GIN expression index | Avoids replacing the stored column and preserves full motion-row shapes | Existing `.textSearch("text_search")` readers do not use it. Requires matching expression changes in both hybrid RPCs and a new lexical RPC or API-reader redesign. More deployment surfaces; reserve if rewrite cannot meet the lock budget. |
| Additional stored generated column | Explicit new-field rollout | Stored-column population still needs rewrite/locking; readers/RPCs must migrate; `to_jsonb(m)` gains a field and invalidates frozen full-row receipts. |
| Drop/recreate `text_search` | None needed on this server | Unnecessary dependency/ACL/reader risk; rejected. |

If the additive expression-index route is later selected, its query expression must match the indexed expression and explicit language configuration. Build it with `CREATE INDEX CONCURRENTLY` outside a transaction, validate completion/`indisvalid`, and retain the old index until rollout is verified. Concurrent index creation cannot run inside a transaction block. [PostgreSQL 17 CREATE INDEX](https://www.postgresql.org/docs/17/sql-createindex.html).

## RAG retrieval change, using the existing query embedding

Current `rag.server.ts:search_motions` calls `embedQuery`, returns nothing if it fails, then calls vector-only `match_motions`. Thus a generated-expression repair alone will **not** make the six NULL-vector restored motions reachable through this tool.

Proposed bounded reader change:

1. Generate the query embedding at most once through the existing call. Reuse it; do not create document embeddings or add another model call.
2. Call the existing **filtered nine-argument** `hybrid_search_motions`, explicitly supplying every argument, including date and municipality parameters using the existing request scope. Set `query_text` to the user query, ordinary weights to `1.0/1.0`, and retain its existing `rrf_k`. Push `after_date` into `date_from` instead of discarding dated results after retrieval.
3. If embedding generation returns null or fails, call the **same** RPC with null query embedding and `semantic_weight=0`, `full_text_weight=1`. Require a finite **positive** `rank_score` before accepting any result. The existing SQL semantic branch can return arbitrary rows when distance to a null query vector is unknown; weight zero alone does not remove their zero-score rows. Filter them out and do not treat them as semantic evidence. A no-hit text query must return no motions.
4. Keep positive ranked IDs in RPC order, deduplicate by motion ID, and enrich them with actual motion/vote data. Reorder enrichment rows by this retained ID order; an `.in(id, ...)` query does not promise rank order. The live hybrid RPC caps results at 30 even when a larger count is requested; respect that explicit bound and test dated retrieval without relying on the old semantic over-fetch of 50.
5. Return `rank_score` as rank score, not as fabricated cosine `similarity`. Preserve source IDs, meeting/citation URLs and exact current text. On RPC/enrichment errors, expose the existing retrieval failure behavior; do not manufacture a `0–0` tally or another semantic result. No new RPC signature or ACL change is required.

## Coverage-aware RAG vote counts

Live aggregate: **1,331** motions marked `reconstructed_complete`; all 1,331 have zero legacy yes/no counters. Their actual vote rows are nonempty, have unique nonnull person IDs and valid choices. Another 13 motions have `named_only` partial records. Missing or partial records must not be turned into complete totals.

`rag.server.ts` currently selects and spreads `yes_votes`, `no_votes`, `abstain_votes`, `absent_votes` alongside nested votes, while omitting coverage metadata. Replace that read model:

- Select `meta` and `votes(vote,person_id,people(name))`; stop selecting legacy numeric counters for model context.
- Reuse `isReconstructedVote` from `lib/vote-coverage.ts` as the coverage gate. Add one shared, typed tally helper at this existing owner boundary when implementing; let `voteTally` and RAG use the same numeric result rather than parsing a display string or duplicating counting rules.
- A complete record must also have nonempty rows, unique nonnull person IDs and supported choice values. Otherwise return `counts=null` with unknown/partial coverage and preserve the observed named rows as partial evidence. Do not infer completeness from `CARRIED`, the number of names, mover/seconder, or absence of dissent by itself.
- For valid complete present-voter records, derive `yes` and `no` from actual rows. A known complete 4–3 record becomes `yes=4,no=3`; a partial list of three No names has unknown complete totals, not `yes=0,no=3`. Preserve explicit/inferred choice provenance through existing metadata; complete reconstruction is not an explicit named roll call.
- Keep absence distinct from the present-voter ballot. No `Absent` row does not establish that nobody was absent. Return unknown absent total unless a separately complete roster/absence source proves it. Likewise do not promote recusal or unsupported choice states into ordinary Yes/No. Current live choices are Yes/No only.
- Prefer an explicit tool object such as `vote_counts:{yes,no}` or null plus `vote_coverage` and `tally_basis`. If internal compatibility requires `yes_votes`/`no_votes`, populate those **derived** values only for complete valid records and use null otherwise. Remove the spread of stale legacy fields. Do not update historical database counters or run profile/summary generation in this repair.

## Implementation verification boundaries

No tests were added in this proposal phase. During approved implementation, keep each contract at its owning boundary:

1. **Real PostgreSQL 17 migration boundary, isolated data copy:** old/new expression and rollback path; non-FTS fingerprints; FKs/index validity/RLS/ACLs/unchanged five function definitions; GIN-vs-direct-expression equivalence; body-only, summary-only, null/empty summary and field-boundary phrase cases. Include exact terms from reviewed restored source fixtures without putting private text/vectors in public artifacts.
2. **Existing RPC boundary:** both hybrid overloads find a body-only term for a NULL-embedding motion after migration; summary-only recall remains; three vector-only overloads retain thresholds/person/filter behavior and exclude NULL embeddings; date/municipality dispatch and legacy call shapes remain valid. Use stored vectors or synthetic fixed vectors on the isolated copy, never an embedding API.
3. **RAG tool retrieval boundary:** a NULL-vector restored motion is retrievable through FTS; missing embedding uses weight zero and discards zero/NaN ranks; a no-hit query returns empty; deduplication and enrichment preserve ranked source IDs and dates. Replace providers with existing test fixtures so the test performs no AI call; do not add a production-only injection seam just for the test.
4. **Shared vote-coverage helper:** complete 4–3 and complete all-Yes records derive correct totals; named-only/empty/duplicate/null-person/unsupported choices return unknown totals; absence is not inferred. The UI display and RAG payload consume this one contract.
5. **Public search/API compatibility:** direct `text_search` endpoint finds restored body terms while retaining response fields, slugs, municipality scope and citation links. Confirm the legacy substring route remains explicitly its existing route rather than claiming it acquired FTS behavior.

Scope ends at this plan. No generated expression, index, RPC, reader, counter or embedding has been modified, and no new AI/API call was made for verification.
