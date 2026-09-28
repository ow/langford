# Speaker research workflow

This workflow works for any named participant in the public meeting archive. It separates three kinds of evidence:

1. **Minutes appearance:** the name occurs in official minutes. Review the excerpt and PDF to confirm it is a speaking entry, not a reference to someone else.
2. **Timed transcript:** a meeting transcript attributes speech to the person. The duration is the sum of attributed segment lengths, which can differ slightly from wall-clock turn length.
3. **Voice candidate:** local diarization suggests a speaker label. Similarity alone does not establish identity. A self-identification in the transcript plus the official minutes can support a provisional label; listen to the audio before treating it as verified for publication.

From `apps/pipeline`:

```bash
.venv/bin/python -m pipeline.speaker_research --name "Lisa Foxall" \
  --review-manifest ../../research/lisa-foxall-review.json
```

The command writes a Markdown report, a meeting CSV, a **turn-level CSV**, and a voice-candidate CSV under `research/`. The turn-level CSV has one row per attributed speaking block, including full text, timing, source links, speaker label, and review status. It can be filtered by date, meeting, duration, or text terms. `meeting_topic_hints` are meeting-level leads from the review manifest; they are not claims that every turn discusses those topics. All exported turns start as `needs_audio_review`, so the CSV is a research index rather than a set of publication-ready quotes or duration totals. Add `--alias "Alternate Name"` when the minutes use another form. `--municipality` selects another municipality slug after its records are added to this database. `--site-base-url` changes the meeting links in the report.

To process recordings that have no local transcript, add `--queue-missing`. This enqueues `transcribe_meeting` jobs; a queue worker started with `--job-types transcribe_meeting` generates local transcripts without modifying meeting summaries or speaker attributions. Re-run the report command as jobs finish. Inspect the voice-candidate CSV, which includes an audio path and sample timestamp for each suggested voice. Compare self-identification with official minutes, and record provisional `Speaker_N` labels in a per-person review manifest. Listen to the audio to verify identity and timing before publishing a duration claim. Keep claims intended for publication linked to the original minutes and recording.

Add `--watch-queue` to refresh the report and candidate CSV every two minutes until the person's queued transcription jobs finish. The report process exits when the queue is empty.

The Lisa Foxall pilot has all 54 named meeting recordings locally. The per-person manifest contains provisional speaker labels for meetings where the local transcript, official minutes, and cross-meeting voice comparison support attribution. Other recordings continue to be transcribed in the background.

To produce a repeatable attribution screen after refreshing the inventory:

```bash
.venv/bin/python -m pipeline.speaker_attribution_audit --name "Lisa Foxall" \
  --review-manifest ../../research/lisa-foxall-review.json \
  --inventory ../../research/lisa-foxall-speaking.csv \
  --turns ../../research/lisa-foxall-speaking-turns.csv \
  --output ../../research/lisa-foxall-attribution-audit.csv
```

The audit compares each selected voice against a reference built from *other* meetings, checks for a likely self-introduction and minutes name match, and highlights speaker-label audio excluded from totals or long diarization segments. It does not listen to recordings or upgrade provisional turns to verified status. The excluded seconds column is blank for meetings whose existing archive transcript turns supersede local manifest turns.

For a difficult boundary, the manifest may contain `service_check` with a JSON `path`, `speaker_name`, and optional `include_windows` in absolute recording seconds. The saved response must contain `clip_start_seconds` and `response.segments` with speaker labels, text, and relative start/end times. The report uses the selected service segments instead of the local diarization blocks for that meeting and identifies them as `provisional_service_diarization`. Keep the original service response and the official recording link as evidence; a second machine transcription is still provisional.

To prepare short local clips for listening review of manifest entries, run:

```bash
.venv/bin/python -m pipeline.speaker_review_pack --name "Lisa Foxall" \
  --review-manifest ../../research/lisa-foxall-review.json
```

Open `research/lisa-foxall-audio-review/index.html` locally. The adjacent `review.csv` records each clip's time, speaker label, transcript opening, and official source links. The pack does not change review status automatically; update the manifest only after listening to the full relevant recording and checking boundaries.
