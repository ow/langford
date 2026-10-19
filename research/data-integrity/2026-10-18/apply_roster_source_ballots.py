"""CAS apply source-reviewed historical ballots and exact canonical text repairs.

Default is a read-only transaction. --apply requires an independent source review
bound to the immutable plan. Existing choices/IDs are never overwritten. Every
source and shared production guard is rechecked; failures hold the whole batch.
"""
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from collections import defaultdict
import psycopg2
from psycopg2.extras import RealDictCursor,Json,execute_values
from pipeline import config
from pipeline.ingestion import official_ballots as engine
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
cli=argparse.ArgumentParser(description=__doc__);cli.add_argument('--apply',action='store_true');cli.add_argument('--rollback',action='store_true');args=cli.parse_args()
if args.apply and args.rollback:cli.error('Choose apply or rollback')
receipt_path=OUT/'roster-source-applied-receipt.json'
canonical=lambda value:json.loads(json.dumps(value,default=str))
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
if args.rollback:
 receipt=json.loads(receipt_path.read_text())
 if receipt['mode']!='applied':raise RuntimeError('Only an applied receipt can roll back')
 with psycopg2.connect(config.DATABASE_URL,connect_timeout=15) as db:
  with db.cursor(cursor_factory=RealDictCursor) as cur:
   ids=[c['motion_id'] for c in receipt['changes']]
   cur.execute('SELECT id,text_content,meta,updated_at FROM motions WHERE id=ANY(%s) FOR UPDATE',(ids,));live={r['id']:canonical(r) for r in cur.fetchall()}
   inserted=[v for c in receipt['changes'] for v in c['inserted_votes']]
   cur.execute('SELECT id,motion_id,person_id,vote,updated_at FROM votes WHERE id=ANY(%s) FOR UPDATE',([v['id'] for v in inserted],));live_votes={v['id']:canonical(v) for v in cur.fetchall()}
   for c in receipt['changes']:
    row=live[c['motion_id']]
    if row['text_content']!=c['after_text_content'] or row['meta']!=c['after_meta'] or row['updated_at']!=c['after_updated_at']:raise RuntimeError('Rollback held: motion changed')
   if any(live_votes.get(v['id'])!=v for v in inserted):raise RuntimeError('Rollback held: inserted choices changed')
   cur.execute('SELECT id,motion_id,person_id,vote,updated_at FROM votes WHERE motion_id=ANY(%s) ORDER BY id FOR UPDATE',(ids,))
   all_live=[canonical(v) for v in cur.fetchall()]
   all_expected=sorted([v for c in receipt['changes'] for v in c['before_votes']+c['inserted_votes']],key=lambda v:v['id'])
   if all_live!=all_expected:raise RuntimeError('Rollback held: ballot choices changed independently')
   cur.execute('DELETE FROM votes WHERE id=ANY(%s)',([v['id'] for v in inserted],))
   for c in receipt['changes']:cur.execute('UPDATE motions SET text_content=%s,meta=%s WHERE id=%s',(c['before']['text_content'],Json(c['before']['meta']),c['motion_id']))
  receipt['rollback_committed_at']=datetime.now(timezone.utc).isoformat()
 (OUT/'roster-source-rollback-receipt.json').write_text(json.dumps(receipt,indent=2));print('Rolled back',len(inserted),'new choices; prior choices preserved');raise SystemExit
if receipt_path.exists():raise RuntimeError('Applied receipt already exists; never overwrite rollback evidence')
plan_bytes=(OUT/'roster-source-recovery-plan.json').read_bytes();plan=json.loads(plan_bytes);plan_hash=hashlib.sha256(plan_bytes).hexdigest()
before=json.loads((OUT/'roster-source-recovery-before.json').read_text());prior={m['id']:m for m in before['motions']}
if before['plan_sha256']!=plan_hash:raise RuntimeError('Before snapshot is bound to another plan')
review_path=OUT/'roster-source-independent-review.json';review_bytes=review_path.read_bytes();review=json.loads(review_bytes);review_hash=hashlib.sha256(review_bytes).hexdigest()
if review['candidate_plan_sha256']!=plan_hash:raise RuntimeError('Independent review is bound to another plan')
if review.get('apply_script_sha256')!=sha(Path(__file__)):raise RuntimeError('Apply script changed since independent review')
reviewed={r['motion_id']:r for r in review['records'] if r['status']=='reviewed'}
correction_reviewed=set(review.get('reviewed_body_correction_ids',[]))
new=plan['motions'];corrections=plan['canonical_body_corrections'];selected=new+corrections
if len({r['motion_id'] for r in selected})!=len(selected):raise RuntimeError('Duplicate plan motion')
for candidate in new:
 record=reviewed.get(candidate['motion_id'])
 if not record or record['source_sha256']!=candidate['source_sha256'] or {(v['person_id'],v['vote']) for v in record['choices']}!={(v['person_id'],v['vote']) for v in candidate['votes']}:raise RuntimeError('Candidate lacks exact independent source/choice review')
if not {r['motion_id'] for r in corrections}<=correction_reviewed:raise RuntimeError('Canonical body correction lacks independent source review')
for path,digest in plan['summary']['code_sha256s'].items():
 if sha(ROOT/path)!=digest:raise RuntimeError('Shared production validator changed during independent review')
