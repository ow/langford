"""Restore reviewed prose after a concurrent legacy bulk summarizer overwrote it.
Only exact observed summary values are replaced; other meeting fields untouched.
"""
from pathlib import Path
import json
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv('.env')
from supabase import create_client
from pipeline import config
OUT=Path(__file__).parent
s=create_client(config.SUPABASE_URL,config.SUPABASE_SECRET_KEY or config.SUPABASE_KEY)
rows=json.loads((OUT/'summary-overwrite-audit.json').read_text())
fifty=json.loads((OUT/'summary-50-applied.json').read_text())['after_summary']
receipts=[]
for row in rows:
    mid=row['id']; expected=fifty if mid==50 else row['reviewed_summary']
    if row['summary'] != expected:
        applied=s.table('meetings').update({'summary':expected}).eq('municipality_id',1).eq('id',mid).eq('summary',row['summary']).execute().data
        if len(applied)!=1:raise RuntimeError(f'Concurrent summary change {mid}; stop rather than overwrite')
    cache=Path(row['archive_path'])/'refinement.json'
    if not cache.is_absolute():cache=Path(config.BASE_DIR if hasattr(config,'BASE_DIR') else Path.cwd().parents[1])/cache
    synced=False
    if cache.exists():
        data=json.loads(cache.read_text())
        backup=OUT/'summary-overwrite-cache-backups'/f'{mid}.json';backup.parent.mkdir(exist_ok=True)
        if not backup.exists():backup.write_text(cache.read_text())
        if data.get('summary') in (row['summary'],expected):
            data['summary']=expected;cache.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');synced=True
    receipts.append({'id':mid,'before_summary':row['summary'],'after_summary':expected,'changed':row['summary']!=expected,'cache_synced':synced})
    (OUT/'summary-overwrite-restored.json').write_text(json.dumps(receipts,indent=2)+'\n')
current=s.table('meetings').select('id,summary').eq('municipality_id',1).in_('id',[r['id'] for r in rows]).execute().data
expected={r['id']:r['after_summary'] for r in receipts}
assert len(current)==len(expected)
assert all(r['summary']==expected[r['id']] for r in current)
(OUT/'summary-overwrite-restoration-verified.json').write_text(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'verified_count':len(current),'restored_count':sum(r['changed'] for r in receipts),'cache_synced':sum(r['cache_synced'] for r in receipts)},indent=2)+'\n')
print('Verified',len(current),'restored',sum(r['changed'] for r in receipts),'cache_synced',sum(r['cache_synced'] for r in receipts))
