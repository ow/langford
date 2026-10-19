"""Revert only inserted ballots held after full-block ambiguity re-audit."""
import json
from pathlib import Path
from datetime import datetime,timezone
import psycopg2
from psycopg2.extras import RealDictCursor,Json
from pipeline import config
OUT=Path(__file__).parent
receipt_path=OUT/'named-vote-repair-receipt.json';receipt=json.loads(receipt_path.read_text())
held=set(json.loads((OUT/'named-vote-boundary-reaudit.json').read_text())['held_motion_ids'])
backup=OUT/'named-vote-repair-receipt-before-boundary-audit.json'
if not backup.exists():backup.write_text(json.dumps(receipt,indent=2))
count=0
with psycopg2.connect(config.DATABASE_URL,connect_timeout=15) as db:
 with db.cursor(cursor_factory=RealDictCursor) as cur:
  for change in receipt['changes']:
   if change['motion_id'] not in held or change.get('reverted_reason'):continue
   cur.execute('SELECT meta,updated_at FROM motions WHERE id=%s FOR UPDATE',(change['motion_id'],));current=cur.fetchone()
   if current['meta']!=change['after_meta'] or str(current['updated_at'])!=change['after_updated_at']:raise RuntimeError('Motion changed since insert; held rollback')
   for row in change['inserted_votes']:
    cur.execute('DELETE FROM votes WHERE id=%s AND motion_id=%s AND person_id=%s AND vote=%s AND updated_at=%s RETURNING id',(row['id'],row['motion_id'],row['person_id'],row['vote'],row['updated_at']))
    if not cur.fetchone():raise RuntimeError('Inserted vote changed; held rollback')
    count+=1
   cur.execute('UPDATE motions SET meta=%s WHERE id=%s',(Json(change['before_meta']),change['motion_id']))
   change['reverted_reason']='Complete source-block deduplication leaves ambiguous source occurrences';change['reverted_at']=datetime.now(timezone.utc).isoformat()
receipt['boundary_audit_reverted_votes']=count
receipt_path.write_text(json.dumps(receipt,indent=2));print('Reverted ambiguous inserted votes:',count)
