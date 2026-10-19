"""Read-only current-native key proposal for six independently reviewed identities."""
import json,hashlib
from pathlib import Path
from datetime import datetime,timezone
import psycopg2
from psycopg2.extras import RealDictCursor
from pipeline import config
from pipeline.ingestion.official_ballots import load_official_minutes
from pipeline.ingestion.canonical_motions import source_identity,bound_source_motion
from pipeline.ingestion.vote_evidence import normalize_text
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
IDS=[326,1918,1919,1959,2458,2459]
MC='id,meeting_id,agenda_item_id,text_content,result,meta,updated_at,meta IS NULL AS meta_is_sql_null'
VC='id,motion_id,person_id,vote,recusal_reason,created_at,updated_at'
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
canon=lambda obj:json.loads(json.dumps(obj,default=str))
def main():
 review_file=OUT/'legacy36-source-only-correction-plan.json';triage_file=OUT/'legacy-source-identity-triage-v2.json'
 review=json.loads(review_file.read_bytes());triage=json.loads(triage_file.read_bytes())
 reviewed={r['motion_id']:r for r in review['reviews'] if r['motion_id'] in IDS}
 proposed={r['motion_id']:r for r in triage['proposals'] if r['motion_id'] in IDS}
 assert sorted(reviewed)==IDS and all(r['identity_verified'] and r['status']=='verified_repeated_formal_identity_needs_source_key_binding_not_text_rewrite' for r in reviewed.values())
 with psycopg2.connect(config.DATABASE_URL,connect_timeout=15) as db:
  db.set_session(readonly=True,isolation_level='REPEATABLE READ')
  with db.cursor(cursor_factory=RealDictCursor) as cur:
   cur.execute(f'SELECT {MC} FROM motions WHERE id=ANY(%s) ORDER BY id',(IDS,));motions=canon(cur.fetchall())
   cur.execute(f'SELECT {VC} FROM votes WHERE motion_id=ANY(%s) ORDER BY id',(IDS,));votes=canon(cur.fetchall())
   cur.execute('SELECT m.id,m.meeting_date,m.title,m.type,m.archive_path,m.organization_id,m.updated_at,o.classification FROM meetings m JOIN organizations o ON o.id=m.organization_id WHERE m.id=ANY(%s) ORDER BY m.id',([m['meeting_id'] for m in motions],));meetings={r['id']:canon(r) for r in cur.fetchall()}
   cur.execute('SELECT id,name FROM people ORDER BY id');people=canon(cur.fetchall())
 changes=[]
 for old in motions:
  mid=old['id'];p=proposed[mid];verified=reviewed[mid];witness=p['candidates'];assert len(witness)==1;witness=witness[0]
  expected={'id':mid,'meeting_id':p['meeting_id'],'agenda_item_id':p['agenda_item_id'],'text_content':p['original_motion_text'],'result':p['stored_result']}
  assert all(old[key]==value for key,value in expected.items()),(mid,'live original identity differs')
  meeting=meetings[old['meeting_id']]
  source=load_official_minutes(meeting,root=ROOT,people=people,cache_dir='/private/tmp/repeated-motion-current-native')
  assert not source.get('error'),(mid,source.get('error'))
  assert source['source_sha256']==witness['source_sha256']==verified['source_sha256']
  assert source.get('source_classification')=='Council',(mid,'native Council scope not proven')
  assert source.get('local_date') and abs((datetime.fromisoformat(source['local_date'])-datetime.fromisoformat(meeting['meeting_date'])).days)<=1,(mid,'native source date not bound')
  assert source.get('source_url')==witness['source_url'],(mid,'primary source URL changed')
  matches=[b for b in source['blocks'] if normalize_text(b['source_block'])==normalize_text(witness['source_block']) and normalize_text(b['motion_text'])==normalize_text(witness['raw_motion_text'])]
  assert len(matches)==1,(mid,'current unique entire source witness not found',len(matches))
  block=matches[0];assert normalize_text(old['text_content'])==normalize_text(block['motion_text']) and old['result']==block['result']
  identity=source_identity(old['meeting_id'],source,block)
  prior=(old['meta'] or {}).get('canonical_source_motion') or {}
  if prior:
   identity['previous_keys']=sorted(set(prior.get('previous_keys',[])+([prior['key']] if prior.get('key') and prior['key']!=identity['key'] else [])))
   identity['previous_sources']=(prior.get('previous_sources',[])+([prior] if prior.get('key') and prior['key']!=identity['key'] else []))[-8:]
  metadata={**(old['meta'] or {}),'canonical_source_motion':identity,'canonical_identity_review':{'method':'independent_entire_formal_witness_and_agenda_actor_identity','review_sha256':sha(review_file),'review_file':review_file.name,'source_key_recomputed_with_current_parser':True}}
  assert bound_source_motion({**old,'meta':metadata},source,old['meeting_id']) is block
  changes.append({'motion_id':mid,'before_motion':old,'before_votes':[v for v in votes if v['motion_id']==mid],'meeting':meeting,'after_meta':metadata,'independent_review':verified,'current_source_identity':identity,'verified_native_date':source['local_date'],'verified_source_classification':source['source_classification'],'reviewed_source_url':witness['source_url'],'frozen_prior_key':witness['key'],'source_body_occurrences':len(source['index'][normalize_text(block['motion_text'])])})
 assert sorted(c['motion_id'] for c in changes)==IDS
 deps=['canonical_motions.py','official_ballots.py','ballot_reconstruction.py','vote_evidence.py','committee_ballots.py','meeting_ballots.py','native_header_ocr.py','native_header_vision.swift']
 plan={'mode':'read_only_exact_six_metadata_binding_proposal','at':datetime.now(timezone.utc).isoformat(),'input_sha256':{review_file.name:sha(review_file),triage_file.name:sha(triage_file)},'code_sha256s':{str(Path('apps/pipeline/pipeline/ingestion')/n):sha(ROOT/'apps/pipeline/pipeline/ingestion'/n) for n in deps},'summary':{'metadata_updates':6,'text_writes':0,'agenda_relinks':0,'vote_writes':0,'existing_choices_preserved':len(votes),'no_ballot_eligibility_claim':True},'changes':changes}
 target=OUT/'repeated-six-source-key-binding-plan.json';assert not target.exists(),'Never overwrite reviewed plan';target.write_text(json.dumps(plan,indent=2)+'\n');print(json.dumps({'summary':plan['summary'],'plan_sha256':sha(target)}))
if __name__=='__main__':main()
