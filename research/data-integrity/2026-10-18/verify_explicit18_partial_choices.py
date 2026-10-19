"""Exact independent readback of explicit partial choices; never asserts full coverage."""
from pathlib import Path
import json,hashlib
import psycopg2
from psycopg2.extras import RealDictCursor
from pipeline import config
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
raw=(OUT/'explicit18-partial-choice-applied-receipt.json').read_bytes();receipt=json.loads(raw);assert receipt['mode']=='applied';changes=receipt['changes'];ids=sorted(c['motion_id']for c in changes);assert len(ids)==9 and 2473 not in ids
plan_raw=(OUT/'explicit18-partial-choice-plan.json').read_bytes();assert hashlib.sha256(plan_raw).hexdigest()==receipt['plan_sha256'];plan={r['motion_id']:r for r in json.loads(plan_raw)['records']}
canon=lambda x:json.loads(json.dumps(x,default=str))
with psycopg2.connect(config.DATABASE_URL,connect_timeout=15)as db:
 db.set_session(readonly=True)
 with db.cursor(cursor_factory=RealDictCursor)as c:
  c.execute('SELECT id,meeting_id,agenda_item_id,text_content,result,meta,updated_at FROM motions WHERE id=ANY(%s) ORDER BY id',(ids,));motions=canon(c.fetchall())
  c.execute('SELECT id,motion_id,person_id,vote,recusal_reason,created_at,updated_at FROM votes WHERE motion_id=ANY(%s) ORDER BY id',(ids,));votes=canon(c.fetchall())
assert motions==sorted([c['after_motion']for c in changes],key=lambda r:r['id'])
assert votes==sorted([v for c in changes for v in c['before_votes']+c['inserted_votes']],key=lambda r:r['id'])
assert sum(len(c['inserted_votes'])for c in changes)==18
proof_count=0;sources=set();records=[]
for change in changes:
 original=plan[change['motion_id']];assert hashlib.sha256((ROOT/original['source_file']).read_bytes()).hexdigest()==original['source_sha256']
 motion=next(m for m in motions if m['id']==change['motion_id']);before=change['before_motion']
 assert all(motion[k]==before[k]for k in ('id','meeting_id','agenda_item_id','text_content','result'))
 assert motion['meta']['individual_vote_coverage']=='named_only'and motion['meta']['vote_record']['coverage']=='partial'
 prior=before['meta']or{};new=motion['meta'];assert all(new[k]==v for k,v in prior.items()if k not in ('individual_vote_coverage','vote_record'))
 old_record=prior.get('vote_record')or{};new_record=new['vote_record'];assert all(new_record[k]==v for k,v in old_record.items()if k not in ('coverage','source_verified_named_choices'))
 proofs=new_record['source_verified_named_choices'];old_proofs=old_record.get('source_verified_named_choices')or[];assert proofs[:len(old_proofs)]==old_proofs
 added=proofs[len(old_proofs):];expected={(v['person_id'],v['vote'])for v in change['inserted_votes']};assert {(p['person_id'],p['vote'])for p in added}==expected
 for proof in added:
  assert proof['source_sha256']==original['source_sha256']
  assert proof['evidence']=='explicit_named'and proof['vote']=='No'and proof['source_quote']
  assert proof['independent_review_sha256']==receipt['independent_review_sha256'];sources.add(proof['source_sha256']);proof_count+=1
 records.append({'motion_id':motion['id'],'inserted_vote_ids':[v['id']for v in change['inserted_votes']],'prior_vote_ids_preserved':[v['id']for v in change['before_votes']],'partial_coverage_only':True,'text_agenda_result_preserved':True,'prior_meta_sql_null':change['before_meta_is_sql_null']})
assert proof_count==18
result={'mode':'independent_full_row_readback_no_writes','receipt_sha256':hashlib.sha256(raw).hexdigest(),'summary':{'motions_exact_rows':9,'explicit_vote_rows':18,'full_ballot_claims':0,'original_source_hashes':len(sources),'text_result_agenda_writes':0,'database_writes':0},'records':records};f=OUT/'explicit18-partial-choice-postcommit-verification.json';f.write_text(json.dumps(result,indent=2)+'\n');print(result['summary']);print(hashlib.sha256(f.read_bytes()).hexdigest())
