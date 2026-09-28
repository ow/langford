# Lisa Foxall speaking analysis — working notes

Updated 2026-09-27. This is a research inventory from public Langford council records, not a verified quotation or a complete lifetime speaking total.

## Current coverage

- Official minutes name L. Foxall in **54 meetings** in the archive. All 54 local audio recordings are present.
- **41 meetings** currently have timed, attributed speech: **89 speaking blocks** totaling **105.6 minutes**. This is a provisional sum of diarized speech segments, not elapsed time at the microphone. The block count fell because a service check now combines several local fragments into one checked turn.
- The other **13 meetings** remain in the transcription queue at this update. Their speech is absent from the total.
- By year among timed meetings: 2023 **34.5 min** in 14 meetings; 2024 **33.5 min** in 13; 2025 **27.3 min** in 10; 2026 **10.3 min** in 4. These figures will rise as the queue finishes.

## Attribution checks I performed

For each of the 41 selected meetings, I compared its selected diarized voice with a voice reference built from the *other* meetings. The selected voice ranked first within each recording; the lowest similarity was 0.910. The official minutes contain the name in each case. An automatic scan found a likely spoken self-introduction in 37 of 41. The four misses are 2024-04-15 (the chair calls Foxall by name, then the speaker says “Lisa from Langford”), 2024-06-25, 2024-11-05, and 2025-05-05 (the name is partly garbled in the transcript). The local text, minutes, and voice comparison still support provisional attribution. These checks do **not** replace listening to the original audio.

I excluded same-label fragments that made the timed sum less defensible:

- [2023-06-05 minutes](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=6229): a second diarized transcription with a known-speaker reference independently identifies the main speech and its interruptions. Its earlier short fragments were not confidently matched to her and remain excluded.
- [2024-11-05 minutes](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=11863): an isolated “Wow” outside the identified turns was removed.
- [2024-12-17 minutes](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=12394): one local 86-second ASR segment joins the preceding speaker, the chair, and Foxall's introduction. A second diarized transcription with a known-speaker reference places her speech at 3295.9–3474.8 seconds and separates the other voices. Its 171.6 seconds of attributed speech replace the incomplete local count of 123.2 seconds.
- [2025-01-14 minutes](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=13135): an isolated fragment between speakers was removed.

The [attribution audit](lisa-foxall-attribution-audit.csv) records the per-meeting voice rank, minutes match, self-introduction screen, timing source, excluded seconds, and boundary flags. The [service responses](lisa-foxall-service-check/) are preserved beside the [turn-level data](lisa-foxall-speaking-turns.csv), which carries provisional text, date, duration, and source links. Its `meeting_topic_hints` apply to a meeting, not necessarily to every turn in that meeting.

## What the current speeches cover

These are themes in the currently timed material, with examples to open in the official record. They summarize topics she addressed, not independent findings about the truth of any statement made in the speech.

| Theme | Examples in the official minutes |
| --- | --- |
| Municipal budget, property tax, and development fees | [2023-05-01](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=5812), [2024-03-05](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=9261), [2024-05-06](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=10208) |
| Public speaking time, meeting rules, and consultation | [2023-11-21](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=8952), [2024-05-06](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=10208) |
| Policing, RCMP facilities, and public safety | [2023-11-21](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=8952), [2025-05-05](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=14404) |
| Recreation facilities and the YMCA purchase | [2024-12-17](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=12394) |
| Downtown development and transportation | [2023-05-18](https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=5884) |

For analysis, filter the turn CSV by date or text term and follow its minutes and official recording links. Do not add topic durations by summing every turn tagged with a meeting topic: multi-topic speeches would be counted more than once. Precise time *by topic* requires splitting and checking the relevant turn boundaries.

## Remaining limits

The source audio has not been independently listened to in this pass, so identity, exact words, and the start and end of individual turns remain provisional. The local ASR has occasional mangled names and conflated speakers. The independent service checks improve the two difficult boundaries but are still machine outputs. The 105.6-minute total is a **current captured amount**, with 13 recordings still pending. It should not be published as an exact total. Any quotation or allegation for a public site needs a final check against the official recording in context.
