# Two-meeting diarization benchmark

Comparison of Senko, Pyannote Community-1 and OpenAI gpt-4o-transcribe-diarize on two entire council recordings totaling7.14 hours. Senko and all44 OpenAI requests are complete. Community-1 is running with full-recording global clustering and durable segmentation/embedding checkpoints. No paid cloud requests are repeated.

The exact protocol manifest, reference windows, source audio and person-level diagnostics are private. The active runner reads a content-pinned manifest under ignored `.private/research/diarization-benchmark/2026-10-19/`; raw outputs remain in ignored `results/`. The current public tree contains anonymous aggregate findings only. Earlier published raw reports remain in Git history.

Run the offline Community continuation with the existing isolated environment:

```sh
/private/tmp/langford-diarization-bench/venv/bin/python research/diarization-benchmark/2026-10-18/resume_community.py
```

Only one heavy local media job may run at a time on this32GiB host. The runner refuses duplicate execution and mismatched completed provenance. It requires locally provisioned source artifacts and model access; never put credentials in this directory.

After both full outputs complete, run the model-free aggregate analyzer:

```sh
apps/pipeline/.venv/bin/python research/diarization-benchmark/2026-10-18/analyze_completed.py
```

The analyzer refuses an incomplete three-engine comparison by default. Public output is `comparison-v2-aggregate.json`; raw model outputs and identity diagnostics stay ignored. Legacy entry points fail closed to prevent recreating public person-level research.

All engines share a40-second diagnostic reference prefix excluded from meeting totals; OpenAI also received its known-speaker interface. Those old alias/consensus enrollments are not independent identity truth. Anonymous agreement is measured on100ms frames with optimal label matching separately in ten-minute blocks. It is not accuracy or DER. Cloud anonymous labels are request-local; whole-meeting local speaker counts are not directly comparable.

Local acoustic runtime excludes fresh ASR; cloud runtime includes ASR. Cached-ASR sentence compatibility is not intrinsic timing accuracy because cloud native ASR boundaries differ. Source-backed direct identity admission and abstention remain separate from clustering. See [evaluation plan](evaluation-plan-v2.md), [status](resumption-status.json) and [hardware limits](hardware-planning.md).
