"""Independent read-only postcommit verification of guarded source corrections."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib
import psycopg2
from psycopg2.extras import RealDictCursor
from pipeline import config
OUT=Path(__file__).parent;receiptpath=OUT/'source-correction-atomic-receipt.json';receipt=json.loads(receiptpath.read_text());ids=[r['motion_id']for r in receipt['changes']]
serial=lambda data:json.loads(json.dumps(data,default=str))
with psycopg2.connect(config.DATABASE_URL,connect_timeout=20)as db:
 with db.cursor(cursor_factory=RealDictCursor)as cur:
  cur.execute('SELECT id,text_content,result,meta,updated_at FROM motions WHERE id=ANY(%s)',(ids,));motions={r['id']:serial(dict(r))for r in cur.fetchall()};assert len(motions)==40
  cur.execute('SELECT id,motion_id,person_id,vote,updated_at FROM votes WHERE motion_id=ANY(%s) ORDER BY id',(ids,));votes=serial(list(cur.fetchall()));indexed={v['id']:v for v in votes}
  for change in receipt['changes']:
   assert motions[change['motion_id']]==change['after_motion'],'after_motion_differs'
   for before in change['before_votes']:assert indexed.get(before['id'])==before,'existing_vote_changed'
   for inserted in change['inserted_votes']:assert indexed.get(inserted['id'])==inserted,'inserted_vote_changed'
   expected={v['person_id']:v['vote']for v in change['after_meta']['ballot_reconstruction']['votes']}
   actual={v['person_id']:v['vote']for v in votes if v['motion_id']==change['motion_id']};assert actual==expected,'complete_choices_differ'
   assert change['after_meta']['source_motion_correction']['original_motion_text']==change['before_motion']['text_content']
  cur.execute("SELECT count(*) FILTER(WHERE (meta->>'individual_vote_coverage')='reconstructed_complete') AS complete_ballots FROM motions");totals=dict(cur.fetchone())
  cur.execute('SELECT count(*) AS vote_rows FROM votes');totals.update(dict(cur.fetchone()))
  cur.execute('SELECT id,status,meta FROM matters WHERE id=ANY(%s)',([m['id']for m in receipt['affected_matters']],));matters=serial(list(cur.fetchall()))
  assert all(m['status']=='Active'and not(m['meta']or{}).get('lifecycle_evidence')for m in matters),'affected_matter_lifecycle_changed'
result={'at':datetime.now(timezone.utc).isoformat(),'receipt_sha256':hashlib.sha256(receiptpath.read_bytes()).hexdigest(),'verified_motions':len(motions),'verified_choices':len(votes),
 'inserted_choices':sum(len(r['inserted_votes'])for r in receipt['changes']),'existing_vote_ids_preserved':[v['id']for r in receipt['changes']for v in r['before_votes']],
 'affected_matters_verified_active_without_terminal_evidence':[m['id']for m in matters],'totals':totals}
(OUT/'source-correction-postcommit-verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
