# ViewRoyal.ai -- Data Pipeline

Python ETL pipeline that scrapes council meeting documents, diarizes video, and ingests structured data into Supabase.

## Setup

### Prerequisites

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) package manager

### Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase anon key |
| `SUPABASE_SECRET_KEY` | Supabase service role key |
| `GEMINI_API_KEY` | Google Generative AI key (used when selected AI provider is `gemini`) |
| `OPENAI_API_KEY` | OpenAI key (Phase 5 embeddings and AI generation when selected provider is `openai`) |
| `AI_PROVIDER` | Default AI provider: `gemini` or `openai` (defaults to `gemini`) |
| `EXTRACTION_AI_PROVIDER` / `EXTRACTION_AI_MODEL` | Optional override for meeting refinement and agenda/bylaw intelligence |
| `DOCUMENT_AI_PROVIDER` / `DOCUMENT_AI_MODEL` | Optional override for document PDF extraction |
| `PROFILE_AI_PROVIDER` / `PROFILE_AI_MODEL` | Optional override for topic/stance/profile generation |
| `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` | Optional override for embeddings; defaults to OpenAI `text-embedding-3-small` |
| `VIMEO_TOKEN` | Vimeo API token (Phase 2 audio download) |
| `MOSHI_TOKEN` | Moshi push notification token (optional, update-mode alerts) |

## Quick Start

```bash
cd apps/pipeline
uv run python main.py --download-audio
```

This runs the full 5-phase pipeline: scrape, download audio, diarize, ingest, and embed.

## Pipeline Ops Console

The web app includes an internal admin console at `/admin/pipeline`. It tracks
upstream source meetings, queues pipeline jobs, and shows worker events/results.

Run the web app and worker from the project root:

```bash
pnpm dev:web
pnpm dev:worker
```

For a one-shot worker pass that processes at most one queued job:

```bash
pnpm dev:worker:once
```

The worker processes jobs from the `pipeline_jobs` table and writes progress to
`pipeline_run_events`. The helper script auto-sets `REQUESTS_CA_BUNDLE` to the
Homebrew CA bundle on macOS when available, which is required for Langford's
eSCRIBE TLS requests in some local Python environments.

Supported queue job types:

| Job type | What it does |
|----------|--------------|
| `preflight` | Check worker/database/API-key readiness without doing pipeline work |
| `discover_meetings` | Discover upstream source meetings and update `source_meetings` |
| `sync_documents` | Discover and download meeting PDFs into the archive |
| `ingest_meeting` | Ingest one archived meeting into Supabase |
| `extract_documents` | Run AI document extraction for one ingested meeting |
| `embed_content` | Generate missing embeddings for selected content tables |
| `diarize_meeting` | Run local diarization for one meeting folder |

Direct worker invocation is still available:

```bash
cd apps/pipeline
uv run python worker.py --once
uv run python worker.py --poll-interval 10
```

## Pipeline Phases

| Phase | What it does |
|-------|-------------|
| 1. Documents | Scrape agendas & minutes PDFs from CivicWeb (or Legistar/static HTML) |
| 2. Vimeo Download | Match meetings to Vimeo videos, download audio |
| 3. Diarization | Transcribe + speaker-diarize audio files locally (MLX on Apple Silicon) |
| 4. Ingestion | AI refinement via the configured provider: extracts agenda items, motions, votes, speaker aliases, key statements, summaries. Upserts to Supabase with smart change detection. |
| 5. Embeddings | Generate OpenAI `text-embedding-3-small` halfvec(384) vectors for semantic search |

Phase 4 uses **smart change detection**: it compares disk state (new agenda/minutes/transcript files) against DB flags (`has_agenda`, `has_minutes`, `has_transcript`) and automatically re-ingests meetings that have new data.

## CLI Reference

| Flag | Description |
|------|-------------|
| `--download-audio` | Download audio files (MP3) from Vimeo |
| `--include-video` | Download MP4 video files |
| `--videos-only` | Skip document scraping (Phase 1) |
| `--skip-diarization` | Skip audio processing (Phase 3) |
| `--skip-ingest` | Skip database ingestion (Phase 4) |
| `--skip-embed` | Skip embedding generation (Phase 5) |
| `--process-only` | Only diarize existing audio (skip Phases 1-2) |
| `--rediarize` | Re-run diarization reusing cached raw transcripts |
| `--ingest-only` | Only run Phase 4 (with change detection) |
| `--embed-only` | Only run Phase 5 |
| `--target <id\|path>` | Target a single meeting (force re-processes) |
| `--update` | Force update existing meetings (with `--ingest-only`) |
| `--extract-documents` | Run AI-powered document extraction on agenda PDFs (resumable) |
| `--batch` | Use Gemini Batch API for extraction when Gemini is selected; ignored for OpenAI |
| `--force` | Delete and reprocess all extraction data (use with `--extract-documents`) |
| `--generate-stances` | Generate AI stance summaries for all councillors using the configured provider (use `--target` for single person) |
| `--municipality <slug>` | Target a specific municipality (loads config from DB) |
| `--limit N` | Limit number of items to process (testing) |
| `--input-dir DIR` | Override archive directory |

