# Matter integrity audit

Read-only live snapshot: 1,640 matters, 6,197 agenda items, 3,624 motions,
344 meetings. The queried live columns include `matters.meta`, `bylaw_id`,
`agenda_items.matter_status_snapshot`, and persisted motion result/disposition.
The reviewed repairs below were applied with optimistic concurrency checks and saved before-values.

## Status lifecycle (#1)

`Ingester.get_or_create_matter` always inserts `Active`; nothing subsequently
updates it. A passed motion may simply request a report, give first reading,
or receive correspondence, so marking every passed motion as completed would
replace missing data with incorrect data.

New deterministic rule: a persisted carried substantive motion must explicitly
adopt or repeal every bylaw identifier of the linked matter. Recommendations,
conditional/future adoption, interim readings, amendments and failed motions do
not qualify. General topics/projects remain unresolved. The most recent dated
final action wins, independently of ingestion order. Provenance records the
motion ID, meeting ID/date, matched bylaw numbers, exact source text and rule
version in existing `meta.lifecycle_evidence`.

The reviewed proposal applied **283 Active → Adopted** changes. Every qualifying source is
from Regular Council (248) or Special Council (35). Examples: matter 22 / bylaw 2237,
matter 25 / bylaw 2246, matter 47 / bylaw 2260. Inspect `matter-repair-proposal.json` for
all rows. No generic project is declared completed or denied. The remaining
1,357 records require richer object-level evidence or remain ongoing; Active
still does not prove a project has never finished. The ingestion hook refreshes
affected matters from their complete persisted motion history after ingestion.

Status application updated only `status` and merged the provided
`lifecycle_evidence` key into each *current* metadata value. Every row passed fresh status and metadata preflight checks and each update used a status+metadata comparison to guard concurrent changes. Before-values and per-row application receipts are saved in `/private/tmp/matter-status-before-2026-10-18.json` (mode0600).

## Duplicate matters (#5)

Plural identifiers such as `Bylaw Nos. 2275, 2270 & 2271` were not split into
individual identities. The matcher now understands these lists, semicolon
bundles, and explicit title-only bylaw numbers. A one-bylaw item is not
automatically equated with a bundle containing other bylaws.

The audit finds **19 matching bylaw-set groups / 20 excess records**. These are
merge candidates, not an automatically approved fuzzy merge list. The reported
Amenity Cost Charge example is exactly matters 205 and 218, both covering
2270/2271/2275, both seen June 15–29, 2026. The candidate canonical ID is 205.

A concrete counterexample demonstrates why matching a number alone is unsafe:
matters 1607 (Centre Mountain BP8 variance) and 1645 (2181 Bear Mountain Parkway
variance) both cite parent servicing Bylaw 1000 but are different applications.
These are excluded from the candidate groups. The matcher also refuses to use
a shared parent bylaw to join different variances without shared property
addresses. Broad fuzzy merging remains audit-only.

Before applying any candidate merge, compare full matter scope and linked
agenda content, inspect all live foreign keys and bylaw links. In one transaction:
retain both matter IDs, relink the duplicate's agenda/evidence/subscription links
to the canonical record as appropriate, merge dates/metadata, and store a
canonical alias/redirect for the old ID. Do not hard-delete history. The exact205/218 pair has now been consolidated through reversible metadata:
218.meta.canonical_matter_id=205;205.meta.merged_matter_ids=[218]. Both IDs and
the two original agenda links (item1384/meeting50 adoption; item1505/meeting49
first reading) are retained unchanged. The canonical service aggregates both
histories and evidence, the old detail URL redirects301 to205, lists filter
aliases before pagination, and the matcher excludes aliases. Canonical dates
are June15–29,2026. Before-values and unchanged agenda-link evidence are saved
in `/private/tmp/matter-alias-205-218-before-2026-10-18.json` (mode0600).
The other18 candidate groups remain audit-only (the initial19 included205/218).

## Home “New” badge (#9)

The component used `first_seen === last_seen`, so a single appearance from 2021
was still labelled New. It now requires first_seen within the preceding 30 days,
with valid nonfuture dates. Older records show their first-discussed date.
This uses calendar evidence rather than appearance-count equality.

## Validation

