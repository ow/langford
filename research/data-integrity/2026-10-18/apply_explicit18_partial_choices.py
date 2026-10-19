"""Read-only preflight / guarded append of 18 explicit named choices, never full ballots."""
import argparse,json,hashlib
from pathlib import Path
from datetime import datetime,timezone
from collections import defaultdict
import psycopg2
from psycopg2.extras import RealDictCursor,Json,execute_values
from pipeline import config
from pipeline.ingestion.official_ballots import load_official_minutes
from pipeline.ingestion.vote_evidence import normalize_text,outcome_family,named_votes,named_vote_declarations
from pipeline.ingestion.ballot_reconstruction import validate_roster_entries
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
PLAN=OUT/'explicit18-partial-choice-plan.json';REVIEW=OUT/'explicit18-partial-choice-independent-review.json';RECEIPT=OUT/'explicit18-partial-choice-applied-receipt.json';PENDING=OUT/'explicit18-partial-choice-pending-receipt.json'
MC='id,meeting_id,agenda_item_id,text_content,result,meta,updated_at';VC='id,motion_id,person_id,vote,recusal_reason,created_at,updated_at'
canon=lambda x:json.loads(json.dumps(x,default=str))
def capture(path):
 raw=path.read_bytes();return json.loads(raw),hashlib.sha256(raw).hexdigest()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,data):
 temp=path.with_suffix('.json.tmp');temp.write_text(json.dumps(canon(data),indent=2)+'\n');temp.replace(path)
def current(cur,ids,lock):
 cur.execute(f'SELECT {MC} FROM motions WHERE id=ANY(%s) ORDER BY id'+(' FOR UPDATE'if lock else''),(ids,));motions=canon(cur.fetchall())
 cur.execute(f'SELECT {VC} FROM votes WHERE motion_id=ANY(%s) ORDER BY id'+(' FOR UPDATE'if lock else''),(ids,));votes=canon(cur.fetchall());return motions,votes

