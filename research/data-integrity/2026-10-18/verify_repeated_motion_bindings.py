"""Independent complete-row readback and fresh eligibility only; never writes DB."""
import json,hashlib
from pathlib import Path
from datetime import datetime,timezone
import psycopg2
from psycopg2.extras import RealDictCursor
from pipeline import config
from pipeline.ingestion.canonical_motions import bound_source_motion
from pipeline.ingestion.official_ballots import load_official_minutes
from pipeline.ingestion.meeting_ballots import evaluate_ballot
from pipeline.ingestion.vote_policy import refresh_vote_policy
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
MC='id,meeting_id,agenda_item_id,text_content,result,meta,updated_at,meta IS NULL AS meta_is_sql_null'
VC='id,motion_id,person_id,vote,recusal_reason,created_at,updated_at'
canon=lambda x:json.loads(json.dumps(x,default=str))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 receipt_file=OUT/'repeated-six-source-key-binding-applied-receipt.json';receipt=json.loads(receipt_file.read_bytes());assert receipt['mode']=='applied'
 ids=sorted(c['motion_id'] for c in receipt['changes']);assert ids==[326,1918,1919,1959,2458,2459]
 with psycopg2.connect(config.DATABASE_URL,connect_timeout=15) as db:
  db.set_session(readonly=True,isolation_level='REPEATABLE READ')
  with db.cursor(cursor_factory=RealDictCursor) as cur:
   cur.execute(f'SELECT {MC} FROM motions WHERE id=ANY(%s) ORDER BY id',(ids,));motions=canon(cur.fetchall())
   cur.execute(f'SELECT {VC} FROM votes WHERE motion_id=ANY(%s) ORDER BY id',(ids,));votes=canon(cur.fetchall())
   cur.execute('SELECT id,name FROM people ORDER BY id');people=canon(cur.fetchall())
   cur.execute('SELECT m.person_id,p.name,m.role,m.start_date,m.end_date,o.classification FROM memberships m JOIN people p ON p.id=m.person_id JOIN organizations o ON o.id=m.organization_id WHERE o.municipality_id=1');memberships=canon(cur.fetchall())
   mids=sorted({m['meeting_id'] for m in motions});cur.execute('SELECT m.id,m.meeting_date,m.title,m.type,m.archive_path,m.organization_id,m.updated_at,o.classification FROM meetings m JOIN organizations o ON o.id=m.organization_id WHERE m.id=ANY(%s) ORDER BY m.id',(mids,));meetings={r['id']:canon(r) for r in cur.fetchall()}
 assert motions==[c['after_motion'] for c in receipt['changes']],'Complete live motion rows differ'
 assert votes==sorted([v for c in receipt['changes'] for v in c['before_votes']],key=lambda v:v['id']),'Vote rows changed'
 policy=refresh_vote_policy(json.loads((ROOT/'apps/pipeline/pipeline/ingestion/policies/langford-voting.json').read_bytes()),Path('/private/tmp/repeated-motion-verification-policy.json'),datetime.now(timezone.utc).date().isoformat());policy['municipality_slug']='langford'
 sources={};records=[]
 for c,motion in zip(receipt['changes'],motions):
  before=c['before_motion'];mid=motion['id'];meeting=meetings[motion['meeting_id']]
  assert meeting==c['meeting']
  assert all(motion[k]==before[k] for k in ('id','meeting_id','agenda_item_id','text_content','result'))
  assert {k:v for k,v in motion['meta'].items() if k not in ('canonical_source_motion','canonical_identity_review')}=={k:v for k,v in (before['meta'] or {}).items() if k not in ('canonical_source_motion','canonical_identity_review')}
  if meeting['id'] not in sources:sources[meeting['id']]=load_official_minutes(meeting,root=ROOT,people=people,cache_dir='/private/tmp/repeated-motion-independent-readback')
  source=sources[meeting['id']];block=bound_source_motion(motion,source,meeting['id'])
  assert block is not None and block['source_block']==c['current_source_identity']['source_block']
  assert source['source_classification']=='Council' and source['source_url']==c['reviewed_source_url']
  assert source['local_date']==c['verified_native_date'] and abs((datetime.fromisoformat(source['local_date'])-datetime.fromisoformat(meeting['meeting_date'])).days)<=1
  ballot=evaluate_ballot(motion,{'status':'available','source':source,'meeting':{**meeting,'municipality_slug':'langford'},'people':people,'memberships':memberships,'policy':policy},[v for v in votes if v['motion_id']==mid])
  records.append({'motion_id':mid,'complete_motion_row_exact':True,'unrelated_metadata_preserved':True,'source_key':motion['meta']['canonical_source_motion']['key'],'source_sha256':source['source_sha256'],'source_date':source['local_date'],'native_body_occurrences':len(source['index'][__import__('pipeline.ingestion.vote_evidence',fromlist=['normalize_text']).normalize_text(motion['text_content'])]),'fresh_eligibility':ballot['status'],'hold_evidence':ballot if ballot['status']!='reconstructable_candidate' else None,'candidate':ballot if ballot['status']=='reconstructable_candidate' else None})
 output={'mode':'independent_read_only_full_postcommit_verification','at':datetime.now(timezone.utc).isoformat(),'receipt_sha256':sha(receipt_file),'summary':{'exact_full_motion_rows':6,'exact_vote_rows':len(votes),'source_files':len(sources),'metadata_only_updates_verified':6,'text_result_agenda_changes':0,'database_writes':0,'fresh_eligible_ballots':sum(r['fresh_eligibility']=='reconstructable_candidate' for r in records)},'records':records}
 path=OUT/'repeated-six-source-key-binding-postcommit-verification.json';path.write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(output['summary']));print('verification_sha256',sha(path));print([(r['motion_id'],r['fresh_eligibility']) for r in records])
if __name__=='__main__':main()
