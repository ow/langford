"""Regenerate only the reported repeated-title example from complete official sources."""
from pathlib import Path
import json
from dotenv import load_dotenv
load_dotenv('.env')
from pipeline import config
from pipeline.ingestion.summary import regenerate_meeting_summary
from supabase import create_client
OUT=Path(__file__).resolve().parent
s=create_client(config.SUPABASE_URL,config.SUPABASE_SECRET_KEY or config.SUPABASE_KEY)
receipt=OUT/'summary-50-applied.json'
if receipt.exists():
    print('Already applied; see receipt')
    raise SystemExit(0)
before=s.table('meetings').select('id,summary,archive_path').eq('id',50).eq('municipality_id',1).single().execute().data
proposal=regenerate_meeting_summary(s,50,municipality_id=1,dry_run=True)
(OUT/'summary-50-proposal.json').write_text(json.dumps({'before':before,'proposal':proposal},indent=2)+'\n')
result=s.table('meetings').update({'summary':proposal['summary']}).eq('id',50).eq('municipality_id',1).eq('summary',before['summary']).execute().data
if not result:raise RuntimeError('Meeting50 changed concurrently; proposed summary saved, no overwrite')
cache=Path(before['archive_path'])/'refinement.json'
cache_synced=False
if cache.exists():
    data=json.loads(cache.read_text())
    if data.get('summary')==before['summary']:
        (OUT/'summary-50-cache-before.json').write_bytes(cache.read_bytes())
        data['summary']=proposal['summary']
        cache.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
        cache_synced=True
receipt.write_text(json.dumps({'before':before,'after_summary':proposal['summary'],'cache_synced':cache_synced},indent=2)+'\n')
assert s.table('meetings').select('summary').eq('id',50).single().execute().data['summary']==proposal['summary']
print('Meeting50 summary regenerated and verified:',proposal['summary'])
