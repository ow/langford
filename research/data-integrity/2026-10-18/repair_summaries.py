"""Recover public source files and prepare reviewable summaries; never writes DB.

PYTHONPATH=apps/pipeline apps/pipeline/.venv/bin/python research/data-integrity/2026-10-18/repair_summaries.py recover
PYTHONPATH=apps/pipeline apps/pipeline/.venv/bin/python research/data-integrity/2026-10-18/repair_summaries.py propose
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from datetime import date

from dotenv import load_dotenv
load_dotenv('.env')
from supabase import create_client
from pipeline import config
from pipeline.scrapers.base import MunicipalityConfig, ScrapedDocument, ScrapedMeeting
from pipeline.scrapers.escribe import EscribeScraper
from pipeline.ingestion.summary import regenerate_meeting_summary
from pipeline.ingestion.ingester import MeetingIngester
from pipeline.ingestion.ai_refiner import refine_meeting_data
from pipeline.ai_provider import get_ai_config

OUT = Path(__file__).resolve().parent
IDS = list(range(389, 395))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('phase', choices=['recover', 'propose', 'refine'])
    args = p.parse_args()
    s = create_client(config.SUPABASE_URL, config.SUPABASE_SECRET_KEY or config.SUPABASE_KEY)
    meetings = s.table('meetings').select('id,title,meeting_date,archive_path,municipality_id,summary').in_('id', IDS).execute().data
    municipality = MunicipalityConfig.from_db_row(s.table('municipalities').select('*').eq('id', 1).single().execute().data)
    if args.phase == 'recover':
        scraper = EscribeScraper(municipality)
        evidence = []
        for meeting in meetings:
            src = s.table('source_meetings').select('id,source_id,raw').eq('ingested_meeting_id', meeting['id']).single().execute().data
            docs = [ScrapedDocument(**doc) for doc in src['raw']['documents'] if doc.get('category') in {'Agenda','Minutes'}]
            scraped = ScrapedMeeting(date=date.fromisoformat(meeting['meeting_date']), title=meeting['title'], documents=docs, meta=src['raw'])
            paths = scraper.download_documents(scraped, meeting['archive_path'])
            files = []
            for file in paths:
                path = Path(file)
                files.append({'path': str(path), 'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'url': Path(file+'.url').read_text() if Path(file+'.url').exists() else None})
            evidence.append({'meeting_id':meeting['id'],'source_meeting_id':src['id'],'files':files})
            print(meeting['id'],len(files),'source documents')
        (OUT/'recovered-summary-sources.json').write_text(json.dumps(evidence,indent=2)+'\n')
    elif args.phase == 'refine':
        ingester = MeetingIngester(config.SUPABASE_URL, config.SUPABASE_SECRET_KEY or config.SUPABASE_KEY, config.GEMINI_API_KEY, municipality_id=1)
        cache = OUT/'structured-refinements'
        cache.mkdir(exist_ok=True)
        for meeting in meetings:
            target = cache/f"{meeting['id']}.json"
            if target.exists():
                continue
            agenda, minutes, _ = ingester.get_raw_texts(meeting['archive_path'])
            if len(minutes.strip()) < 100:
                raise ValueError(f"No usable official minutes for {meeting['id']}")
            result = refine_meeting_data(agenda, minutes, '', meeting_date=meeting['meeting_date'], canonical_names_context=', '.join(ingester._get_canonical_names()), active_council_members=ingester._get_active_council_members(meeting['meeting_date']))
            if result is None:
                raise RuntimeError(f"Structured extraction failed for {meeting['id']}")
            data = result.model_dump()
            if data.get('speaker_aliases') or data.get('transcript_corrections'):
                raise ValueError('Document-only extraction invented acoustic speaker evidence')
            target.write_text(json.dumps(data, indent=2)+'\n')
            print(meeting['id'],len(data['items']),'items',sum(len(x.get('motions',[])) for x in data['items']),'motions',flush=True)
    else:
        path = OUT/'summary-proposals.json'
        proposals = json.loads(path.read_text()) if path.exists() else []
        done = {x['meeting_id'] for x in proposals}
        for meeting in meetings:
            if meeting['id'] in done:
                continue
            result = regenerate_meeting_summary(s, meeting['id'], municipality_id=1, dry_run=True)
            result['expected_old_summary'] = meeting['summary']
            result['ai_config'] = get_ai_config('extraction')
            proposals.append(result)
            path.write_text(json.dumps(proposals,indent=2)+'\n')
            print(meeting['id'],result['summary'])


if __name__ == '__main__':
    main()
