"""Prepare/dry-run/apply exactly the independently reviewed 22 roster ballots.

No apply by default. --prepare captures exact current motion/vote/catalog rows.
Apply requires caller-bound immutable plan/review/before bytes and independent
approval of this script. All source/policy/identity guards replay live inside a
SERIALIZABLE transaction; existing choice IDs/values are never overwritten.
"""
import argparse,hashlib,json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor,Json,execute_values
from pipeline import config
from pipeline.ingestion.official_ballots import load_official_minutes
from pipeline.ingestion.meeting_ballots import evaluate_ballot
from pipeline.ingestion.vote_policy import refresh_vote_policy
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
PLAN=BEFORE=REVIEW=RECEIPT=PENDING=None
MC='motions.*,meta IS NULL AS meta_is_sql_null';VC='votes.*'
DEPS=['committee_ballots.py','official_ballots.py','ballot_reconstruction.py','vote_evidence.py','meeting_ballots.py','canonical_motions.py','native_header_ocr.py','native_header_vision.swift','vote_policy.py','operative_motion_body.py','roster_ocr.py','policies/langford-voting.json']
canon=lambda value:json.loads(json.dumps(value,default=str))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def capture(path):
 raw=path.read_bytes();return json.loads(raw),hashlib.sha256(raw).hexdigest()
def save(path,data):
 if path.exists():raise RuntimeError('Receipt already exists; never overwrite evidence')
 temp=path.with_suffix('.json.tmp');
 with temp.open('x')as f:
  f.write(json.dumps(canon(data),indent=2)+'\n');f.flush();__import__('os').fsync(f.fileno())
 temp.replace(path)
 fd=__import__('os').open(path.parent,__import__('os').O_RDONLY)
 try:__import__('os').fsync(fd)
 finally:__import__('os').close(fd)
def code_hashes():
 base=ROOT/'apps/pipeline/pipeline/ingestion'
 paths=[base/n for n in DEPS]+sorted((base/'data/roster-ocr').glob('*.json'))
 return {str(p.relative_to(ROOT)):sha(p)for p in paths}
def rows(cur,ids,lock):
 cur.execute(f'SELECT {MC} FROM motions WHERE id=ANY(%s) ORDER BY id'+(' FOR UPDATE'if lock else''),(ids,));motions=[canon(r)for r in cur.fetchall()]
 cur.execute(f'SELECT {VC} FROM votes WHERE motion_id=ANY(%s) ORDER BY id'+(' FOR UPDATE'if lock else''),(ids,));votes=[canon(r)for r in cur.fetchall()]
 mids=sorted({m['meeting_id']for m in motions})
 cur.execute('SELECT m.id,m.meeting_date,m.title,m.type,m.archive_path,m.organization_id,m.updated_at,o.classification FROM meetings m JOIN organizations o ON o.id=m.organization_id WHERE m.id=ANY(%s) ORDER BY m.id'+(' FOR SHARE OF m,o'if lock else''),(mids,));meetings=[canon(r)for r in cur.fetchall()]
 return motions,votes,meetings

def verify_after_rows(changes,motions,votes):
 """Reject unexpected trigger effects before a transaction can commit."""
 inserted=[v for c in changes for v in c['inserted_votes']]
 preserved=[v for c in changes for v in c['before_votes']]
 if len(changes)!=22 or len(inserted)!=147 or len(preserved)!=7:raise RuntimeError('Post-write exact row counts differ')
 expected_new=sorted(tuple(v)for c in changes for v in c['new_choices'])
 actual_new=sorted((v['motion_id'],v['person_id'],v['vote'])for v in inserted)
 if actual_new!=expected_new or len({v['id']for v in inserted})!=147:raise RuntimeError('Inserted choice rows differ from intended147')
 if votes!=sorted(preserved+inserted,key=lambda v:v['id']):raise RuntimeError('Complete preserved/inserted vote rows changed')
 actual={m['id']:m for m in motions}
 if len(actual)!=22 or set(actual)!={c['motion_id']for c in changes}:raise RuntimeError('Post-write motion inventory differs')
 for c in changes:
  after=actual[c['motion_id']]
  stable=lambda row:{k:v for k,v in row.items()if k not in ('meta','updated_at','meta_is_sql_null')}
  if stable(after)!=stable(c['before_motion']):raise RuntimeError('Non-metadata motion fields changed')
  if after['meta']!=c['after_meta'] or after['meta_is_sql_null']:raise RuntimeError('Stored metadata differs from intended proof')
  if after!=c['after_motion']:raise RuntimeError('Returned motion row differs from transaction readback')