def main():
 cli=argparse.ArgumentParser(description=__doc__);mode=cli.add_mutually_exclusive_group();mode.add_argument('--apply',action='store_true');mode.add_argument('--rollback',action='store_true')
 for key in ('plan','review','receipt'):cli.add_argument('--expected-'+key+'-sha256')
 args=cli.parse_args()
 if args.rollback:
  receipt,rhash=capture(RECEIPT)
  if args.expected_receipt_sha256!=rhash or receipt['mode']!='applied':raise RuntimeError('Exact applied receipt required')
  ids=sorted(c['motion_id']for c in receipt['changes'])
  with psycopg2.connect(config.DATABASE_URL,connect_timeout=15)as db:
   db.set_session(isolation_level='SERIALIZABLE')
   with db.cursor(cursor_factory=RealDictCursor)as cur:
    motions,votes=current(cur,ids,True)
    if motions!=sorted([c['after_motion']for c in receipt['changes']],key=lambda r:r['id'])or votes!=sorted([v for c in receipt['changes']for v in c['before_votes']+c['inserted_votes']],key=lambda r:r['id']):raise RuntimeError('Rollback held: full rows changed')
    inserted=[v['id']for c in receipt['changes']for v in c['inserted_votes']];cur.execute('DELETE FROM votes WHERE id=ANY(%s)',(inserted,))
    for c in receipt['changes']:cur.execute('UPDATE motions SET meta=%s WHERE id=%s',(None if c['before_meta_is_sql_null'] else Json(c['before_motion']['meta']),c['motion_id']))
   save(OUT/'explicit18-partial-choice-rollback-pending.json',{'receipt_sha256':rhash,'deleted_vote_ids':inserted,'restored_motion_ids':ids});db.commit()
  save(OUT/'explicit18-partial-choice-rollback-receipt.json',{'mode':'rolled_back','receipt_sha256':rhash,'deleted_vote_ids':inserted,'restored_motion_ids':ids});return
 plan,phash=capture(PLAN);review,rhash=capture(REVIEW);records=plan['records'];ids=sorted(r['motion_id']for r in records)
 if len(ids)!=9 or len(set(ids))!=9 or 2473 in ids or sum(len(r['named_choices'])for r in records)!=18:raise RuntimeError('Exact9/18 nonoverlapping scope required')
 if plan.get('code_sha256s_pending_source_key_checkpoint')or not plan.get('code_sha256s'):raise RuntimeError('Final source-key guard rebind required')
 for name,digest in plan['code_sha256s'].items():
  if sha(ROOT/name)!=digest:raise RuntimeError('Reviewed guard changed')
 if review['candidate_plan_sha256']!=phash or set(review['reviewed_candidate_ids'])!=set(ids)or review.get('apply_script_sha256')!=sha(Path(__file__)):raise RuntimeError('Exact independent source and applier review required')
 approved={r['motion_id']:r for r in review['records']if r['status']=='reviewed'}
 for r in records:
  proof=approved[r['motion_id']]
  if proof['source_sha256']!=r['source_sha256']or{(v['person_id'],v['vote'])for v in proof['choices']}!={(v['person_id'],v['vote'])for v in r['named_choices']}:raise RuntimeError('Per-person independent source proof differs')
 if args.apply and((args.expected_plan_sha256,args.expected_review_sha256)!=(phash,rhash)or RECEIPT.exists()or PENDING.exists()):raise RuntimeError('Bind exact reviewed scope; never retry uncertain receipt')
 db=psycopg2.connect(config.DATABASE_URL,connect_timeout=15);db.set_session(readonly=not args.apply,isolation_level='SERIALIZABLE')
 try:
  with db.cursor(cursor_factory=RealDictCursor)as cur:
   motions,votes=current(cur,ids,args.apply)
   expected_motions=sorted([r['current_motion']for r in records],key=lambda r:r['id']);expected_votes=sorted([v for r in records for v in r['current_votes']],key=lambda r:r['id'])
   semantic=lambda rows:[{k:v for k,v in row.items()if k!='updated_at'}for row in rows]
   if semantic(motions)!=semantic(expected_motions)or votes!=expected_votes:raise RuntimeError('Exact original semantic motion/full-vote CAS failed')
   timestamp_only_differences=[{'motion_id':fresh['id'],'reviewed_updated_at':expected['updated_at'],'locked_current_updated_at':fresh['updated_at']}for expected,fresh in zip(expected_motions,motions)if expected['updated_at']!=fresh['updated_at']]
   if timestamp_only_differences and not plan.get('allow_updated_at_only_drift'):raise RuntimeError('Timestamp-only drift was not explicitly reviewed')
   cur.execute('SELECT id,meta IS NULL AS meta_is_sql_null FROM motions WHERE id=ANY(%s)',(ids,));meta_null_flags={r['id']:r['meta_is_sql_null']for r in cur.fetchall()}
   if any(meta_null_flags[r['motion_id']]!=r['before_meta_is_sql_null']for r in records):raise RuntimeError('SQL NULL/JSON null before-state changed')
   byid={m['id']:m for m in motions};existing=defaultdict(list)
   for v in votes:existing[v['motion_id']].append(v)
   cur.execute('SELECT id,name FROM people ORDER BY id'+(' FOR SHARE'if args.apply else''));people=[dict(r)for r in cur.fetchall()];names={p['id']:p['name']for p in people}
   mids=sorted({r['meeting_id']for r in records});cur.execute('SELECT m.id,m.meeting_date,m.title,m.type,m.archive_path,m.organization_id,o.classification FROM meetings m JOIN organizations o ON o.id=m.organization_id WHERE m.id=ANY(%s)'+(' FOR SHARE OF m,o'if args.apply else''),(mids,));meetings={r['id']:canon(r)for r in cur.fetchall()}
   sources={};changes=[]
   for r in records:
    mid=r['motion_id'];row=byid[mid];meeting=meetings[r['meeting_id']];prior_meta=row.get('meta')or{};prior_record=prior_meta.get('vote_record')or{}
    if prior_meta.get('individual_vote_coverage')=='reconstructed_complete':raise RuntimeError('Never downgrade complete ballots')
    if meeting['id']not in sources:sources[meeting['id']]=load_official_minutes(meeting,root=ROOT,people=people,cache_dir='/private/tmp/explicit18-native')
    source=sources[meeting['id']]
    if source.get('source_sha256')!=r['source_sha256']:raise RuntimeError('Official source binary changed')
    if source.get('local_date')!=r['source_date']or source.get('source_url')!=r['source_url']:raise RuntimeError('Fresh source date/URL differs from reviewed provenance')
    if not source.get('local_date')or abs((datetime.fromisoformat(source['local_date'])-datetime.fromisoformat(meeting['meeting_date'])).days)>1:raise RuntimeError('Native meeting date not bound')
    blocks=source['index'].get(normalize_text(row['text_content']),[])
    if len(blocks)!=1:raise RuntimeError('Unique exact source body required')
    block=blocks[0]
    if normalize_text(block['source_block'])!=normalize_text(r['source_block'])or outcome_family(block['result'])!=outcome_family(row['result']):raise RuntimeError('Full bounded source/outcome changed')
    for d in named_vote_declarations(block):
     resolved,unknown=validate_roster_entries(d['names'],people)
     if d.get('unparsed')or unknown or not resolved or(d.get('declared_count')is not None and d['declared_count']!=len(resolved)):raise RuntimeError('Unknown or ambiguous named source declaration')
    actual=named_votes(block,[p['name']for p in people]);found=defaultdict(set)
    for v in actual:found[v['person_name']].add(v['vote'])
    if any(len(v)!=1 for v in found.values()):raise RuntimeError('Conflicting source choices')
    additions=[];proofs=[]
    for v in r['named_choices']:
     if names.get(v['person_id'])!=v['person_name']or any(old['person_id']==v['person_id']for old in existing[mid]):raise RuntimeError('Identity changed or choice already exists')
     if not any(a['person_name']==v['person_name']and a['vote']==v['vote']and normalize_text(a['source_quote'])==normalize_text(v['source_quote'])for a in actual):raise RuntimeError('Named choice not exact source verified')
     additions.append((mid,v['person_id'],v['vote']));proofs.append({**v,'source_url':r['source_url'],'source_sha256':r['source_sha256'],'source_date':r['source_date'],'source_motion_text':r['source_motion_text'],'source_block':r['source_block'],'independent_review_sha256':rhash})
    meta={**prior_meta,'individual_vote_coverage':'named_only','vote_record':{**prior_record,'coverage':'partial','source_verified_named_choices':(prior_record.get('source_verified_named_choices')or[])+proofs}}
    changes.append({'motion_id':mid,'before_meta_is_sql_null':r['before_meta_is_sql_null'],'before_motion':row,'before_votes':existing[mid],'after_meta':meta,'new_choices':additions,'inserted_votes':[]})
   if args.apply:
    inserted=execute_values(cur,f'INSERT INTO votes(motion_id,person_id,vote) VALUES %s RETURNING {VC}',[v for c in changes for v in c['new_choices']],fetch=True);lookup={c['motion_id']:c for c in changes}
    if len(inserted)!=18 or {(v['motion_id'],v['person_id'],v['vote'])for v in inserted}!={v for c in changes for v in c['new_choices']}:raise RuntimeError('Inserted explicit choice set differs')
    for v in inserted:lookup[v['motion_id']]['inserted_votes'].append(canon(v))
    for c in changes:
     cur.execute(f'UPDATE motions SET meta=%s WHERE id=%s RETURNING {MC}',(Json(c['after_meta']),c['motion_id']));c['after_motion']=canon(cur.fetchone())
   receipt={'mode':'pending_commit'if args.apply else'dry_run','at':datetime.now(timezone.utc).isoformat(),'plan_sha256':phash,'independent_review_sha256':rhash,'apply_script_sha256':sha(Path(__file__)),'timestamp_only_differences':timestamp_only_differences,'rollback_baseline':'fresh_locked_current_full_rows','summary':{'motions':9,'new_explicit_choices':18,'existing_choices_preserved':len(votes),'full_ballot_claims':0,'text_or_result_writes':0},'changes':changes}
   save(PENDING if args.apply else OUT/'explicit18-partial-choice-preflight.json',receipt)
  if args.apply:
   db.commit();receipt['mode']='applied';save(RECEIPT,receipt)
  else:db.rollback()
  print(json.dumps(receipt['summary']))
 except BaseException:db.rollback();raise
 finally:db.close()
if __name__=='__main__':main()
