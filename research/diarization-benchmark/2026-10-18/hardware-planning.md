# Processing on the planned Mac Studio

The intended production processing host is a forthcoming Mac Studio with more
RAM. Its chip, GPU configuration and memory capacity are not yet specified.
Keep the web deployment on Cloudflare and run the Python media worker on the
Mac; the two communicate through the existing database and job queue.

## Observed constraints

The current test host has 32 GiB of unified memory and was also running other
applications and build work. During the first Community-1 attempt, macOS reported
a 6.5 GiB physical footprint, 6.7 GiB peak footprint and substantial paging for
that process. This is one in-progress observation, not a peak memory benchmark.
Host swap use cannot all be attributed to diarization.

That attempt was stopped after an exporter compatibility bug was discovered:
this pyannote version iterates annotations as `(segment, label)` pairs. The
replacement runner explicitly uses `itertracks(yield_label=True)`, checkpoints
the completed model output before JSON conversion, logs pipeline progress and
sets four PyTorch CPU threads. The interrupted attempt is excluded from final
completed-run throughput. Retain its paging observation as diagnostic evidence.

Senko completed acoustic diarization of the two full recordings in 21.34 and
16.52 seconds using CoreML; these timings exclude transcription and model
initialization. Its identity collisions still prevent treating every speaker
cluster as a named person. Extra RAM alone cannot resolve that identity issue.

OpenAI completed all 44 full-meeting chunks. Its reported runtimes include
transcription and diarization; parallel API wall time and summed request latency
are separate measures. Running on a larger Mac does not remove API charges or
remote service latency. The usage-based estimate for these 7.14 hours is about
US$9.20, excluding the separate diagnostic excerpt and downstream refinement.

## Operational recommendation pending the third engine's results

Use the Mac Studio as the persistent processing host. Start with one concurrent
media job; allow inexpensive document-only ingestion independently. Measure
resident/physical footprint, memory pressure, swap growth and throughput on two
real meetings before increasing media concurrency. Do not choose concurrency by
dividing total RAM by this one observed footprint: ASR, refinement, embeddings
and the operating system also need memory, and GPU/CPU bandwidth is shared.

Cache downloaded audio, acoustic segments and ASR separately. Reprocess only the
stage invalidated by a change, so a better speaker matcher need not trigger paid
transcription or regenerate summaries. Persist per-stage timings and retryable
job state; keep the worker able to resume after a restart.

The additional memory could reduce paging and fit more concurrent working sets.
It does not establish a particular speedup without knowing the chip and measuring
the same workload. The final engine recommendation must also account for named
speaker reliability, mixed-speaker ASR blocks and cost, not just throughput.
