# Site processing audit — Langford archive

Checked 2026-09-28 against the current Supabase database and local archive. This audits the **338 Langford meeting records indexed by the site**, dated 2016-01-18 through 2026-06-29. It does not establish that every meeting held by the municipality is in the catalog. Langford is the only municipality in this database.

| Year | Meetings | Agenda records | Minutes records | Summary text | Video URL | Local audio | Local diarized transcript | Site transcript |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2016 | 22 | 20 | 19 | 22 | 0 | 0 | 0 | 0 |
| 2017 | 21 | 21 | 18 | 21 | 0 | 0 | 0 | 0 |
| 2018 | 25 | 25 | 22 | 25 | 0 | 0 | 0 | 0 |
| 2019 | 27 | 25 | 23 | 27 | 0 | 0 | 0 | 0 |
| 2020 | 23 | 21 | 3 | 23 | 0 | 0 | 0 | 0 |
| 2021 | 19 | 19 | 19 | 19 | 16 | 17 | 1 | 1 |
| 2022 | 20 | 19 | 20 | 20 | 19 | 19 | 0 | 0 |
| 2023 | 48 | 48 | 47 | 48 | 38 | 39 | 22 | 2 |
| 2024 | 51 | 51 | 51 | 51 | 38 | 39 | 15 | 0 |
| 2025 | 47 | 47 | 47 | 47 | 38 | 39 | 14 | 1 |
| 2026 | 35 | 35 | 35 | 35 | 26 | 24 | 23 | 23 |
| **Total** | 338 | 331 | 304 | 338 | 175 | 177 | 75 | 27 |

A document count means a record in the `documents` table with category `Agenda` or `Minutes`; a file may be categorized otherwise or included in an agenda package. Summary text can be generated from an agenda and does not prove post-meeting transcription. Local diarized transcripts are audio-adjacent JSON files. Site transcripts are meetings with at least one `transcript_segments` database row.

At this check, the Langford job queue had **0 queued** and **0 running** jobs, alongside 635 succeeded, 11 failed, and 2 cancelled job records. An empty queue only says no work has been scheduled. There are 47 successful `transcribe_meeting` jobs. The `transcribe_meeting` worker writes local transcript JSON and does not ingest its segments into the site database.

Operationally, **102** meetings have local audio but no local diarized transcript; **48** have a local diarized transcript but no transcript rows on the site; **161** have no local audio. These buckets describe the current local/site state, not an estimate of recording availability in the official archive.

The separate `source_meetings` inventory has 239 entries: 23 cancelled, 213 extracted, 1 ingested, 2 postponed. It is not one-to-one with the older `meetings` table.

## Freshness and scope

The newest indexed site meeting is **2026-06-29**, while the separate source-discovery catalog stops at **2026-05-19**. The city has since posted a [September 8, 2026 council agenda notice](https://langford.ca/city-hall/public-notices/) and reported a [later council approval](https://langford.ca/city-and-westshore-chamber-strengthen-partnership-through-modernized-agreement-and-downtown-relocation/). The site is therefore behind the current official meeting record. The counts above describe the current database, not every meeting that has occurred.

The meeting list uses an OR-style readiness filter: agenda flag, minutes flag, transcript flag, or any summary. All 338 records have summary text, so all can appear in the list even though most have no transcript. Flags and document records also disagree: 30 meetings have a minutes flag without a `Minutes` document record; 5 have the reverse.

The earlier “all processed” statement referred to the 54-meeting Foxall research selection and its local transcription queue. It did not describe the site archive. The [per-meeting CSV](site-processing-audit.csv) gives every record and stage for follow-up.
