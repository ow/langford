"""Read-only exact post-commit verification of every repaired ballot/choice."""
import json,hashlib
from pathlib import Path
from datetime import datetime,timezone
import psycopg2
from psycopg2.extras import RealDictCursor
from pipeline import config
OUT=Path(__file__).parent;receipt_path=OUT/'roster-source-applied-receipt.json';receipt=json.loads(receipt_path.read_text());freeze=lambda v:json.loads(json.dumps(v,default=str))
assert receipt['mode']=='applied'
ids=[c['motion_id'] for c in receipt['changes']]
with psycopg2.connect(config.DATABASE_URL,connect_timeout=15) as db:
 db.set_session(readonly=True,isolation_level='REPEATABLE READ')
 with db.cursor(cursor_factory=RealDictCursor) as cur:
  cur.execute('SELECT id,text_content,meta,updated_at FROM motions WHERE id=ANY(%s)',(ids,));motions={m['id']:freeze(m) for m in cur.fetchall()}
  cur.execute('SELECT id,motion_id,person_id,vote,updated_at FROM votes WHERE motion_id=ANY(%s) ORDER BY id',(ids,));votes=[freeze(v) for v in cur.fetchall()]
  expected=sorted([v for c in receipt['changes'] for v in c['before_votes']+c['inserted_votes']],key=lambda v:v['id']);assert votes==expected,'Exact stored choices differ from receipt'
  for c in receipt['changes']:
   m=motions[c['motion_id']];assert m['text_content']==c['after_text_content'] and m['meta']==c['after_meta'] and m['updated_at']==c['after_updated_at']
   actual={(v['person_id'],v['vote']) for v in votes if v['motion_id']==c['motion_id']};proof={(v['person_id'],v['vote']) for v in m['meta']['ballot_reconstruction']['votes']};assert actual==proof
  result={'at':datetime.now(timezone.utc).isoformat(),'receipt_sha256':hashlib.sha256(receipt_path.read_bytes()).hexdigest(),'verified_new_complete_ballots':receipt['summary']['new_ballots'],'verified_canonical_body_repairs':receipt['summary']['canonical_body_repairs'],'verified_inserted_choices':sum(len(c['inserted_votes']) for c in receipt['changes']),'preserved_existing_choices':sum(len(c['before_votes']) for c in receipt['changes']),'exact_proof_choice_agreement':len(motions),'row_ids_values_timestamps_verified':len(votes),'role_bound_mayor_cases':[c['motion_id'] for c in receipt['changes'] if any(e.get('role_binding') for e in c['after_meta']['ballot_reconstruction']['presence_events'])]}
  (OUT/'roster-source-applied-verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
