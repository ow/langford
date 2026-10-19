# Provisional recommendation — third engine incomplete

Keep the fast local path as the default and improve identity validation and turn alignment before making a wholesale engine switch. Use OpenAI diarization as an independent diagnostic or targeted fallback, with identity checks before any profile totals change. This is provisional: Community-1 has not completed either full meeting, so the requested three-engine comparison remains unfinished.

The restarted Community-1 process disappeared after 841/1,342 embedding batches of the first meeting, at 3,356 seconds elapsed. Read-only process checks found no remaining runner; neither meeting had its completed-output checkpoint. The log contains no traceback, so the cause is unknown. No model was restarted, in accordance with the explicit handoff instruction. This incomplete attempt is excluded from completed-run throughput. See [interruption evidence](community-interruption.json).

## Complete results currently available

Both Senko and OpenAI processed the entire February 22, 2023 and December 3, 2024 recordings, totaling 7.14 hours. All 44 OpenAI requests completed and are cached.

| Meeting | Engine | Acoustic named Colby | Acoustic named Lisa | Runtime |
| --- | --- | ---: | ---: | --- |
| February 22, 2023 | Senko | 599.9 s | 180.4 s | 21.34 s, acoustic diarization only |
| February 22, 2023 | OpenAI | 674.4 s | 657.3 s | 22.58 min observed request wall span |
| December 3, 2024 | Senko | unresolved | 181.6 s | 16.52 s, acoustic diarization only |
| December 3, 2024 | OpenAI | 1,337.6 s | 175.6 s | 19.14 min observed request wall span |

These are assignments, not independently verified speaking totals. In the second meeting, Senko puts Colby and Kimberley reference clips into the same cluster. The collision gate correctly abstains instead of crediting the shared cluster to Colby. In the first meeting, Kimberley's strongest reference share is 79.3%, below the 80% acceptance threshold.

OpenAI recovers Colby-labelled time in the second meeting, but it also labels two separate public speakers as Scott Goodmanson in the first meeting. Cached ASR and independent new OpenAI ASR both corroborate those speakers' self-introductions as Malcolm McNaughton and Nicholas Joel. A known-speaker tag is therefore insufficient identity proof. Lisa's first-meeting assignment differs greatly between engines; her correctly recognised introduction alone does not validate every subsequent second assigned to her.

Anonymous speaker agreement between the completed engines is 78.4% and 75.5% on common speech after optimal matching separately in each ten-minute interval. This is consistency, not accuracy or DER. No engine serves as ground truth.

## The pipeline issue is broader than the acoustic engine

The 214.9-second cached Colby candidate at 8,615–8,830 seconds of the first meeting contains multiple voices. Senko assigns 66.2 seconds to Colby and 75.9 to Scott; OpenAI assigns 62.2 to Colby and 61.8 to Scott. Crediting that whole cached ASR block to Colby would inflate her speaking total.

For Senko on that meeting, the current timing gate accepts 399.0 seconds of Colby ASR text against 599.9 acoustic seconds. Lisa's accepted ASR time is 173.3 seconds in the first meeting and 122.6 in the second. Recover supported coverage through finer ASR/turn alignment and collision-aware identity matching; do not simply lower confidence thresholds or assign a whole mixed block to its dominant speaker.

## Costs and the intended Mac Studio

The measured OpenAI usage estimate is US$9.198 for these recordings, excluding the separate diagnostic excerpt and later refinement. It uses recorded token usage and the published US$2.50/M input and US$10/M output rates; it is not a billing receipt. [Official model pricing](https://developers.openai.com/api/docs/models/gpt-4o-transcribe-diarize). OpenAI supports up to four 2–10-second known-speaker references, so this native enrollment interface alone does not cover every councillor plus all public speakers. [Official file-transcription documentation](https://developers.openai.com/api/docs/guides/speech-to-text).

The local timings exclude new ASR and model initialization; OpenAI timings include both transcription and diarization. The current host is an Apple M4 with 32 GiB unified memory under other work. A prior interrupted Community-1 attempt showed approximately 6.7 GiB peak physical footprint and substantial paging, but that is not a controlled peak-memory or concurrency experiment. A larger Mac Studio may reduce paging; no speedup follows from RAM capacity alone when its chip and configuration are unspecified. Begin with one media job and measure complete end-to-end throughput and memory pressure before increasing concurrency.

## Required to finish the requested comparison

Run Community-1 persistently through both full recordings using the existing isolated environment and corrected checkpoint exporter, without repeating paid OpenAI work. Then rerun `analyze.py` and `identity_checks.py`, verify full audio coverage and source/version hashes, inspect named Colby/Lisa results and identity contradictions, and replace this provisional recommendation with the three-engine result. No production speaker labels or profile statistics have been changed by the benchmark.

See [protocol](README.md), [full comparison data](comparison.json), [identity checks](identity_checks.json), [code versions](benchmark-code-versions.json), and [evaluation limits](evaluation-limitations.md).
