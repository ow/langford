"""Independent full-row readback of applied CAC ballots; no mutation mode."""
from pathlib import Path
import json,hashlib
from collections import Counter
import psycopg2
from psycopg2.extras import RealDictCursor
from pipeline import config
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
receipt_path=OUT/'committee-ballot-applied-receipt.json';receipt_bytes=receipt_path.read_bytes();receipt=json.loads(receipt_bytes);assert receipt['mode']=='applied'
canon=lambda x:json.loads(json.dumps(x,default=str))
changes=receipt['changes'];ids=sorted(r['motion_id']for r in changes);assert len(ids)==len(set(ids))==81
with psycopg2.connect(config.DATABASE_URL,connect_timeout=15)as db:
 db.set_session(readonly=True)
 with db.cursor(cursor_factory=RealDictCursor)as c:
  c.execute('SELECT id,meeting_id,agenda_item_id,text_content,result,meta,updated_at FROM motions WHERE id=ANY(%s) ORDER BY id',(ids,));motions=canon(c.fetchall())
  c.execute('SELECT id,motion_id,person_id,vote,recusal_reason,created_at,updated_at FROM votes WHERE motion_id=ANY(%s) ORDER BY id',(ids,));votes=canon(c.fetchall())
expected_motions=sorted([r['after_motion']for r in changes],key=lambda r:r['id']);assert motions==expected_motions,'Full motion rows differ from receipt'
expected_votes=sorted([v for r in changes for v in r['before_votes']+r['inserted_votes']],key=lambda v:v['id']);assert votes==expected_votes,'Full vote rows differ from receipt'
assert len(votes)==634 and sum(len(r['inserted_votes'])for r in changes)==628 and sum(len(r['before_votes'])for r in changes)==6
old_byid={v['id']:v for r in changes for v in r['before_votes']};actual_byid={v['id']:v for v in votes};assert all(actual_byid[i]==v for i,v in old_byid.items())
extras=('member_observations','excluded_nonvoting_attendees','committee_chair_person_ids','committee_quorum_minimum_appointees','committee_policy_validation');records=[];sourcefiles=set()
for r in changes:
 motion=next(m for m in motions if m['id']==r['motion_id']);before=r['before_motion'];meta=motion['meta'];proof=meta['ballot_reconstruction']
 assert motion['text_content']==before['text_content']and motion['agenda_item_id']==before['agenda_item_id']and motion['meeting_id']==before['meeting_id']and motion['result']==before['result'],'Text/agenda/result identity changed'
 assert meta['individual_vote_coverage']=='reconstructed_complete'and meta['vote_record']['coverage']=='reconstructed_complete'
 assert proof['voting_body']=='community_advisory_committee'and proof['outcome_role']=='committee_guidance_or_recommendation'
 assert all(key in proof for key in extras),'Missing membership/policy/quorum proof'
 assert hashlib.sha256((ROOT/proof['source_file']).read_bytes()).hexdigest()==proof['source_sha256'],'Original source hash changed';sourcefiles.add(proof['source_file'])
 policy=proof['committee_policy_validation'];assert policy['status']=='verified_unchanged';assert policy['terms_sha256']=='dd4dd8b6b95b963ef7c964be676e11d1a4603e1bbb27f2b847467ecefe748182';assert policy['identity_section_sha256']=='3ff00718fd35dc916b9655f61dac7157dd2ae78fb123b426188af5f6ed0f9917';assert policy['enabled_from']<=proof['source_date']<=policy['enabled_through']
 assert proof['independent_review']['sha256']==receipt['independent_review_sha256']and proof['independent_review']['plan_sha256']==receipt['plan_sha256']
 actual={(v['person_id'],v['vote'])for v in votes if v['motion_id']==motion['id']};assert actual=={(v['person_id'],v['vote'])for v in proof['votes']},'Proof choices differ from actual rows'
 for observation in proof['member_observations']:
  assert observation['creates_term_interval']is False and observation['observed_date']==proof['source_date']and observation['source_sha256']==proof['source_sha256']
 records.append({'motion_id':motion['id'],'choice_count':len(actual),'preserved_vote_ids':[v['id']for v in r['before_votes']],'inserted_vote_ids':[v['id']for v in r['inserted_votes']],'full_row_equal_receipt':True,'text_agenda_result_preserved':True,'five_committee_proof_extras_present':True,'source_sha256':proof['source_sha256'],'policy_validated_as_of':policy['validated_as_of']})
result={'mode':'independent_full_row_readback_no_writes','receipt_sha256':hashlib.sha256(receipt_bytes).hexdigest(),'plan_sha256':receipt['plan_sha256'],'independent_review_sha256':receipt['independent_review_sha256'],'summary':{'motions_exact_rows':81,'votes_exact_rows':634,'new_vote_rows':628,'prior_vote_rows_exact_preserved':6,'original_sources_hash_verified':len(sourcefiles),'proof_extras_verified_all':81,'text_agenda_result_writes':0,'database_writes':0},'records':records}
f=OUT/'committee-ballot-postcommit-verification.json';f.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['summary']));print('verification_sha256',hashlib.sha256(f.read_bytes()).hexdigest());print('receipt_sha256',result['receipt_sha256'])
