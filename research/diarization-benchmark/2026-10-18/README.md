# Two-meeting diarization benchmark

Requested comparison: Senko, Pyannote Community-1 and OpenAI
`gpt-4o-transcribe-diarize`. This experiment never changes production rows or
cached source transcripts. `manifest.json` records the complete recordings and
held-out machine-enrolled reference sources. The requested three-engine comparison is incomplete: Community-1 was interrupted
before its first full-meeting output. See the [provisional recommendation](recommendation-provisional.md)
and [interruption evidence](community-interruption.json). No three-engine winner is claimed.

The user's intended processing host is a forthcoming Mac Studio with more RAM.
[Hardware planning](hardware-planning.md) distinguishes measured memory pressure,
local throughput, remote API cost and the limits of projecting these results to
that machine. Exact chip and RAM capacity are not yet known.

## Protocol

* Entire February 22, 2023 and December 3, 2024 council recordings: 25,707.5 seconds
  (7.14 hours). No excerpt is substituted for either complete meeting.
* Mono 16 kHz audio for local engines. OpenAI receives the same material encoded
  at 48 kbit/s MP3 in ten-minute requests, below its upload limit. This is a
  native-service workflow comparison, not a sample-identical codec experiment.
* The same four short reference voices are prepended to each complete recording,
  with marked boundaries and silence between them. Reference time is excluded
  from all meeting speech totals. All reference recordings are outside the two
  test meetings. Existing machine enrollment is evidence, not human ground truth.
* OpenAI also receives its native known-speaker references on every request.
  Anonymous API speaker labels are request-local, so clustering agreement is
  optimally matched separately within each ten-minute block for all engines.
* Local cluster identity is inferred from reference-prefix overlap. A reference
  needs >=80% of its detected speech in one cluster. If another reference puts
  >=50% of its speech in that same cluster, the shared identity is unresolved;
  no speaker gets its time credited merely for winning a close comparison.
* Local engines also share the existing cached ASR sentences to measure the
  downstream effect of timing gates. Their runtime excludes new ASR. OpenAI
  produces new text and diarization together, so its wall time is not a pure
  acoustic-model speed comparison.
* Report named speech, reference collisions, chunk-level speaker agreement,
  speech coverage and known difficult windows. Pairwise agreement is not DER or
  verified accuracy. No model is selected as ground truth to grade its rivals.
* Paid requests initially used three concurrent workers, then resumed with five
  after the latency diagnostic. No in-flight requests were discarded. There are
  no automatic retries. Successful
  responses are cached individually; reruns reuse those files. Two meetings only.

## Commands

From the repository root, using the existing pipeline Python:

```sh
PYTHONPATH=apps/pipeline apps/pipeline/.venv/bin/python research/diarization-benchmark/2026-10-18/run.py prepare
PYTHONPATH=apps/pipeline apps/pipeline/.venv/bin/python research/diarization-benchmark/2026-10-18/run.py senko
PYTHONPATH=apps/pipeline apps/pipeline/.venv/bin/python research/diarization-benchmark/2026-10-18/run.py openai
PYTHONPATH=apps/pipeline apps/pipeline/.venv/bin/python research/diarization-benchmark/2026-10-18/analyze.py
```

Community-1 uses a separate environment to avoid changing worker dependencies:

```sh
/private/tmp/langford-diarization-bench/venv/bin/python research/diarization-benchmark/2026-10-18/run.py community
```

Official model access requires Hugging Face login and acceptance of the model's
access conditions. Do not copy credentials into this directory. Raw audio and
reference clips are under `/private/tmp/langford-diarization-bench`; model results
and provenance are under `results/`. API keys are loaded from existing ignored
environment files and are never written into benchmark artifacts.