snapshot=json.loads((OUT/'ballot-source-current-snapshot.json').read_text());meetings={m['id']:m for m in snapshot['meetings']}
if sha(OUT/'ballot-source-current-snapshot.json')!=plan['summary']['current_motion_snapshot_sha256']:raise RuntimeError('Meeting/source snapshot changed')
policy={**json.loads((ROOT/'apps/pipeline/pipeline/ingestion/policies/langford-voting.json').read_text()),**json.loads((OUT/'policy-refresh-verification.json').read_text()),'municipality_slug':'langford'}
prior_votes=defaultdict(list)
for v in before['votes']:prior_votes[v['motion_id']].append(v)
changes=[];db=psycopg2.connect(config.DATABASE_URL,connect_timeout=15);db.set_session(isolation_level='SERIALIZABLE',readonly=not args.apply)
try:
 with db.cursor(cursor_factory=RealDictCursor) as cur:
  suffix=' FOR UPDATE' if args.apply else ''
  ids=sorted(prior)
  cur.execute('SELECT id,meeting_id,agenda_item_id,text_content,result,meta,updated_at FROM motions WHERE id=ANY(%s) ORDER BY id'+suffix,(ids,));current={r['id']:canonical(r) for r in cur.fetchall()}
  cur.execute('SELECT id,motion_id,person_id,vote,updated_at FROM votes WHERE motion_id=ANY(%s) ORDER BY id'+suffix,(ids,));existing=defaultdict(list)
  for v in cur.fetchall():existing[v['motion_id']].append(canonical(v))
  cur.execute('SELECT id,name FROM people'+(' FOR SHARE' if args.apply else ''));people=[dict(r) for r in cur.fetchall()]
  cur.execute("SELECT m.person_id,p.name,m.role,m.start_date,m.end_date,o.classification FROM memberships m JOIN organizations o ON o.id=m.organization_id JOIN people p ON p.id=m.person_id WHERE o.municipality_id=1"+(' FOR SHARE OF m,o' if args.apply else ''));memberships=canonical(cur.fetchall())
  sources={}
  for c in selected:
   mid=c['motion_id'];row=current.get(mid)
   if row!=prior[mid] or existing[mid]!=prior_votes[mid]:raise RuntimeError(f'Concurrent change held motion {mid}')
   meeting=meetings[c['meeting_id']]
   if c['meeting_id'] not in sources:sources[c['meeting_id']]=engine.load_official_minutes(meeting,root=ROOT,people=people,cache_dir='/private/tmp/langford-ballot-source-audit')
   source=sources[c['meeting_id']]
   if source.get('source_sha256')!=c['source_sha256']:raise RuntimeError('Official source binary changed')
   checked=engine.inspect_motion({**row,'text_content':c['source_motion_text']},source,meeting=meeting,people=people,memberships=memberships,policy=policy)
   if checked['status']!='reconstructable_candidate' or {(v['person_id'],v['vote']) for v in checked['votes']}!={(v['person_id'],v['vote']) for v in c['votes']}:raise RuntimeError(f'Fresh production gate held motion {mid}: {checked["status"]}')
   expected={v['person_id']:v['vote'] for v in checked['votes']}
   if any(v['person_id'] not in expected or expected[v['person_id']]!=v['vote'] for v in existing[mid]):raise RuntimeError('Existing choices conflict; never overwrite')
   if mid in correction_reviewed and {v['person_id'] for v in existing[mid]}!=set(expected):raise RuntimeError('Canonical correction must preserve the entire existing ballot')
   checked['independent_review']={'file':str(review_path.relative_to(ROOT)),'sha256':review_hash}
   proof=engine.complete_ballot_proof(checked,policy);proof['independent_review']=checked['independent_review']
   metadata={**(row['meta'] or {}),'individual_vote_coverage':'reconstructed_complete','ballot_reconstruction':proof}
   text=c['source_motion_text'] if mid in correction_reviewed else row['text_content']
   if mid in correction_reviewed:metadata['canonical_source_body_repair']={'original_text':row['text_content'],'method':'same_binary_and_unique_complete_bounded_official_source','independent_review_sha256':review_hash}
   changes.append({'motion_id':mid,'before':row,'before_votes':existing[mid],'after_meta':metadata,'after_text_content':text,'new_choices':[(mid,v['person_id'],v['vote']) for v in checked['votes'] if v['person_id'] not in {x['person_id'] for x in existing[mid]}],'inserted_votes':[]})
  if args.apply:
   insert_rows=[r for c in changes for r in c['new_choices']]
   inserted=execute_values(cur,'INSERT INTO votes(motion_id,person_id,vote) VALUES %s RETURNING id,motion_id,person_id,vote,updated_at',insert_rows,page_size=500,fetch=True) if insert_rows else []
   by_id={c['motion_id']:c for c in changes}
   for vote in inserted:by_id[vote['motion_id']]['inserted_votes'].append(canonical(vote))
   for c in changes:
    cur.execute('UPDATE motions SET text_content=%s,meta=%s WHERE id=%s RETURNING updated_at',(c['after_text_content'],Json(c['after_meta']),c['motion_id']));c['after_updated_at']=str(cur.fetchone()['updated_at'])
  receipt={'mode':'pending_commit' if args.apply else 'dry_run','at':datetime.now(timezone.utc).isoformat(),'plan_sha256':plan_hash,'independent_review_sha256':review_hash,'apply_script_sha256':sha(Path(__file__)),'summary':{'new_ballots':len(new),'canonical_body_repairs':len(corrections),'new_choice_rows':sum(len(c['new_choices']) for c in changes),'existing_choice_rows_preserved':sum(len(c['before_votes']) for c in changes)},'changes':changes}
  path=OUT/('roster-source-pending-receipt.json' if args.apply else 'roster-source-current-preflight.json');path.write_text(json.dumps(receipt,indent=2))
 if args.apply:
  db.commit();receipt['mode']='applied';receipt['committed_at']=datetime.now(timezone.utc).isoformat();receipt_path.write_text(json.dumps(receipt,indent=2))
 else:db.rollback()
 print(json.dumps(receipt['summary']))
except BaseException:
 db.rollback();raise
finally:db.close()
