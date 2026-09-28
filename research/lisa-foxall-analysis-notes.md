# Lisa Foxall speaking analysis — working notes

Updated 2026-09-28. This is a research inventory from public Langford council records, not a verified quotation or a complete lifetime speaking total.

## Current coverage

- Official minutes name L. Foxall in **54 meetings** in the archive. All 54 recordings and local transcripts are processed, with **0 transcription jobs remaining**.
- All 54 meetings have provisional timed speech: **131 speaking blocks totaling 153.7 minutes** (9,224.65 seconds). This sums diarized speech segments, not elapsed time at the microphone. The five meetings with pre-existing named transcript matches contribute 13.3 minutes; manually attributed local and service-checked blocks contribute 140.4 minutes.
- By year: 2023 **58.7 min** in 21 meetings; 2024 **39.5 min** in 15; 2025 **45.3 min** in 14; 2026 **10.3 min** in 4. The archive search covers these 54 minutes entries, not every public appearance she has made.

## Attribution checks I performed

For each of the 54 selected meetings, I compared its selected diarized voice with a voice reference built from the *other* meetings. The selected voice ranked first within each recording; the lowest similarity was 0.876. The official minutes contain the name in each case. An automatic scan found a likely spoken self-introduction in 48 of 54. The six misses are 2023-03-07 (the name is rendered “Elle Foxell”), 2024-04-15 (the chair calls Foxall by name, then the speaker says “Lisa from Langford”), 2024-06-25, 2024-11-05, 2024-11-19 (the service transcription renders the name as “Vauxhall”), and 2025-05-05 (the name is partly garbled in the transcript). The local text, minutes, and voice comparison still support provisional attribution. These checks do **not** replace listening to the original audio.

I excluded same-label fragments that made the timed sum less defensible:

- [2023-06-05 minutes](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=6229): a second diarized transcription with a known-speaker reference independently identifies the main speech and its interruptions. Its earlier short fragments were not confidently matched to her and remain excluded.
- [2023-08-21 minutes](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=7284): the local model assigned the chair's introduction to her second turn. A service check places that turn at 7936.5–8239.0 seconds and separates the chair; the earlier parking remarks remain timed from the local recording.
- [2024-11-05 minutes](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=11863): an isolated “Wow” outside the identified turns was removed.
- [2024-11-19 minutes](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=12086): the first local block included the preceding speaker and chair. A known-speaker service check starts her speech at 3011.6 seconds; her later self-identified turn uses local diarization.
- [2024-12-03 minutes](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=12301): one long local ASR segment mixed the preceding speaker and chair with Foxall's introduction. A known-speaker service check attributes 172.3 seconds to her from 3618.8–3799.6 seconds, excluding the preceding speaker.
- [2024-12-17 minutes](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=12394): one local 86-second ASR segment joins the preceding speaker, the chair, and Foxall's introduction. A second diarized transcription with a known-speaker reference places her speech at 3295.9–3474.8 seconds and separates the other voices. Its 171.6 seconds of attributed speech replace the incomplete local count of 123.2 seconds.
- [2025-01-14 minutes](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=13135): an isolated fragment between speakers was removed.
- [2025-04-07 minutes](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=14297): a long local segment included the chair after the speaker's closing exchange. The service check separates the chair; it attributes 176.5 seconds to Foxall, including a brief reply that the service gave a separate speaker label during the interruption.

The [attribution audit](lisa-foxall-attribution-audit.csv) records the per-meeting voice rank, minutes match, self-introduction screen, timing source, excluded seconds, and boundary flags. The [service responses](lisa-foxall-service-check/) are preserved beside the [turn-level data](lisa-foxall-speaking-turns.csv), which carries provisional text, date, duration, and source links. Its `meeting_topic_hints` apply to a meeting, not necessarily to every turn in that meeting.

## What the current speeches cover

These are themes in the 54 timed meetings, with examples to open in the official record. They summarize topics she addressed, not independent findings about the truth of any statement made in the speech.

| Theme | Examples in the official minutes |
| --- | --- |
| Municipal budget, property tax, and development fees | [2023-05-01](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=5812), [2024-03-05](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=9261), [2025-02-21](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=13493) |
| Tree bylaw and land use | [2023-02-07](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=4495), [2024-11-19](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=12086) |
| Public speaking time, meeting rules, and consultation | [2023-07-24](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=7014), [2023-11-21](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=8952), [2024-05-06](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=10208) |
| Policing, RCMP facilities, and public safety | [2023-11-21](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=8952), [2025-05-05](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=14404) |
| Recreation facilities and the YMCA purchase | [2024-12-03](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=12301), [2024-12-17](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=12394) |
| Downtown development and transportation | [2023-05-18](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=5884), [2025-03-04](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=13537) |

For analysis, filter the turn CSV by date or text term and follow its minutes and official recording links. Do not add topic durations by summing every turn tagged with a meeting topic: multi-topic speeches would be counted more than once. Precise time *by topic* requires splitting and checking the relevant turn boundaries.

## Remaining limits

The source audio has not been independently listened to in this pass, so identity, exact words, and the start and end of individual turns remain provisional. The local ASR has occasional mangled names and conflated speakers. The independent service checks improve several difficult boundaries but are still machine outputs. The 153.7-minute figure is the **provisional captured amount** across the 54 named meetings, and can undercount speech if the minutes omit appearances or the models miss short turns. It can also overcount if a merged segment includes another voice. It should not be published as an exact verified total. Any quotation or allegation for a public site needs a final check against the official recording in context.
