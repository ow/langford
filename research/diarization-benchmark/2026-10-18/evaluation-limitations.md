# What this experiment can establish

All three runs use the two complete meeting recordings, with the same held-out voice clips prefixed to the audio. OpenAI additionally receives those clips through its native known-speaker interface. Enrollment is machine evidence, not independently hand-labelled ground truth. The existing consensus-based reference selection may favor characteristics already recognized by the current local pipeline. The benchmark tests this operational enrollment workflow, not an unconstrained model leaderboard.

Anonymous clustering is matched independently inside each ten-minute interval. Pairwise speaker agreement measures consistency between two outputs; it is neither accuracy nor diarization error rate (DER). A shared mistake can increase agreement. Only bounded, independently corroborated self-introduction windows provide direct identity contradictions; they do not validate every second assigned to that speaker.

Named acoustic seconds and accepted named ASR seconds answer different questions. An acoustic cluster may identify a voice while a long cached ASR sentence spans several people. Crediting the whole sentence to its dominant cluster inflates individual speaking totals. The current timing gate abstains on such sentences; finer turn or word alignment is required to recover supported time.

Local timings cover acoustic diarization, excluding new ASR and model initialization. OpenAI produces transcription plus speaker segments, and summed request latency differs from parallel wall time. All 44 paid chunks are cached; the usage-based cost estimate is not an invoice and excludes the separate diagnostic excerpt and later refinement. Local electricity and hardware costs were not measured.

The observed host is an Apple M4 with 32 GiB unified memory under other application/build load. A process paging snapshot from an interrupted attempt is diagnostic evidence, not a controlled memory or throughput benchmark. Additional Mac Studio RAM may relieve paging; its unspecified chip, GPU, memory bandwidth and future workload prevent claiming a speedup or safe concurrency level.

No production speaker identities, transcripts or profile totals are changed by this experiment.
