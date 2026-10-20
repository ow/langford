# First finite ballot-repair batch

This code-only batch addresses three confirmed causes from the 496-record diagnostic census. It makes no database changes. The last verified live receipt still says **1,223 complete / 496 unresolved**; the figures below are offline results on that exact receipt-backed state.

## Behavior changes

- An original agenda accommodation is a typed documentary observation with **no attendance state effect**. It can release the agenda's own ballot, or a later ballot only after the uniquely referenced item has a complete, source-owned exit → formal motion → outcome → return episode before its next peer heading. Ambiguous subjects, target ballots, missing/duplicate headings, pre-heading exits, nested/unclosed introductions, unknown chair transfers, actual movements in the agenda bullet, and recipient-specific declarations remain held. Raw source text, physical events, IDs and occurrence keys are unchanged.
- Special-threshold uncertainty still holds actual extensions and unfamiliar procedural language. Exact incidental owner reconsideration-rights/deadline references and a staff review of extension-consent rules no longer trigger the hold. The classifier is shared by Council/COTW and CAC. All 21 actual extension holds in this census are preserved, including “at 9:53 pm, extend…”.
- Original-source withdrawals and documentary adjournments with no choices receive `individual_vote_coverage=not_applicable` and matching `vote_record.coverage`. Existing choices are preserved and prevent this classification. A TABLED result remains held; a non-Yes/No label alone cannot establish that no ballot occurred.
- The documentary classifier is included in the loaded runtime guard. Older validation/skip receipts cannot authorize skipping this new code.

## Frozen before/after evidence

`finite-ballot-repair-first-batch-evidence.json` contains exact input/guard/output hashes, 18 proposal targets and source URLs. `replay_finite_ballot_repairs.py` reconstructs the frozen committed state and evaluates cached evidence without constructing a database client, invoking OCR, or permitting socket access. Full original rows and source contexts remain local; the committed evidence is minimized.

| Disposition of original 496 | Count |
|---|---:|
| Newly passing ballot candidates | 14 |
| Source-proven non-ballot records | 4 |
| Remaining documented holds | 478 |

The 14 candidates supply **98 inferred Yes choices**, seven each. They are inferred under the already validated dissent-recording convention, **not explicit individual roll calls**:

- Meeting 37: 253, 258–267 (11 ballots).
- Threshold predicate false positives: 1986 (meeting 24), 1820 (172), 2394 (233).
- Metadata-only non-ballots: 1755, 1980, 2841, 3068.

Meeting 37 was reloaded from its original PDF through the ordinary source loader. The closed target's native heading is **6487–6551**, exit **6649**, formal introduction **6773**, outcome **10076–10180**, return **10219**, next peer **10310**. The earlier participation episode at 2368/2621 cannot discharge the target reference. All 11 meeting-309 declaration holds remain unchanged.

The **1,223 current-term complete ballots** and **125 older complete ballots** (dated March 19, 2020–September 6, 2022) together form the **1,348 all-history replay corpus**. Current-term complete ballots contain 8,253 choices; 8,275 includes 22 partial choices. Older complete ballots contain 781 choices. All **1,348 already complete ballots / 9,034 complete choices** still pass. Their full candidate results, proposed choices, merged metadata and existing-choice fingerprints compare exactly before/after, without proof normalization or ignored fields. All 3,727 motion and 9,057 vote fingerprints match the latest applied receipt during input reconstruction. All original source binaries for the 18 proposed targets were rehashed successfully.

If a separately reviewed data batch were later applied, the current-term accounting would be **1,237 complete + 478 held ballot targets + 4 non-ballot outcomes**; current choice rows would be 8,373. These are hypothetical, not live counts.

## Validation

