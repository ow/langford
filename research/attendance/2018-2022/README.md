# Historical council attendance correction

The former mayor's profile showed 2% attendance because two AI attendee rows
were divided by 89 meeting entries. Missing attendance was treated as absence;
65 meetings contained staff/other attendees but no elected-member attendance.
Cached extracts often selected ATTENDING staff and omitted PRESENT councillors;
61 separately identified Young as chair. The source corpus was substantially
more complete than its attendance rows.

PR #7 replaced these grades with source-verified presence, absence, unknowns and
coverage. A rate is available only when every eligible meeting is verified.
This follow-up accepts explicit attendance events in the original minutes,
including a documented later arrival, and records the bounded data correction.

## Results

All 88 original roster pages were visually checked against source headings,
dates and the seven-member historical council identity mapping. Existing native
PDF extraction and geometry provided cached leads, not the acceptance gate.
Image-only originals were reviewed visually. Missing roster entries were not
inferred absent. The 89th entry was an official cancellation notice.

605 verified records were committed: 551 present, 54 absent; eleven cases remain
unknown. 523 rows were inserted and 82 existing council rows updated. Presence
modes remain Unknown because physical modality was not reconstructed. Presence
does not assert full-meeting duration.

| Person | Present | Absent | Unknown |
|---|---:|---:|---:|
| Stew Young | 67 | 20 | 1 |
| Denise Blackwell | 83 | 5 | 0 |
| Matt Sahlstrom | 81 | 6 | 1 |
| Lanny Seaton | 82 | 4 | 2 |
| Norma Stewart | 79 | 7 | 2 |
| Lillian Szpak | 81 | 5 | 2 |
| Roger Wade | 78 | 7 | 3 |

Young's unknown is the May 25, 2020 standalone public hearing, whose roster lists
only Blackwell. Do not assume the other six members were required or absent.
Other omissions: Szpak on February 7, 2019; Seaton/Stewart/Wade on March 26, 2020;
Wade on July 29, 2021. These remain explicit holds in the source index.

On December 9, 2019 the opening roster lists Young absent, but page 3 expressly
records his arrival and subsequent chairing of adjournment. This is documented
presence at part of the meeting. The header/body clocks disagree; no arrival_time
or duration value was inferred. The source quote and page are retained.

April 20, 2020 was cancelled, according to the official notice. Only that meeting's
status and cancellation provenance were corrected; it is excluded from attendance.

## Evidence and verification

- `reviewed-rosters.json`: complete explicit presence/absence/unknown ledger,
  identity key, source exception and remaining holds.
- `source-index.json`: all 88 official source URLs, original SHA-256 hashes,
  relative archive paths, verified dates, cancellation evidence and holds.
- `verification.json`: application counts, protected-data hashes, shadow rollback,
  independent readback and backup hashes.
- Full before-images, correction plan and guarded rollback receipt are retained
  in the task workspace (`2026-10-19/task-17`); the backup manifest identifies their
  exact hashes. They are not replaced by a later idempotent apply.

The shadow rehearsal used the actual timestamp trigger function. The inverse
restored all original business fields and removed inserted rows. `updated_at`
continues to follow the existing audit trigger, including on a real rollback.
No production sequence was consumed by the shadow rehearsal.

Independent readback re-derived expectations from the visual ledger, re-hashed
original files, and checked all 605 rows. All 600 staff/other attendance rows were
unchanged, as were the other 88 meeting records and council memberships. Hashes
for 781 scoped votes, 27,896 transcript segments, all 96 memberships and all 348
people were unchanged within the correction transaction. A second apply made
zero changes. No votes, transcripts, person identities or service dates were edited.

## Reproduction and recovery

Run scripts with the existing pipeline Python environment and `PYTHONPATH` set
to `apps/pipeline`. Each command requires explicit input/output paths.

1. `prepare.py --before SNAPSHOT --repo REPO --output DIR` reads originals via
   the existing pipeline PDF reader, caches unchanged hashes and extracts geometry.
2. `build_plan.py --extracted DIR/roster-plan.json --reviewed reviewed-rosters.json
   --before SNAPSHOT --output PLAN` binds the reviewed finite ledger to source bytes.
3. `apply.py preflight|rehearse|apply --plan PLAN --before SNAPSHOT --receipt RECEIPT`
   performs the named operation. Rehearsal writes only temporary shadow tables.
   Apply checks stale rows, preserves non-targets, and persists a pending receipt
   before commit. After an uncertain commit, inspect/read back before retrying.
4. `verify.py --before SNAPSHOT --reviewed reviewed-rosters.json --repo REPO
   --output REPORT` independently checks production using a read-only transaction.
5. `apply.py rollback --plan PLAN --before SNAPSHOT --receipt APPLIED_RECEIPT`
   is the guarded inverse, only for an explicitly intended rollback. It refuses
   to overwrite target rows changed after the correction. Do not execute it as
   an ordinary verification step.

## Coverage limits

This correction covers the finite recorded corpus, not proof of every meeting
that ever occurred. The current official legacy archive's 2018-2020 term dates
matched the database. Complete 2021-2022 calendar availability remains unverified
because fresh eSCRIBE requests encountered a browser challenge; archived originals
were available for review. Earlier years have no stored recordings/transcripts.
No inference about attendance or conduct follows from missing media or rows.
