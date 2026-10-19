"""Controlled six-meeting metadata repair; preserves existing transcript records.

Requires all six locally reviewed structured refinements and summary proposals.
No media download, ASR, diarization, or embedding calls.
"""
from pathlib import Path
import hashlib
import json
from dotenv import load_dotenv
load_dotenv('.env')
from supabase import create_client
from pipeline import config
from pipeline.ingestion.ingester import MeetingIngester
from pipeline.ingestion.ai_refiner import MeetingRefinement

OUT=Path(__file__).resolve().parent
IDS=list(range(389,395))
s=create_client(config.SUPABASE_URL,config.SUPABASE_SECRET_KEY or config.SUPABASE_KEY)
proposals={x['meeting_id']:x for x in json.loads((OUT/'summary-proposals.json').read_text())}
prepared={mid:MeetingRefinement.model_validate(json.loads((OUT/'structured-refinements'/f'{mid}.json').read_text())).model_dump() for mid in IDS}
for source in json.loads((OUT/'recovered-summary-sources.json').read_text()):
    for file in source['files']:
        if hashlib.sha256(Path(file['path']).read_bytes()).hexdigest() != file['sha256']:
            raise RuntimeError(f"Official source changed since review: {file['path']}")
ingester=MeetingIngester(config.SUPABASE_URL,config.SUPABASE_SECRET_KEY or config.SUPABASE_KEY,config.GEMINI_API_KEY,municipality_id=1)
backups=OUT/'six-meeting-before';backups.mkdir(exist_ok=True)

def segments(mid):
    rows=[]
    while True:
        batch=s.table('transcript_segments').select('id,meeting_id,person_id,start_time,end_time,text_content,speaker_name,attribution_source,is_verified').eq('meeting_id',mid).order('id').range(len(rows),len(rows)+999).execute().data
        rows.extend(batch)
        if len(batch)<1000:return rows

def digest(rows):return hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()

receipt_path=OUT/'six-meeting-applied.json'
receipts=json.loads(receipt_path.read_text()) if receipt_path.exists() else []
done={x['meeting_id'] for x in receipts}
for mid in IDS:
    if mid in done:continue
    meeting=s.table('meetings').select('*').eq('id',mid).eq('municipality_id',1).single().execute().data
    if meeting['summary'] is not None:
        raise RuntimeError(f'Meeting {mid} summary changed; stop before overwriting')
    for table in ['agenda_items','motions','documents']:
        if s.table(table).select('id',count='exact',head=True).eq('meeting_id',mid).execute().count:
            raise RuntimeError(f'Meeting {mid} already has {table}; stop before destructive replacement')
    before=segments(mid)
    if not before:raise RuntimeError('Expected existing transcripts')
    (backups/f'{mid}-meeting.json').write_text(json.dumps(meeting,indent=2)+'\n')
    (backups/f'{mid}-transcripts.json').write_text(json.dumps(before,indent=2)+'\n')
    refined=prepared[mid]
    refined['summary']=proposals[mid]['summary']
    if refined.get('speaker_aliases') or refined.get('transcript_corrections'):
        raise RuntimeError('Document-only repair must not propose acoustic identity changes')
    result=ingester.process_meeting(meeting['archive_path'],precomputed_refinement=refined,force_update=False,force_refine=False)
    if not result or result.get('meeting_id') != mid:raise RuntimeError(f'Ingestion did not complete for expected meeting {mid}: {result}')
    after=segments(mid)
    if after != before:raise RuntimeError(f'Transcript invariant changed for {mid}; stop immediately')
    counts={table:s.table(table).select('id',count='exact',head=True).eq('meeting_id',mid).execute().count for table in ['agenda_items','motions','documents']}
    current=s.table('meetings').select('id,summary,has_agenda,has_minutes,status').eq('id',mid).single().execute().data
    if current['summary'] != refined['summary']:raise RuntimeError('Summary write verification failed')
    receipts.append({'meeting_id':mid,'before_transcript_count':len(before),'after_transcript_count':len(after),'transcript_fields_sha256':digest(before),'after_transcript_fields_sha256':digest(after),'counts':counts,'meeting':current,'incomplete_attachment_extraction':True})
    receipt_path.write_text(json.dumps(receipts,indent=2)+'\n')
    print(mid,counts,'transcripts unchanged',len(after),flush=True)