## Selective Execution

```bash
# Only run ingestion with change detection (Phase 4)
uv run python main.py --ingest-only

# Force-update all meetings during ingestion
uv run python main.py --ingest-only --update

# Only generate embeddings for rows missing them (Phase 5)
uv run python main.py --embed-only

# Process audio -> ingest -> embed (skip scraping/download)
uv run python main.py --process-only

# Re-diarize cached transcripts -> re-ingest -> embed
uv run python main.py --rediarize --limit 5

# Target a single meeting by DB ID
uv run python main.py --target 42

# Target a specific municipality
uv run python main.py --municipality esquimalt
```

## Standalone Embeddings

```bash
# Embed all tables
uv run python -m pipeline.ingestion.embed --table all

# Embed a specific table
uv run python -m pipeline.ingestion.embed --table motions

# Re-embed everything from scratch
uv run python -m pipeline.ingestion.embed --table all --force
```

## AI Refinement

Phase 4 sends meeting documents (agenda PDF text + minutes PDF text + diarized transcript) to the configured AI provider for structured extraction. The AI refiner produces:

- **Meeting metadata** -- type, status, chair, attendees
- **Speaker aliases** -- maps Speaker_01 to "John Rogers" etc.
- **Transcript corrections** -- fixes ASR misspellings
- **Agenda items** -- titles, plain English summaries, debate summaries, discussion timestamps, categories
- **Key statements** -- typed statements (claim/proposal/objection/recommendation/financial/public_input) attributed to speakers
- **Motions** -- text, mover, seconder, vote results with individual votes
- **Key quotes** -- notable quotes from discussion

## Multi-Municipality Support

The pipeline supports multiple municipalities via a scraper abstraction layer:

| Scraper | Source | Municipalities |
|---------|--------|---------------|
| `CivicWebScraper` | CivicWeb portal | View Royal (active) |
| `LegistarScraper` | Legistar/InSite API | Esquimalt (planned) |
| `StaticHtmlScraper` | CSS selector-based | RDOS (planned) |

Scrapers are registered via `SCRAPER_REGISTRY` and selected based on the municipality's `source_config.type`. Each municipality gets its own archive directory and `municipality_id` foreign key throughout the schema.

## Testing

```bash
# Run all tests
uv run pytest

# Run a single test file with verbose output
uv run pytest tests/core/test_parser.py -v
```

## Project Structure

```
apps/pipeline/
  main.py                   Entry point
  pipeline/
    orchestrator.py          Pipeline orchestration and phase execution
    config.py                Configuration and environment loading
    paths.py                 File path management for archives
    utils.py                 Shared utilities
    scrapers/
      base.py                BaseScraper abstract class
      civicweb.py            CivicWeb portal scraper
      legistar.py            Legistar/InSite API scraper
      static_html.py         CSS selector-based HTML scraper
      bylaws.py              Bylaw scraping
    video/
      vimeo.py               Vimeo API client and audio download
    diarization/
      pipeline.py            Diarization orchestration
      inference.py           MLX model inference
      audio.py               Audio preprocessing
      clustering.py          Speaker clustering
      models.py              Model loading
    ingestion/
      ai_refiner.py          AI-powered meeting extraction
      ingester.py            Supabase upsert logic
      embed.py               Embedding generation (OpenAI)
      gemini_extractor.py    Document section extraction
      batch_extractor.py     Gemini Batch API extraction (Gemini-only)
      document_chunker.py    PDF document chunking
      image_extractor.py     Document image extraction
      audit.py               Change detection and audit
      matter_matching.py     Cross-meeting matter linking
    profiling/               Councillor stance generation
    update_detector.py       New meeting/document detection
    notifier.py              Push notification integration (Moshi)
  tests/                     pytest test suite
  scripts/                   One-off maintenance scripts (gitignored)
```