The final focused suite passed **219 tests** across official ballots, physical presence, committees, header attendance, source occurrences, unique tallies, canonical motions and operative bodies. Eight positive regression cases were reproduced as intended failures against unchanged `main`; the negative controls passed. One independent review then found an overlapping-extension-reference P1 in the first PR commit. The exact owner-boundary reproducer failed before correction and passes after correction; the same reviewer independently confirmed closure. The corrected replay payloads for all 1,844 selected records are exactly unchanged. Additional counterexamples caught and repaired an incidental-reference overreach and protected TABLED results. No test-only production hook was introduced.

Each new test belongs to the ordinary `load_official_minutes → merge_ballot_evidence` owner boundary. It protects observable choice sets, provenance/physical ordering, or non-ballot coverage metadata against a concrete demonstrated failure. Existing low-level physical/roster tests remain the owners of their unchanged contracts; they are not duplicated.

Example focused verification (from `apps/pipeline`):

```sh
python -m pytest tests/ingestion/test_official_ballots.py tests/ingestion/test_ballot_reconstruction.py tests/ingestion/test_committee_ballots.py tests/ingestion/test_header_attendance.py tests/ingestion/test_source_occurrences.py tests/ingestion/test_unique_tally_ballots.py tests/ingestion/test_canonical_motions.py tests/ingestion/test_operative_motion_body.py --no-cov -q
```

The offline replay accepts explicit `--evidence-root`, `--sources`, and `--output` paths. Use the frozen source-context artifact whose SHA is in the evidence JSON; do not silently refresh sources or rebase the fixed 496-target input. Policy snapshots are reused and have not been freshly renewed. The exact local source/proof artifacts are available for parent review; they are not needed by production ingestion or tests.

## Data proposal boundary: pending first-batch scope review

The local `first-batch-data-proposal.json` holds exact before full rows, intended after metadata, the 98 proposed natural choice values, full evaluated proofs, and original source hashes for these 18 IDs. Its hash is committed in the evidence JSON. It is a review proposal, not an executable or authorized applier.

A later separately reviewed executor must satisfy all of these concrete requirements:

1. Fresh read-only target capture and current source/policy/claim checks must match the proposal. Lock only the 18 target motions and their vote rows; require exact before rows and zero current target votes before any write. Do not depend on immutability of unrelated global sequences or schema.
2. In one transaction, insert exactly the 98 planned choices and update only the 18 `meta` fields plus managed timestamps. Preserve source text, IDs, roster, vectors, all other columns and every pre-existing vote. A mismatch aborts the entire transaction.
3. Recognize a repeated execution only when **all** target business rows/metadata and choice tuples already equal the complete planned after state. Return an unchanged no-op with no ID allocation. Mixed or competing state is held, not resumed blindly.
4. Capture exact allocated vote IDs/full rows and target after rows in an applied receipt. Independently read back exact metadata, choices and immutable columns; confirm the four non-ballots still have no choices and all pre-existing votes/proofs remain unchanged.
5. Rollback requires that exact applied receipt plus fresh after-state comparison. Delete only receipt-owned vote IDs and restore exact prior metadata. Record managed rollback timestamps explicitly; never rewind sequences. Independently verify restored metadata, zero target choices and preservation of all pre-existing votes. No rollback rehearsal or live readback has yet run for this proposal.

No live update, merge, deploy, paid API, model, embedding transfer, uncached OCR, broad pipeline run or recurring job was started. The existing recurring schedule was left off.

## Next finite cohorts

Every one of the 478 residual cases is listed in `finite-ballot-repair-holds.csv` with its blocking cause and required evidence/change. Do not retry a held case without that change.

After first-batch review, the next source cohort is the existing exact raw-body proposals **988 / 3174 / 2443**, retaining full clauses and complete meeting ownership. Meeting 309's 11 declaration cases require an independent recipient-overlap model with main/amendment/resumption/incorporation closure. Arrival and resumed-session cases require source-proven chronology; committee identity/role conflicts require dated evidence. Skipped-introduction recovery/rekeying and new OCR remain outside this batch. No individual vote is guessed to meet a coverage target.
