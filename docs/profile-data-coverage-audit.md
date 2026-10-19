# Profile statistics coverage audit — 2026-10-18

Live audit of Langford (municipality 1), prompted by implausible profile totals.

- `votes` has zero rows. Motion outcomes are present (3,624 motions), but an
  outcome such as CARRIED is not a record of how each councillor voted.
- All 338 cached refinements inspected have empty individual vote lists, across
  3,666 cached motions. None of the attendee arrays include Mayor/Councillor
  titles, so the legacy title-based Yes-vote fallback never runs. That fallback
  must not be used to reconstruct historical individual votes from CARRIED.
- Actual transcript rows cover 27 of 344 meetings, with records spanning
  2021-07-29 to 2026-06-29. `has_transcript` is set on 33 meetings, so the flag
  alone is not a reliable coverage measure. 1,506 of 5,742 segments have no person.
- Colby Harder's attributed speech totals 2.19 hours across 19 meetings in the
  last 12 months, plus 0.19 hours across two older meetings. These are partial
  recorded totals, not her tenure's complete speaking time. No duplicate Harder
  person identity was found.
- The default speaking window was 12 months while the main selector said Entire
  career. It now defaults to all available records; explicit speaking windows
  and term selection remain supported and labeled.
- The local archive contains 182 final transcript files (including shared media
  copies) with 200,620 segments. These figures are not unique meeting counts.

## Repairs in this change

Profiles show missing vote records as unavailable, label speech as recorded
speech, show contributing meeting counts and the selected speaking period, and
explain excluded transcripts/unidentified speech. The votes tab no longer claims
complete history or divides a zero total into percentages.

Normal ingestion previously prepared transcript rows only with `force_update`
(or dry run), so cached transcripts could remain absent from the database.
It now inserts segments when the meeting has none, while preserving existing
segments unless an explicit update was requested. Integration coverage reproduces
first-import failure and checks preservation on re-import.

## Remaining data work

Reconcile cached final transcripts with database meetings, shared media ranges,
and speaker identity confidence before a bounded backfill. Existing person
mappings must not be guessed merely to increase totals. No paid transcription
or historical re-extraction was triggered by this audit.

Individual voting records need a source-backed extraction/backfill from minutes,
with provenance and explicit handling of dissent, recusals and absences. Do not
convert every carried motion into an inferred unanimous vote. Review the legacy
Yes-vote fallback before enabling a vote backfill. No votes were manufactured
or backfilled by this change.

## Authorized cached-record recovery

`apps/pipeline/pipeline/backfill/records.py` now recovers cached transcript
words and times only. Every recovered row has `person_id=NULL`, its original
cached speaker label, and `CACHED_TRANSCRIPT_BACKFILL` provenance. From
`apps/pipeline/`:

```sh
uv run python -m pipeline.backfill.records --report /tmp/langford-backfill-plan.json
uv run python -m pipeline.backfill.records --report /tmp/langford-backfill-pilot.json --apply --limit 2
```

Each meeting commits independently under a row lock. Existing transcript rows,
linked person IDs, and their history remain intact. Shared recordings without
verified meeting boundaries are skipped. Source hashes are retained in meeting
metadata. Do not force destructive transcript or motion replacement to recover
missing cached words.

Legacy vote extraction and fuzzy motion matching have been removed. A saved
legacy plan containing ANY vote writes or named transcript rows is rejected
before the first write transaction, including mixed batches with otherwise safe
transcript rows. For official-source vote validation use the regular workflow:

```sh
uv run python main.py --ingest-only --target <meeting_id>
```

Existing-choice conflicts are held for an independently reviewed exact-source
correction; repeatedly retrying the old plan cannot repair them. The shared
ballot validator requires bounded formal decisions, dated eligible voting
members, actual departures/returns/recusals, applicable recording rules and
consistent outcomes. Explicit named choices and inferred choices retain distinct
provenance.

Alias-derived acoustic banks are no longer used by this recovery command.
Agreement among five alias-derived recordings demonstrates consistency, not
independent named identity. The regular strict identity producer may later
admit only independently proved source/audio turns through the private evidence
ledger. Unknown and ambiguous speakers stay unlinked. Existing linked rows are
never rewritten by cached recovery.

### Completed execution (historical)

The reports below describe the earlier execution. Their alias-consensus and
legacy named-vote methods are retired; current recovery follows the safeguards
above. Historical assignments are not newly certified by those old reports.

The authorized pilot and full recovery added **168,982 transcript segments across
154 previously empty meetings**, plus **154 explicitly named individual votes
on 60 motions**. All 5,742 pre-existing transcript rows were preserved. Live
transcript coverage is now 181 meetings, with 174,724 segments through September
28, 2026; 33,657 segments have a person attribution. All 154 recovered choices
have matching source evidence in motion metadata.

Of the new segments, 29,421 passed conservative voice attribution; the remaining
139,561 retain unknown identities. Colby Harder now has 11.26 recorded hours
across 127 meetings and 20 named vote records. These are partial recorded totals,
not a claim of complete career coverage. Repeating the full apply operation
created zero records. All 168,982 new transcript rows have unique
(meeting, start, end, text) tuples.

Audit plans are saved locally under `/private/tmp/langford-record-backfill-*.json`.
The implementation and source metadata, not those temporary files, are the
durable recovery mechanism. No transcription or language-model API was called.
