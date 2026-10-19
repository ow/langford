# Summary ownership clarification

The user confirmed the separate agent's new summary prompt, bulk regeneration, and canonical Markdown bullets are intentional. That agent owns `pipeline/ingestion/summary.py`, `summary_format.py`, and summary content. Do not restore prose or restart a competing regeneration.

The root briefly paused legacy PID 24355 during investigation, then resumed it after clarification. Our superseded restoration of 168 summaries is reversed using exact after-value comparisons, preserving subsequent writer changes. Before-values, summaries, hashes, and cache backups remain in the sibling overwrite/undo receipts. These records are an audit trail, not an instruction to rerun any repair script.

The pipeline recovery, failure propagation, source validation and transcript-preservation guards remain owned by this data-integrity task. Coordinate mixed-file staging with the root; do not overwrite the other agent's prompt or normalizer changes.
