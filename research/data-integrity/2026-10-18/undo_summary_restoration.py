"""Undo only our superseded prose restoration; preserve concurrent writer changes."""
from pathlib import Path
import json,hashlib
from dotenv import load_dotenv
load_dotenv('.env')
from supabase import create_client
from pipeline import config
from pipeline.paths import BASE_DIR
OUT=Path(__file__).parent
s=create_client(config.SUPABASE_URL,config.SUPABASE_SECRET_KEY or config.SUPABASE_KEY)
audit={r['id']:r for r in json.loads((OUT/'summary-overwrite-audit.json').read_text())}
receipts=[]
for row in json.loads((OUT/'summary-overwrite-restored.json').read_text()):
    restored=False
    if row['changed']:
        changed=s.table('meetings').update({'summary':row['before_summary']}).eq('municipality_id',1).eq('id',row['id']).eq('summary',row['after_summary']).execute().data
        restored=bool(changed)
    cache=Path(BASE_DIR)/audit[row['id']]['archive_path']/'refinement.json'
    backup=OUT/'summary-overwrite-cache-backups'/f"{row['id']}.json"
    synced=False
    if cache.exists() and backup.exists():
        current=json.loads(cache.read_text());before=json.loads(backup.read_text())
        if current.get('summary')==row['after_summary']:
            current['summary']=before.get('summary');cache.write_text(json.dumps(current,ensure_ascii=False,indent=2)+'\n');synced=True
    receipts.append({'id':row['id'],'our_write':row['changed'],'restored_newer_summary':restored,'concurrent_change_preserved':row['changed'] and not restored,'cache_summary_restored':synced,'newer_summary_sha256':hashlib.sha256(row['before_summary'].encode()).hexdigest()})
    (OUT/'summary-restoration-undone.json').write_text(json.dumps(receipts,indent=2)+'\n')
print('Reversed',sum(r['restored_newer_summary'] for r in receipts),'preserved concurrent',sum(r['concurrent_change_preserved'] for r in receipts),'cache restored',sum(r['cache_summary_restored'] for r in receipts),flush=True)
