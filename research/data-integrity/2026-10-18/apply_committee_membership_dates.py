"""Exact four-row committee appointment repair; defaults to read-only validation.

--apply requires an independent review bound to plan/script hashes and all four
membership IDs. --rollback restores original date/meta only if every applied row
still equals the receipt. No people, votes, Council memberships or links change.
"""
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor,Json
from pipeline import config
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');parser.add_argument('--rollback',action='store_true');args=parser.parse_args()
if args.apply and args.rollback:parser.error('Choose apply or rollback')
canonical=lambda x:json.loads(json.dumps(x,default=str))
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
receipt_path=OUT/'committee-membership-date-applied-receipt.json'
plan_path=OUT/'committee-membership-date-correction-plan.json';plan_bytes=plan_path.read_bytes();plan=json.loads(plan_bytes);digest=hashlib.sha256(plan_bytes).hexdigest()
for proof in plan['source_proofs'].values():
 if sha(ROOT/proof['source_file'])!=proof['source_sha256']:raise RuntimeError('Official appointment source changed')
changes=plan['changes'];ids=[r['membership_id']for r in changes]
if len(changes)!=4 or len(set(ids))!=4 or {r['person_id']for r in changes}!={20,21,34,40} or any(r['organization_id']!=9 for r in changes):raise RuntimeError('Exact four-row reviewed scope changed')
review=None
if args.apply:
 if receipt_path.exists():raise RuntimeError('Receipt exists; do not reapply or replace rollback evidence')
 review_path=OUT/'committee-membership-date-independent-review.json';review=json.loads(review_path.read_text())
 if review.get('plan_sha256')!=digest or set(review.get('reviewed_membership_ids',[]))!=set(ids) or review.get('apply_script_sha256')!=sha(Path(__file__)):raise RuntimeError('Independent review does not bind exact plan/script/four rows')
if args.rollback:
 receipt=json.loads(receipt_path.read_text())
 if receipt['mode']!='applied' or receipt['plan_sha256']!=digest:raise RuntimeError('No matching applied receipt')
 expected={r['membership_id']:r['after']for r in receipt['changes']}
else:expected={r['membership_id']:r['before']for r in changes}
db=psycopg2.connect(config.DATABASE_URL,connect_timeout=15);db.set_session(isolation_level='SERIALIZABLE',readonly=not(args.apply or args.rollback))
try:
 with db.cursor(cursor_factory=RealDictCursor)as cur:
  suffix=' FOR UPDATE'if args.apply or args.rollback else''
  cur.execute('SELECT id,to_jsonb(m) row FROM memberships m WHERE id=ANY(%s) ORDER BY id'+suffix,(ids,));current={r['id']:canonical(r['row'])for r in cur.fetchall()}
  if current!=expected:raise RuntimeError('Concurrent membership change; entire batch held')
  applied=[]
  for change in changes:
   target=change['before']if args.rollback else change['after']
   if args.apply or args.rollback:
    cur.execute('UPDATE memberships SET start_date=%s,end_date=%s,meta=%s WHERE id=%s RETURNING to_jsonb(memberships)',(target['start_date'],target['end_date'],Json(target['meta']),change['membership_id']));after=canonical(cur.fetchone()['to_jsonb'])
   else:after=target
   applied.append({'membership_id':change['membership_id'],'before':current[change['membership_id']],'after':after})
  result={'mode':'rollback_pending_commit'if args.rollback else'pending_commit'if args.apply else'dry_run','at':datetime.now(timezone.utc).isoformat(),'plan_sha256':digest,'apply_script_sha256':sha(Path(__file__)),'changes':applied}
  path=OUT/('committee-membership-date-rollback-receipt.json'if args.rollback else'committee-membership-date-pending-receipt.json'if args.apply else'committee-membership-date-preflight.json');path.write_text(json.dumps(result,indent=2)+'\n')
 if args.apply or args.rollback:
  db.commit();result['mode']='rolled_back'if args.rollback else'applied';result['committed_at']=datetime.now(timezone.utc).isoformat();(path if args.rollback else receipt_path).write_text(json.dumps(result,indent=2)+'\n')
 else:db.rollback()
 print(json.dumps({'mode':result['mode'],'memberships':len(applied),'database_writes':4 if args.apply or args.rollback else 0}))
except BaseException:
 db.rollback();raise
finally:db.close()
