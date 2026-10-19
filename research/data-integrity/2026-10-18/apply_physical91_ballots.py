"""Prepare/dry-run/apply exactly the independently reviewed 91 ballots.

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
from pipeline.ingestion.committee_ballots import refresh_committee_policy
from pipeline.ingestion.vote_policy import refresh_vote_policy
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
PLAN=OUT/'physical91-ballot-plan.json';REVIEW=OUT/'physical91-independent-review.json';BEFORE=OUT/'physical91-current-before.json';RECEIPT=OUT/'physical91-applied-receipt.json';PENDING=OUT/'physical91-pending-receipt.json'
MC='id,meeting_id,agenda_item_id,text_content,result,meta,updated_at,meta IS NULL AS meta_is_sql_null';VC='id,motion_id,person_id,vote,recusal_reason,created_at,updated_at'
DEPS=['committee_ballots.py','official_ballots.py','ballot_reconstruction.py','vote_evidence.py','meeting_ballots.py','canonical_motions.py','native_header_ocr.py','native_header_vision.swift','vote_policy.py']
canon=lambda value:json.loads(json.dumps(value,default=str))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def capture(path):
 raw=path.read_bytes();return json.loads(raw),hashlib.sha256(raw).hexdigest()
def save(path,data):
 temp=path.with_suffix('.json.tmp');temp.write_text(json.dumps(canon(data),indent=2)+'\n');temp.replace(path)
def code_hashes():return {str(Path('apps/pipeline/pipeline/ingestion')/n):sha(ROOT/'apps/pipeline/pipeline/ingestion'/n)for n in DEPS}
def rows(cur,ids,lock):
 cur.execute(f'SELECT {MC} FROM motions WHERE id=ANY(%s) ORDER BY id'+(' FOR UPDATE'if lock else''),(ids,));motions=[canon(r)for r in cur.fetchall()]
 cur.execute(f'SELECT {VC} FROM votes WHERE motion_id=ANY(%s) ORDER BY id'+(' FOR UPDATE'if lock else''),(ids,));votes=[canon(r)for r in cur.fetchall()]
 mids=sorted({m['meeting_id']for m in motions})
 cur.execute('SELECT m.id,m.meeting_date,m.title,m.type,m.archive_path,m.organization_id,m.updated_at,o.classification FROM meetings m JOIN organizations o ON o.id=m.organization_id WHERE m.id=ANY(%s) ORDER BY m.id'+(' FOR SHARE OF m,o'if lock else''),(mids,));meetings=[canon(r)for r in cur.fetchall()]
 return motions,votes,meetings

def main():
 cli=argparse.ArgumentParser(description=__doc__);modes=cli.add_mutually_exclusive_group();modes.add_argument('--prepare',action='store_true');modes.add_argument('--apply',action='store_true');modes.add_argument('--rollback',action='store_true')
 for name in ['plan','review','before','receipt']:cli.add_argument('--expected-'+name+'-sha256')
 args=cli.parse_args()
 if args.rollback:
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
   save(OUT/'physical91-rollback-pending-receipt.json',{'receipt_sha256':receipt_hash,'restored_motion_ids':ids,'deleted_inserted_vote_ids':inserted})
   db.commit()
  save(OUT/'physical91-rollback-receipt.json',{'mode':'rolled_back','receipt_sha256':receipt_hash,'at':datetime.now(timezone.utc).isoformat(),'restored_motion_ids':ids,'deleted_inserted_vote_ids':inserted});print('Guarded rollback complete');return
 plan,plan_hash=capture(PLAN);review,review_hash=capture(REVIEW)
 selected=[r for r in plan['records']if r['status']=='reconstructable_candidate'];ids=sorted(r['motion_id']for r in selected)
 if len(selected)!=91 or sum(len(r['new_choices'])for r in selected)!=607 or len(set(ids))!=91:raise RuntimeError('Exact reviewed91/607 scope changed')
 if ids!=[1647, 1648, 1649, 1650, 1653, 1654, 1685, 1686, 1687, 1688, 1689, 1690, 1693, 1697, 1698, 1699, 1741, 1742, 1743, 1744, 1745, 1746, 1747, 1749, 1750, 1751, 2006, 2007, 2079, 2080, 2081, 2082, 2083, 2084, 2085, 2210, 2211, 2212, 2213, 2316, 2317, 2456, 2457, 2460, 2914, 2918, 2919, 2920, 2921, 2922, 2923, 3004, 3005, 3006, 3007, 3010, 3011, 3044, 3045, 3047, 3048, 3049, 3063, 3169, 3170, 3171, 3172, 3173, 3175, 3176, 3178, 3222, 3231, 3232, 3233, 3234, 3235, 3236, 3237, 3239, 3240, 3794, 3795, 3796, 3797, 3798, 3801, 3802, 3803, 3886, 3887]:raise RuntimeError('Exact reviewed91 motion IDs required')
 if review['candidate_plan_sha256']!=plan_hash or set(review['reviewed_candidate_ids'])!=set(ids)or review['summary'].get('proof_issues')!=0:raise RuntimeError('Independent review is not apply-eligible for exact91')
 reviewed={r['motion_id']:r for r in review['records']if r['status']=='reviewed'}
 for r in selected:
  approved=reviewed[r['motion_id']]
  if approved['source_sha256']!=r['source_sha256']or{(v['person_id'],v['vote'])for v in approved['choices']}!={(v['person_id'],v['vote'])for v in r['votes']}:raise RuntimeError('Independent per-choice review differs')
 for name,digest in plan['code_sha256s'].items():
  if sha(ROOT/name)!=digest:raise RuntimeError('Source/committee guard changed since reviewed plan')
 if sha(ROOT/'apps/pipeline/pipeline/ingestion/meeting_ballots.py')!=review['integration_sha256']:raise RuntimeError('Ordinary dispatcher changed since independent proof')
 before=None;before_hash=None
 if not args.prepare:before,before_hash=capture(BEFORE)
 if args.apply:
  if RECEIPT.exists()or PENDING.exists():raise RuntimeError('Existing/uncertain receipt; require readback, never reapply')
  if (args.expected_plan_sha256,args.expected_review_sha256,args.expected_before_sha256)!=(plan_hash,review_hash,before_hash):raise RuntimeError('Caller must bind exact reviewed plan/review/before bytes')
  if review.get('apply_script_sha256')!=sha(Path(__file__)):raise RuntimeError('Applier lacks independent script review')
 if args.prepare and BEFORE.exists():raise RuntimeError('Before snapshot already exists; never overwrite rollback evidence')
 if before and(before['plan_sha256']!=plan_hash or before['code_sha256s']!=code_hashes()):raise RuntimeError('Before snapshot/code differs')
 # Network verification precedes locking; exact signed terms and only the CAC
 # registry section must be unchanged. No human date bumps or remote model calls.
 rule=json.loads((ROOT/'apps/pipeline/pipeline/ingestion/policies/langford-voting.json').read_text());checked=datetime.now(timezone.utc).date().isoformat()
 policy=refresh_vote_policy(rule,Path('/private/tmp/committee-apply-policy/langford.json'),checked)
 policy=refresh_committee_policy({**policy,'municipality_slug':'langford'},checked)
 if policy.get('policy_status')!='verified_unchanged'or policy.get('committee_policy',{}).get('status')!='verified_unchanged':raise RuntimeError('Current official voting/committee policy held')
 db=psycopg2.connect(config.DATABASE_URL,connect_timeout=15);db.set_session(isolation_level='SERIALIZABLE',readonly=not args.apply)
 try:
  with db.cursor(cursor_factory=RealDictCursor)as cur:
   live_motions,live_votes,live_meetings=rows(cur,ids,args.apply)
   if len(live_motions)!=91:raise RuntimeError('Motion inventory changed')
   if before and(live_motions!=before['motions']or live_votes!=before['votes']or live_meetings!=before['meetings']):raise RuntimeError('Full before motion/vote/catalog CAS failed')
   old={m['id']:m for m in live_motions};meetings={m['id']:{**m,'municipality_slug':'langford'}for m in live_meetings};existing=defaultdict(list)
   for v in live_votes:existing[v['motion_id']].append(v)
   cur.execute('SELECT id,name FROM people ORDER BY id'+(' FOR SHARE'if args.apply else''));people=[dict(r)for r in cur.fetchall()]
   cur.execute('SELECT m.person_id,p.name,m.role,m.start_date,m.end_date,o.classification FROM memberships m JOIN people p ON p.id=m.person_id JOIN organizations o ON o.id=m.organization_id WHERE o.municipality_id=1'+(' FOR SHARE OF m,o'if args.apply else''));memberships=canon(cur.fetchall())
   sources={};changes=[]
   for r in selected:
    mid=r['motion_id'];meeting=meetings[r['meeting_id']]
    if meeting['id']not in sources:sources[meeting['id']]=load_official_minutes(meeting,root=ROOT,people=people,cache_dir='/private/tmp/committee-apply-native')
    source=sources[meeting['id']]
    if source.get('source_sha256')!=r['source_sha256']:raise RuntimeError('Official original source changed')
    if any(source.get(key)!=r[expected] for key,expected in [('local_date','source_date'),('source_url','source_url'),('source_format','source_format')]):raise RuntimeError('Official source date/URL/format changed')
    candidate=evaluate_ballot(old[mid],{'status':'available','source':source,'meeting':meeting,'people':people,'memberships':memberships,'policy':policy},existing[mid])
    if candidate['status']!='reconstructable_candidate'or{(v['person_id'],v['vote'])for v in candidate['votes']}!={(v['person_id'],v['vote'])for v in r['votes']}:raise RuntimeError(f'Fresh full source/roster gate held motion{mid}: {candidate["status"]}')
    for key in ('source_motion_text','source_block','roster_quote','presence_events','voting_body','source_result','inference_basis'):
     if candidate.get(key)!=r.get(key):raise RuntimeError(f'Fresh documentary proof changed motion{mid}: {key}')
    if {(v['person_id'],v['vote'],v['evidence'],v['source_quote'])for v in candidate['votes']}!={(v['person_id'],v['vote'],v['evidence'],v['source_quote'])for v in r['votes']}:raise RuntimeError('Fresh per-choice provenance changed')
    expected_plan={(v['id'],v['person_id'],v['vote'],v['updated_at'])for v in r['current_choices']};actual_old={(v['id'],v['person_id'],v['vote'],v['updated_at'])for v in existing[mid]}
    if expected_plan!=actual_old:raise RuntimeError('Existing choice changed since independent review')
    new=[(mid,v['person_id'],v['vote'])for v in candidate['votes']if v['person_id']not in{x['person_id']for x in existing[mid]}]
    if {(p,v)for _,p,v in new}!={(v['person_id'],v['vote'])for v in r['new_choices']}:raise RuntimeError('Current missing choice set differs')
    proof={**candidate['proof'],'independent_review':{'sha256':review_hash,'plan_sha256':plan_hash}}
    metadata={**(old[mid]['meta']or{}),'individual_vote_coverage':'reconstructed_complete','ballot_reconstruction':proof,'vote_record':{**((old[mid]['meta']or{}).get('vote_record')or{}),'coverage':'reconstructed_complete'}}
    changes.append({'motion_id':mid,'before_motion':old[mid],'before_votes':existing[mid],'after_meta':metadata,'new_choices':new,'inserted_votes':[]})
   if sum(len(c['new_choices'])for c in changes)!=607:raise RuntimeError('Exact missing607 changed')
   if len(live_votes)!=20:raise RuntimeError('Exact20 preserved choices changed')
   if args.prepare:
    save(BEFORE,{'mode':'read_only_captured_before','at':datetime.now(timezone.utc).isoformat(),'plan_sha256':plan_hash,'code_sha256s':code_hashes(),'motions':live_motions,'votes':live_votes,'meetings':live_meetings});db.rollback();print(json.dumps({'mode':'prepared_read_only','motions':91,'existing_votes':len(live_votes),'missing_choices':607,'database_writes':0,'before_sha256':sha(BEFORE)}));return
   if args.apply:
    inserted=execute_values(cur,f'INSERT INTO votes(motion_id,person_id,vote) VALUES %s RETURNING {VC}',[x for c in changes for x in c['new_choices']],page_size=500,fetch=True)
    byid={c['motion_id']:c for c in changes}
    for v in inserted:byid[v['motion_id']]['inserted_votes'].append(canon(v))
    for c in changes:
     cur.execute(f'UPDATE motions SET meta=%s WHERE id=%s RETURNING {MC}',(Json(c['after_meta']),c['motion_id']));c['after_motion']=canon(cur.fetchone())
   receipt={'mode':'pending_commit'if args.apply else'dry_run','at':datetime.now(timezone.utc).isoformat(),'plan_sha256':plan_hash,'independent_review_sha256':review_hash,'before_sha256':before_hash,'apply_script_sha256':sha(Path(__file__)),'summary':{'ballots':91,'new_choices':607,'existing_choices_preserved':len(live_votes),'vote_overwrites':0,'motion_text_writes':0},'policy':policy,'changes':changes}
   save(PENDING if args.apply else OUT/'physical91-preflight.json',receipt)
  if args.apply:
   db.commit();receipt['mode']='applied';receipt['committed_at']=datetime.now(timezone.utc).isoformat();save(RECEIPT,receipt)
  else:db.rollback()
  print(json.dumps(receipt['summary']))
 except BaseException:
  db.rollback();raise
 finally:db.close()
if __name__=='__main__':main()