def main():
 global PLAN,REVIEW,BEFORE,RECEIPT,PENDING,OUT
 cli=argparse.ArgumentParser(description=__doc__);modes=cli.add_mutually_exclusive_group();modes.add_argument('--prepare',action='store_true');modes.add_argument('--apply',action='store_true');modes.add_argument('--rollback',action='store_true')
 cli.add_argument('--bundle-dir',type=Path,required=True)
 cli.add_argument('--preflight-name',default='roster22-preflight-v2.json')
 for name in ['plan','review','before','receipt','script']:cli.add_argument('--expected-'+name+'-sha256')
 args=cli.parse_args()
 OUT=args.bundle_dir.resolve();PLAN=OUT/'roster22-reviewed-plan.json';REVIEW=OUT/'roster-independent-source-review.json';BEFORE=OUT/'roster22-current-before.json';RECEIPT=OUT/'roster22-applied-receipt.json';PENDING=OUT/'roster22-pending-receipt.json'
 if args.rollback:
  if args.expected_script_sha256!=sha(Path(__file__)):raise RuntimeError('Rollback requires exact reviewed script SHA')
  receipt,receipt_hash=capture(RECEIPT)
  if args.expected_receipt_sha256!=receipt_hash or receipt['mode']!='applied':raise RuntimeError('Exact applied receipt hash required')
  ids=[r['motion_id']for r in receipt['changes']]
  with psycopg2.connect(config.DATABASE_URL,connect_timeout=15)as db:
   db.set_session(isolation_level='SERIALIZABLE')
   with db.cursor(cursor_factory=RealDictCursor)as cur:
    live_motions,live_votes,_=rows(cur,ids,True)
    expected_motions=sorted([r['after_motion']for r in receipt['changes']],key=lambda r:r['id'])
    expected_votes=sorted([v for r in receipt['changes']for v in r['before_votes']+r['inserted_votes']],key=lambda v:v['id'])
    if live_motions!=expected_motions or live_votes!=expected_votes:raise RuntimeError('Rollback held: entire ballot changed independently')
    inserted=[v['id']for r in receipt['changes']for v in r['inserted_votes']]
    cur.execute('DELETE FROM votes WHERE id=ANY(%s)',(inserted,))
    for r in receipt['changes']:cur.execute('UPDATE motions SET meta=%s WHERE id=%s',(None if r['before_motion']['meta_is_sql_null'] else Json(r['before_motion']['meta']),r['motion_id']))
   save(OUT/'roster22-rollback-pending-receipt.json',{'receipt_sha256':receipt_hash,'restored_motion_ids':ids,'deleted_inserted_vote_ids':inserted})
   db.commit()
  save(OUT/'roster22-rollback-receipt.json',{'mode':'rolled_back','receipt_sha256':receipt_hash,'at':datetime.now(timezone.utc).isoformat(),'restored_motion_ids':ids,'deleted_inserted_vote_ids':inserted});print('Guarded rollback complete');return
 plan,plan_hash=capture(PLAN);review,review_hash=capture(REVIEW)
 selected=[r for r in plan['records']if r['status']=='reconstructable_candidate'];ids=sorted(r['motion_id']for r in selected)
 if len(selected)!=22 or sum(len(r['new_choices'])for r in selected)!=147 or len(set(ids))!=22:raise RuntimeError('Exact reviewed22/147 scope changed')
 if plan['independent_source_review_sha256']!=review_hash or ids!=sorted(review['recommended_motion_ids']):raise RuntimeError('Exact independently reviewed subset required')
 if set(ids)&{2903,2908,3219,3457,3459}:raise RuntimeError('Held or ambiguous source occurrence cannot enter subset')
 if review['recommended_choices']!=154 or review['expected_new_choices']!=147:raise RuntimeError('Reviewed choice counts differ')
 if plan['parent_batch_sha256']!=review['batch_sha256'] or plan['snapshot_sha256']!=review['snapshot_sha256']:raise RuntimeError('Independent review snapshot/parent differs')
 if plan['code_sha256s']!=code_hashes():raise RuntimeError('Complete runtime/receipt inventory changed')
 for name,digest in plan['code_sha256s'].items():
  if sha(ROOT/name)!=digest:raise RuntimeError('Source/committee guard changed since reviewed plan')
 before=None;before_hash=None
 if not args.prepare:before,before_hash=capture(BEFORE)
 if args.apply:
  if RECEIPT.exists()or PENDING.exists():raise RuntimeError('Existing/uncertain receipt; require readback, never reapply')
  if (args.expected_plan_sha256,args.expected_review_sha256,args.expected_before_sha256)!=(plan_hash,review_hash,before_hash):raise RuntimeError('Caller must bind exact reviewed plan/review/before bytes')
  if args.expected_script_sha256!=sha(Path(__file__)):raise RuntimeError('Applier lacks independent script review')
 if args.prepare and BEFORE.exists():raise RuntimeError('Before snapshot already exists; never overwrite rollback evidence')
 if before and(before['plan_sha256']!=plan_hash or before['code_sha256s']!=code_hashes()):raise RuntimeError('Before snapshot/code differs')
 # Network verification precedes locking; exact signed terms and only the CAC
 # registry section must be unchanged. No human date bumps or remote model calls.
 rule=json.loads((ROOT/'apps/pipeline/pipeline/ingestion/policies/langford-voting.json').read_text());checked=datetime.now(timezone.utc).date().isoformat()
 policy=refresh_vote_policy(rule,Path('/private/tmp/committee-apply-policy/langford.json'),checked)
 policy={**policy,'municipality_slug':'langford'}
 if policy.get('policy_status')!='verified_unchanged':raise RuntimeError('Current official voting policy held')
 db=psycopg2.connect(config.DATABASE_URL,connect_timeout=15);db.set_session(isolation_level='SERIALIZABLE',readonly=not args.apply)
 commit_attempted=False;committed=False
 try:
  with db.cursor(cursor_factory=RealDictCursor)as cur:
   live_motions,live_votes,live_meetings=rows(cur,ids,args.apply)
   if len(live_motions)!=22:raise RuntimeError('Motion inventory changed')
   if before and(live_motions!=before['motions']or live_votes!=before['votes']or live_meetings!=before['meetings']):raise RuntimeError('Full before motion/vote/catalog CAS failed')
   old={m['id']:m for m in live_motions};meetings={m['id']:{**m,'municipality_slug':'langford'}for m in live_meetings};existing=defaultdict(list)
   for v in live_votes:existing[v['motion_id']].append(v)
   cur.execute('SELECT id,name FROM people ORDER BY id'+(' FOR SHARE'if args.apply else''));people=[dict(r)for r in cur.fetchall()]
   cur.execute('SELECT m.person_id,m.organization_id,p.name,m.role,m.start_date,m.end_date,o.name organization_name,o.classification FROM memberships m JOIN people p ON p.id=m.person_id JOIN organizations o ON o.id=m.organization_id WHERE o.municipality_id=1'+(' FOR SHARE OF m,o'if args.apply else''));memberships=canon(cur.fetchall())
   sources={};changes=[]
   for r in selected:
    mid=r['motion_id'];meeting=meetings[r['meeting_id']]
    expected_motion={k:v for k,v in old[mid].items()if k!='meta_is_sql_null'}
    if expected_motion!=r['before_motion']:raise RuntimeError('Full reviewed motion row changed')
    if meeting['id']not in sources:sources[meeting['id']]=load_official_minutes(meeting,root=ROOT,people=people,cache_dir='/private/tmp/roster-apply-native')
    source=sources[meeting['id']]
    if source.get('source_sha256')!=r['source_sha256']:raise RuntimeError('Official original source changed')
    if any(source.get(key)!=r[expected] for key,expected in [('local_date','source_date'),('source_url','source_url'),('source_format','source_format')]):raise RuntimeError('Official source date/URL/format changed')
    candidate=evaluate_ballot(old[mid],{'status':'available','source':source,'meeting':meeting,'people':people,'memberships':memberships,'policy':policy},existing[mid])
    if candidate['status']!='reconstructable_candidate'or{(v['person_id'],v['vote'])for v in candidate['votes']}!={(v['person_id'],v['vote'])for v in r['votes']}:raise RuntimeError(f'Fresh full source/roster gate held motion{mid}: {candidate["status"]}')
    for key in ('source_motion_text','source_block','roster_quote','presence_events','voting_body','source_result','inference_basis','operative_motion_body','roster_source_validation','source_date_evidence','membership_evidence','initial_arrival_adjustments'):
     if candidate.get(key)!=r.get(key):raise RuntimeError(f'Fresh documentary proof changed motion{mid}: {key}')
    if {(v['person_id'],v['vote'],v['evidence'],v['source_quote'])for v in candidate['votes']}!={(v['person_id'],v['vote'],v['evidence'],v['source_quote'])for v in r['votes']}:raise RuntimeError('Fresh per-choice provenance changed')
    expected_plan={(v['id'],v['person_id'],v['vote'],v['updated_at'])for v in r['current_choices']};actual_old={(v['id'],v['person_id'],v['vote'],v['updated_at'])for v in existing[mid]}
    if expected_plan!=actual_old:raise RuntimeError('Existing choice changed since independent review')
    new=[(mid,v['person_id'],v['vote'])for v in candidate['votes']if v['person_id']not in{x['person_id']for x in existing[mid]}]
    if {(p,v)for _,p,v in new}!={(v['person_id'],v['vote'])for v in r['new_choices']}:raise RuntimeError('Current missing choice set differs')
    if candidate['proof'].get('roster_source_validation')!=r['proof'].get('roster_source_validation'):raise RuntimeError('Fresh bound OCR proof changed')
    proof={**candidate['proof'],'independent_review':{'sha256':review_hash,'plan_sha256':plan_hash}}
    metadata={**(old[mid]['meta']or{}),'individual_vote_coverage':'reconstructed_complete','ballot_reconstruction':proof,'vote_record':{**((old[mid]['meta']or{}).get('vote_record')or{}),'coverage':'reconstructed_complete'}}
    changes.append({'motion_id':mid,'before_motion':old[mid],'before_votes':existing[mid],'after_meta':metadata,'new_choices':new,'inserted_votes':[]})
   if sum(len(c['new_choices'])for c in changes)!=147:raise RuntimeError('Exact missing147 changed')
   if len(live_votes)!=7:raise RuntimeError('Exact7 preserved choices changed')
   if args.prepare:
    save(BEFORE,{'mode':'read_only_captured_before','at':datetime.now(timezone.utc).isoformat(),'plan_sha256':plan_hash,'code_sha256s':code_hashes(),'motions':live_motions,'votes':live_votes,'meetings':live_meetings});db.rollback();print(json.dumps({'mode':'prepared_read_only','motions':22,'existing_votes':len(live_votes),'missing_choices':147,'database_writes':0,'before_sha256':sha(BEFORE)}));return
   if args.apply:
    inserted=execute_values(cur,f'INSERT INTO votes(motion_id,person_id,vote) VALUES %s RETURNING {VC}',[x for c in changes for x in c['new_choices']],page_size=500,fetch=True)
    byid={c['motion_id']:c for c in changes}
    for v in inserted:byid[v['motion_id']]['inserted_votes'].append(canon(v))
    for c in changes:
     cur.execute(f'UPDATE motions SET meta=%s WHERE id=%s RETURNING {MC}',(Json(c['after_meta']),c['motion_id']));c['after_motion']=canon(cur.fetchone())
    after_motions,after_votes,after_meetings=rows(cur,ids,True)
    verify_after_rows(changes,after_motions,after_votes)
    if after_meetings!=live_meetings:raise RuntimeError('Catalog rows changed during writes')
   if plan['code_sha256s']!=code_hashes():raise RuntimeError('Runtime/store changed during replay')
   receipt={'mode':'pending_commit'if args.apply else'dry_run','at':datetime.now(timezone.utc).isoformat(),'plan_sha256':plan_hash,'independent_review_sha256':review_hash,'before_sha256':before_hash,'apply_script_sha256':sha(Path(__file__)),'summary':{'ballots':22,'new_choices':147,'existing_choices_preserved':len(live_votes),'vote_overwrites':0,'motion_text_writes':0},'policy':policy,'changes':changes}
   if Path(args.preflight_name).name!=args.preflight_name:raise RuntimeError('Preflight name must be a filename')
   save(PENDING if args.apply else OUT/args.preflight_name,receipt)
  if args.apply:
   commit_attempted=True
   db.commit();committed=True
   receipt['mode']='applied';receipt['committed_at']=datetime.now(timezone.utc).isoformat();save(RECEIPT,receipt)
  else:db.rollback()
  print(json.dumps(receipt['summary']))
 except BaseException as error:
  if commit_attempted:
   state='Database commit completed, but final receipt could not be confirmed'if committed else'Database commit outcome is uncertain'
   raise RuntimeError(state+'; retain durable pending receipt and run independent full-row readback. Never blindly retry apply.')from error
  db.rollback();raise
 finally:db.close()
if __name__=='__main__':main()