- 71 focused pytest cases passed (existing matcher suite plus bundle identity,
title-only identity, parent-bylaw variance safety, and lifecycle regressions).
- The exact 205/218 bundle input returned no_match on HEAD's previous matcher;
it matches 205 after the fix. This reproduces the actual duplicate creation bug.
- Proposal regenerated after tightening the direct-action-object rule; all283 genuine adoptions still qualify. Regressions reject report/plan/policy adoption that merely cites a bylaw. No source texts or meeting dates were modified.
- `git diff --check` passed.
- Web integration/type checking belongs to the parent's coordinated test window.

Reproduce the audit from current live data (read-only):

```sh
PYTHONPATH=apps/pipeline apps/pipeline/.venv/bin/python \
  research/data-integrity/2026-10-18/audit_matters.py \
  --output /private/tmp/matter-repair-proposal.json
```

Live verification is in `matter-repair-verification.json`. At the baseline repair boundary, all 1,640 physical IDs were retained with 1,639 canonical visible records. Concurrent ingestion subsequently added records; the verification file records its own later global counts, independently of the 283 repaired rows. Rollback consists of compare-current
updates restoring saved `status`/`meta` for status receipts and saved metadata/
dates for the two alias records; never discard changes made after this run.

## Independent official-source validation after application

A separate exact-body audit re-read the official minutes caches without using
the fuzzy vote matcher or its deduplication. **249 adoptions** have exact
normalized formal motion text, compatible explicit carried outcomes, source
URLs, cache SHA-256 hashes and quotes. **34 remain persisted-motion evidence
only** because no exact bounded source body matched; **zero contradicting
outcomes** were found. The34 were not declared raw-source certified. Existing
status values were retained and every lifecycle record now has
`validation_status` and `source_validation` metadata distinguishing these cases.
Full proof is in `matter-exact-source-validation.json`. Metadata before-values
are in `/private/tmp/matter-validation-before-2026-10-18.json` (mode0600).

## Remaining exact duplicate review

All18 remaining initial same-bylaw groups were reviewed against complete linked
agenda/motion scope and bounded official cache context, URL and SHA-256 proof.
**16 groups /17 aliases** are proven same-bylaw/same-subject histories, preserving
all33 source IDs and50 agenda links. The orphan206 would point to better-evidenced
217; the other groups use their lowest ID as canonical. Full before/after fields
are in `exact-matter-merge-updates.json`; source proof and reasons are in
`exact-matter-merge-plan.json`.

Two groups are held because current agenda links widen their actual scope:
231/661 includes item1631 for separate Bylaw1703 under matter1694;912/1297 includes
item2622 for separate Bylaw1990 under matter1989. Correct those links and re-audit
before merging. Neither distinct property/permit applications nor generic parent
bylaw references were merged.

Automatic approval review initially rejected the16-group/17-alias operation
because it required explicit approval of the exact production scope. The user
subsequently approved the named IDs/status/date/metadata changes and preservation
requirements. **The16 groups /17 aliases have now been applied and verified.**
The initial comparison gate stopped before writes when concurrent ingestion had
already adopted506; only its before-values were refreshed, preserving that
same-motion metadata. No merge scope was expanded. Both held groups remain
untouched.

`exact-matter-merge-receipt.json` records33 retained source IDs and50 unchanged
agenda links. Private before-values are in
`/private/tmp/reviewed-matter-merges-before-2026-10-18.json` (mode0600).
Read-only tests of the actual production service resolved all35 source IDs
across17 groups (including the earlier205/218 pair), preserved every historical
agenda item/address, and omitted aliases from canonical lists. Evidence is in
`exact-matter-merge-service-verification.json`. The canonical list service batches
retained alias agenda/geo evidence so maps and address filters preserve history.
Global counts continue to change with concurrent ingestion; that service check
observed1649 canonical records after consolidation.

## Independent recent HTML ballot pilot review

The57-motion pilot across meetings389/390/391/392/394 was independently checked
against actual structured official HTML DOM nodes, not the ballot reconstruction
helper. All57 have unique exact normalized formal motion bodies, original-file
hashes, source carried results and exact initial/surname roster identities. The
335 proposed choices include2 explicitly named No choices, each verified inside
its own motion's PostMotionText; the other choices remain documentary inferences.
The fixed attendance guards correctly include Morley after motion withdrawal,
exclude Harder before her first join, and hold header-arrival and collective/
OCR-ambiguous attendance cases. The hash-frozen guarded pilot script was reviewed
for concurrent changes, conflict holds, no overwrites and rollback safeguards.
No inferred vote rows were written by this lane. See
`html-ballot-pilot-independent-review.json`; final application belongs to the
vote lane/root coordinator. These checks establish documentary consistency,
not audiovisual or human ground-truth accuracy.
