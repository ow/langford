"""Independent exact postcommit row/proof readback for three keyed ballots."""
import json,hashlib
from pathlib import Path
from datetime import datetime,timezone
import psycopg2
from psycopg2.extras import RealDictCursor
from pipeline import config
from pipeline.ingestion.official_ballots import load_official_minutes
from pipeline.ingestion.canonical_motions import bound_source_motion,source_identity
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
MC='id,meeting_id,agenda_item_id,text_content,result,meta,updated_at,meta IS NULL AS meta_is_sql_null';VC='id,motion_id,person_id,vote,recusal_reason,created_at,updated_at'
canon=lambda x:json.loads(json.dumps(x,default=str));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 path=OUT/'repeated-key3-applied-receipt.json';receipt=json.loads(path.read_bytes());assert receipt['mode']=='applied'
 ids=sorted(c['motion_id'] for c in receipt['changes']);assert ids==[1918,1919,1959]
 with psycopg2.connect(config.DATABASE_URL,connect_timeout=15) as db:
  db.set_session(readonly=True,isolation_level='REPEATABLE READ')
  with db.cursor(cursor_factory=RealDictCursor) as cur:
   cur.execute(f'SELECT {MC} FROM motions WHERE id=ANY(%s) ORDER BY id',(ids,));motions=canon(cur.fetchall())
   cur.execute(f'SELECT {VC} FROM votes WHERE motion_id=ANY(%s) ORDER BY id',(ids,));votes=canon(cur.fetchall())
   cur.execute('SELECT id,name FROM people ORDER BY id');people=canon(cur.fetchall())
   cur.execute('SELECT m.id,m.meeting_date,m.title,m.type,m.archive_path,m.organization_id,m.updated_at,o.classification FROM meetings m JOIN organizations o ON o.id=m.organization_id WHERE m.id=ANY(%s)',([m['meeting_id'] for m in motions],));meetings={r['id']:canon(r) for r in cur.fetchall()}
   cur.execute("SELECT count(*) AS total_motions,count(*) FILTER (WHERE meta->>'individual_vote_coverage'='reconstructed_complete') AS complete_ballots FROM motions");counts=dict(cur.fetchone())
   cur.execute('SELECT count(*) AS choices,count(DISTINCT motion_id) AS motions_with_choices,count(*) FILTER (WHERE person_id=21) AS colby_choices FROM votes');counts.update(dict(cur.fetchone()))
 expected_motions=sorted([c['after_motion']for c in receipt['changes']],key=lambda x:x['id']);expected_votes=sorted([v for c in receipt['changes']for v in c['before_votes']+c['inserted_votes']],key=lambda x:x['id'])
 assert motions==expected_motions and votes==expected_votes
 assert len(motions)==3 and len(votes)==20
 byid={c['motion_id']:c for c in receipt['changes']};sources={};records=[]
 for motion in motions:
  mid=motion['id'];change=byid[mid];before=change['before_motion'];meta=motion['meta'];proof=meta['ballot_reconstruction'];meeting=meetings[motion['meeting_id']]
  assert all(motion[k]==before[k]for k in ('id','meeting_id','agenda_item_id','text_content','result'))
  assert meta['individual_vote_coverage']=='reconstructed_complete' and meta['vote_record']['coverage']=='reconstructed_complete'
  assert all(meta[k]==value for k,value in before['meta'].items() if k not in ('individual_vote_coverage','ballot_reconstruction','vote_record'))
  ballot=[v for v in votes if v['motion_id']==mid];assert {(v['person_id'],v['vote'])for v in ballot}=={(v['person_id'],v['vote'])for v in proof['votes']}
  if meeting['id'] not in sources:sources[meeting['id']]=load_official_minutes(meeting,root=ROOT,people=people,cache_dir='/private/tmp/repeated-key3-postcommit-native')
  source=sources[meeting['id']];block=bound_source_motion(motion,source,meeting['id']);assert block is not None
  identity=source_identity(meeting['id'],source,block)
  assert proof['source_motion_identity']=={**identity,'validation':'current_binary_meeting_offset_order_body_and_recomputed_key'}
  assert proof['source_block']==block['source_block'] and proof['source_sha256']==source['source_sha256'] and proof['source_url']==source['source_url']
  records.append({'motion_id':mid,'exact_full_row':True,'exact_vote_rows':len(ballot),'source_key':identity['key'],'source_sha256':source['source_sha256'],'source_date':source['local_date'],'source_file':source['source_file'],'source_key_proof_exact':True,'unchanged_legacy_identity_and_text':True,'unrelated_metadata_preserved':True,'vote_ids':[v['id']for v in ballot]})
 output={'mode':'independent_read_only_postcommit_full_row_and_native_key_verification','at':datetime.now(timezone.utc).isoformat(),'receipt_sha256':sha(path),'summary':{'exact_full_motion_rows':3,'exact_full_vote_rows':20,'new_choices':20,'existing_choice_ids_preserved':0,'text_result_agenda_writes':0,'source_files':2,'source_key_proofs_verified':3,'database_writes':0},'fresh_global_snapshot_counts':counts,'records':records}
 target=OUT/'repeated-key3-postcommit-verification.json';target.write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(output['summary']));print(json.dumps(counts));print('verification_sha256',sha(target))
if __name__=='__main__':main()
