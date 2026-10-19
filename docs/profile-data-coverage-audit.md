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
