# Trusted native full transcriptions

`v1/manifest.json` is the separately versioned enrollment for exact, already-bound source occurrences. Its exact bytes are pinned by `native_transcriptions.py`; every other file is inventoried. The immutable minimized research candidates retain their original proposal flags and lineage. A database metadata field cannot enroll or replace a receipt.

This store permits an exact complete-body comparison only after the original canonical occurrence and complete current meeting claim inventory are re-proved. It does not assign a legacy record, create a motion, rewrite raw extraction, recover a skipped introduction, infer attendance, or bypass any ballot gate. Source-only review and implementation are distinct from approval to restore live text or deploy a worker.

Original complete PDF geometry, cleaned text and parsed source inventories are recomputed transiently and compared by hash. Only minimized formal source evidence and the five reviewed glyph crops are stored here. Full original PDFs and unrelated resident narrative must not be copied into this directory.

Raster and native-word evidence is pinned to the recorded PyMuPDF/MuPDF, Python, platform, wrapper and binary hashes. A mismatch holds; there is no OCR, model, tolerance or alternate renderer fallback. Revalidation and separate review are required to enroll changed evidence.

Restart ingestion workers after any code or store change. The loaded guard binds executable helpers, orchestration and the complete sorted store inventory; stale imported ingestion orchestration raises instead of advertising newer file bytes as loaded behavior. Finished ingestion receipts bind the exact verified post-write semantic claim inventory, not a pre-write fingerprint.
