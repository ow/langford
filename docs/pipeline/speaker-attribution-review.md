# Machine speaker attribution: workflow review, 2026-10-18

The intended production system is machine-validated. Human listening is not a
required stage. Accepted machine evidence must record its method and provenance;
ambiguous cases can receive another machine pass or remain unresolved. The
legacy `is_verified` flag must not be silently redefined as model agreement.

## What actually runs

`worker.run_job` creates `Archiver`, which unconditionally constructs
`LocalDiarizer`. It runs Senko for acoustic speaker turns/192-dimensional CAM++
embeddings and Parakeet through `uvx parakeet-mlx>=0.4,<1` for ASR. Existing
transcript caches bypass that work. The diarizer can match a voice against the
`voice_fingerprints` table, but that table was empty at the previous production
audit. AI refinement supplies meeting-local name aliases. Ingestion uses those
aliases to assign person IDs and combines consecutive same-person statements.

The historical backfill is a separate path: exact cached/database centroid
anchors, three distinct recordings, similarity >= .90, margin >= .05, at least
five accepted held-out recordings per identity and no accepted identity conflict.
It additionally requires per-segment temporal overlap >= .90. It only fills empty
transcripts, so running it again cannot improve attribution on existing rows.

Lisa's seven cached difficult-clip checks used `gpt-4o-transcribe-diarize`, including
known-speaker reference audio. Their results were consumed by research reports,
not the regular worker. The research manifest also contains selected windows and
boundary corrections; a voice-model response alone did not generate that entire
workflow automatically. The earlier research's human-listening recommendation
describes its original status, not a requirement for the production policy.

## Confirmed implementation defects repaired in this pass

* Fingerprint matches replaced acoustic speaker keys with person names in saved
  transcripts. That broke the downstream join to speaker aliases and centroids.
  Speaker keys are now retained; display names have their own field.
* Normal ingestion compared speaker labels literally. `SPEAKER_1`, `Speaker_1`
  and `Speaker_01` did not all join. Ingestion and backfill now share key
  normalization.
* Temporal confidence used the largest single acoustic interval. A sentence
  spanning several regions from the same speaker could get a low score despite
  complete coverage. It now unions intervals per speaker without double counting,
  and separately records the strongest competing speaker's coverage.
* Consolidation bridged arbitrary gaps between same-speaker statements, counting
  the silence as speech. Only adjoining intervals are now consolidated.
* New caches preserve acoustic intervals and timing-policy metadata, allowing
  future timing repairs without repeating ASR or the acoustic-model pass.
* New acoustic metrics survive parsing. Normal ingestion and recovery now share
  the same temporal gate: at least 90% winning-voice coverage and at most 10%
  coverage by the strongest competitor. An AI name mapping cannot override a
  failing gate. Legacy imports without timing metrics retain their old behavior
  until an explicit repair pass; they have not become machine-validated retroactively.

Public-output and ingestion regression tests failed before these repairs and
pass afterward. They test identity persistence, temporal coverage, normalization,
gap-free duration accounting, rejection of competing voices and preservation on
normal re-import. The broader orchestrator suite still has an existing setup
failure: it patches `orchestrator.VimeoClient`, which no longer exists after the
video-client factory change. That unrelated suite was not rewritten here.

## Colby: measured remaining gap

Production read on October 18: 11.26 hours over 127 meetings. In meetings with an
attendance entry listing her, 33 lack transcripts. Those with transcripts contain
about 176 hours of speech without a person ID, shared across all speakers.

Within the 154 backfilled meetings, voices matching Colby's consensus anchors
cover 11.55 hours; the temporal gate accepted 8.88 and held back 2.67. The held-back
amount is a candidate pool, not additional established Colby speech. Some long
ASR blocks contain multiple people. Do not simply lower the threshold or add
2.67 to her total. Old caches do not preserve the acoustic intervals needed to
recompute this metric, so those need an acoustic pass or bounded service check.

## Model choice and recommended regular workflow

Candidates to evaluate on the same council excerpts:

1. Repaired Senko + Parakeet: existing Mac path, no per-minute API charge.
2. Pyannote Community-1 + existing ASR: a different local diarization pipeline;
   benchmark it rather than asserting it is better for Langford.
3. OpenAI `gpt-4o-transcribe-diarize`: hosted transcription and diarization, with
   existing evidence of useful boundary corrections in Lisa's difficult clips.

OpenAI accepts up to four known-speaker references of 2–10 seconds each. Anonymous
speaker letters are local to a request, not permanent identities across chunks.
That matters with seven council members, staff and public participants. It does
not expose diarization identity probabilities; do not invent confidence values.
Current official pricing pages checked in this pass did not explicitly list
this exact diarization model's per-minute estimate, so do not substitute ordinary
`gpt-4o-transcribe` pricing as a verified price for it.

The recommended architecture is one persistent person/reference registry with
source-meeting lineage, model/embedding version and machine enrollment evidence;
local processing followed by bounded OpenAI passes on ambiguous windows. Machine
acceptance should combine distinct-recording voice evidence, textual introductions
or addressed-speaker context where available, and timing agreement. A minutes
name occurrence or roster membership alone does not identify a particular voice.
Never compare embeddings across model spaces or promote a prediction into a new
independent seed without separate evidence.

Use Colby and Lisa excerpts including interruptions, long turns and competing
voices for evaluation. Hold reference recordings out of the target test. Measure
identity conflicts, unresolved duration and speaker-boundary agreement; more
attributed hours alone is not evidence of better accuracy. Two models agreeing
is useful machine evidence, not a calibrated probability of correctness.

A replacement should run in shadow mode first and report disagreements. Persist
original transcripts, model responses, input/reference hashes, cost usage and a
policy version. An attribution-only reconciliation should update matching rows
by ID without re-ingesting agenda items/motions, duplicating transcripts or
overwriting unrelated concurrent edits. It must also run for existing transcripts,
not only empty meetings. Missing meetings remain a separate coverage queue.

These initial repairs do not implement that complete validator or change the
deployed historical attributions. No hosted transcription calls, production
database changes, model switches, or UX edits were made during this review.

Sources checked: [Senko](https://github.com/narcotic-sh/senko),
[Community-1](https://huggingface.co/pyannote/speaker-diarization-community-1),
[OpenAI diarization](https://developers.openai.com/api/docs/guides/speech-to-text#speaker-diarization),
[OpenAI pricing](https://developers.openai.com/api/docs/pricing).
