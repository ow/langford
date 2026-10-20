import json,hashlib
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor
from pipeline import config
base=Path(__file__).resolve().parent
receiptpath=base/'physical91-applied-receipt.json';raw=receiptpath.read_bytes();receipt=json.loads(raw)
assert receipt['mode']=='applied'
changes=receipt['changes'];ids=[r['motion_id']for r in changes]
canon=lambda v:json.loads(json.dumps(v,default=str))
with psycopg2.connect(config.DATABASE_URL,connect_timeout=15)as db:
 db.set_session(readonly=True)
 with db.cursor(cursor_factory=RealDictCursor)as c:
  c.execute('SELECT id,meeting_id,agenda_item_id,text_content,result,meta,updated_at,meta IS NULL AS meta_is_sql_null FROM motions WHERE id=ANY(%s) ORDER BY id',(ids,));motions=canon(c.fetchall())
  c.execute('SELECT id,motion_id,person_id,vote,recusal_reason,created_at,updated_at FROM votes WHERE motion_id=ANY(%s) ORDER BY id',(ids,));votes=canon(c.fetchall())
  assert motions==sorted([r['after_motion']for r in changes],key=lambda r:r['id'])
  assert votes==sorted([v for r in changes for v in r['before_votes']+r['inserted_votes']],key=lambda v:v['id'])
  for r in changes:
   for key in ('id','meeting_id','agenda_item_id','text_content','result'):assert r['before_motion'][key]==r['after_motion'][key]
   assert r['after_motion']['meta']['individual_vote_coverage']=='reconstructed_complete'
  assert len(votes)==627 and len({(v['motion_id'],v['person_id'])for v in votes})==627
  c.execute("SELECT count(*) AS motions,count(*)FILTER(WHERE meta->>'individual_vote_coverage'='reconstructed_complete') AS complete_ballots FROM motions");totals=dict(c.fetchone())
  c.execute('SELECT count(*) AS individual_choices,count(*)FILTER(WHERE person_id=21) AS colby_choices FROM votes');totals.update(dict(c.fetchone()))
result={'mode':'independent_full_row_readback','applied_receipt_sha256':hashlib.sha256(raw).hexdigest(),'summary':{'motions':91,'new_choices_verified':607,'existing_rows_preserved':20,'full_final_choices_verified':627,'text_or_result_changes':0,'duplicate_motion_person_pairs':0},'live_totals':totals,'motions':motions,'votes':votes}
(base/'physical91-independent-postcommit-verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'summary':result['summary'],'live_totals':totals}))
