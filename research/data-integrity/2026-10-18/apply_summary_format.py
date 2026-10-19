"""Apply reviewed mechanical formatting only, with compare-and-set and rollback data."""
import json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv('.env')
from pipeline import config
from supabase import create_client

OUT=Path(__file__).resolve().parent
s=create_client(config.SUPABASE_URL,config.SUPABASE_SECRET_KEY or config.SUPABASE_KEY)
plan=json.loads((OUT/'summary-format-proposals.json').read_text())
receipt_path=OUT/'summary-format-applied.json'
receipts=json.loads(receipt_path.read_text()) if receipt_path.exists() else []
done={x['id'] for x in receipts if x.get('applied')}
for row in plan:
    if row['id'] in done:
        continue
    current=s.table('meetings').select('id,summary,archive_path').eq('id',row['id']).eq('municipality_id',1).single().execute().data
    if current['summary'] != row['summary']:
        raise RuntimeError(f"Meeting {row['id']} changed since review; stopped before overwrite")
    result=s.table('meetings').update({'summary':row['proposed_summary']}).eq('id',row['id']).eq('municipality_id',1).eq('summary',row['summary']).execute().data
    if not result:
        raise RuntimeError(f"Meeting {row['id']} changed concurrently; stopped")
    receipt={'id':row['id'],'before_summary':row['summary'],'after_summary':row['proposed_summary'],'applied':True,'cache_synced':False}
    receipts.append(receipt)
    receipt_path.write_text(json.dumps(receipts,indent=2)+'\n')
    cache=Path(current['archive_path'])/'refinement.json' if current.get('archive_path') else None
    if cache and cache.exists():
        data=json.loads(cache.read_text())
        if data.get('summary') == row['summary']:
            backups=OUT/'summary-cache-backups';backups.mkdir(exist_ok=True)
            (backups/f"{row['id']}.json").write_bytes(cache.read_bytes())
            data['summary']=row['proposed_summary']
            cache.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
            receipt['cache_synced']=True
            receipt_path.write_text(json.dumps(receipts,indent=2)+'\n')
    print(row['id'],'formatted',flush=True)
print('Applied',len(receipts),'summaries; no AI calls')
