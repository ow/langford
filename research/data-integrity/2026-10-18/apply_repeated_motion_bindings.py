"""Guarded metadata-only source occurrence binding for six reviewed legacy IDs."""
import argparse,json,hashlib
from pathlib import Path
from datetime import datetime,timezone
import psycopg2
from psycopg2.extras import RealDictCursor,Json
from pipeline import config
from pipeline.ingestion.official_ballots import load_official_minutes
from pipeline.ingestion.canonical_motions import bound_source_motion
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
PLAN=OUT/'repeated-six-source-key-binding-plan.json';REVIEW=OUT/'repeated-six-source-key-binding-independent-review.json';RECEIPT=OUT/'repeated-six-source-key-binding-applied-receipt.json';PENDING=OUT/'repeated-six-source-key-binding-pending-receipt.json'
IDS=[326,1918,1919,1959,2458,2459]
MC='id,meeting_id,agenda_item_id,text_content,result,meta,updated_at,meta IS NULL AS meta_is_sql_null';VC='id,motion_id,person_id,vote,recusal_reason,created_at,updated_at'
canon=lambda x:json.loads(json.dumps(x,default=str))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def capture(p):
 raw=p.read_bytes();return json.loads(raw),hashlib.sha256(raw).hexdigest()
def save(path,obj):
 temp=path.with_suffix('.json.tmp');temp.write_text(json.dumps(canon(obj),indent=2)+'\n');temp.replace(path)
def rows(cur,lock):
 cur.execute(f'SELECT {MC} FROM motions WHERE id=ANY(%s) ORDER BY id'+(' FOR UPDATE' if lock else ''),(IDS,));motions=canon(cur.fetchall())
 cur.execute(f'SELECT {VC} FROM votes WHERE motion_id=ANY(%s) ORDER BY id'+(' FOR UPDATE' if lock else ''),(IDS,));votes=canon(cur.fetchall())
 return motions,votes

def main():
 cli=argparse.ArgumentParser(description=__doc__);modes=cli.add_mutually_exclusive_group();modes.add_argument('--apply',action='store_true');modes.add_argument('--rollback',action='store_true')
 for name in ['plan','review','receipt']:cli.add_argument('--expected-'+name+'-sha256')
 args=cli.parse_args()
 if args.rollback:
  receipt,digest=capture(RECEIPT)
  if receipt['mode']!='applied' or args.expected_receipt_sha256!=digest:raise RuntimeError('Exact applied receipt hash required')
  with psycopg2.connect(config.DATABASE_URL,connect_timeout=15) as db:
   db.set_session(isolation_level='SERIALIZABLE')
   with db.cursor(cursor_factory=RealDictCursor) as cur:
    motions,votes=rows(cur,True)
    if motions!=[c['after_motion'] for c in receipt['changes']] or votes!=[v for c in receipt['changes'] for v in c['before_votes']]:raise RuntimeError('Rollback held: full after rows changed')
    for c in receipt['changes']:cur.execute('UPDATE motions SET meta=%s WHERE id=%s',(None if c['before_motion']['meta_is_sql_null'] else Json(c['before_motion']['meta']),c['motion_id']))
   save(OUT/'repeated-six-source-key-binding-rollback-pending.json',{'receipt_sha256':digest,'restored_ids':IDS});db.commit()
  save(OUT/'repeated-six-source-key-binding-rollback-receipt.json',{'mode':'rolled_back','receipt_sha256':digest,'restored_ids':IDS});return
 plan,plan_hash=capture(PLAN)
 if sorted(c['motion_id'] for c in plan['changes'])!=IDS or len(plan['changes'])!=6:raise RuntimeError('Exact six IDs required')
 for filename,digest in plan['code_sha256s'].items():
  if sha(ROOT/filename)!=digest:raise RuntimeError('Source guards changed since plan')
 for filename,digest in plan['input_sha256'].items():
  if sha(OUT/filename)!=digest:raise RuntimeError('Independent primary identity review changed')
 review_hash=None
 if args.apply:
  review,review_hash=capture(REVIEW)
  if (args.expected_plan_sha256,args.expected_review_sha256)!=(plan_hash,review_hash):raise RuntimeError('Caller must bind exact plan/review bytes')
  if review.get('candidate_plan_sha256')!=plan_hash or review.get('apply_script_sha256')!=sha(Path(__file__)) or sorted(review.get('reviewed_candidate_ids',[]))!=IDS:raise RuntimeError('Independent exact6 script/plan approval required')
  if RECEIPT.exists() or PENDING.exists():raise RuntimeError('Existing or uncertain receipt; never reapply')
 db=psycopg2.connect(config.DATABASE_URL,connect_timeout=15);db.set_session(isolation_level='SERIALIZABLE',readonly=not args.apply)
 try:
  with db.cursor(cursor_factory=RealDictCursor) as cur:
   motions,votes=rows(cur,args.apply)
   if motions!=[c['before_motion'] for c in plan['changes']] or votes!=sorted([v for c in plan['changes'] for v in c['before_votes']],key=lambda v:v['id']):raise RuntimeError('Full original motion/vote CAS failed')
   cur.execute('SELECT id,name FROM people ORDER BY id'+(' FOR SHARE' if args.apply else ''));people=canon(cur.fetchall())
   mids=sorted({c['meeting']['id'] for c in plan['changes']})
   cur.execute('SELECT m.id,m.meeting_date,m.title,m.type,m.archive_path,m.organization_id,m.updated_at,o.classification FROM meetings m JOIN organizations o ON o.id=m.organization_id WHERE m.id=ANY(%s) ORDER BY m.id'+(' FOR SHARE OF m,o' if args.apply else ''),(mids,));meetings={r['id']:canon(r) for r in cur.fetchall()}
   sources={};changes=[]
   for c in plan['changes']:
    mid=c['motion_id'];meeting=meetings[c['meeting']['id']]
    if meeting!=c['meeting']:raise RuntimeError('Catalog source identity changed')
    if meeting['id'] not in sources:sources[meeting['id']]=load_official_minutes(meeting,root=ROOT,people=people,cache_dir='/private/tmp/repeated-motion-apply-native')
    source=sources[meeting['id']];identity=c['current_source_identity']
    if source.get('source_sha256')!=identity['source_sha256']:raise RuntimeError('Official source binary changed')
    if source.get('source_classification')!=c['verified_source_classification'] or source.get('source_classification')!='Council':raise RuntimeError('Native Council scope changed')
    if not source.get('local_date') or source['local_date']!=c['verified_native_date'] or abs((datetime.fromisoformat(source['local_date'])-datetime.fromisoformat(meeting['meeting_date'])).days)>1:raise RuntimeError('Native source meeting date not bound')
    if source.get('source_url')!=c['reviewed_source_url'] or source.get('source_url')!=identity['source_url']:raise RuntimeError('Reviewed official source URL changed')
    if {k:v for k,v in c['after_meta'].items() if k not in ('canonical_source_motion','canonical_identity_review')}!={k:v for k,v in (c['before_motion']['meta'] or {}).items() if k not in ('canonical_source_motion','canonical_identity_review')}:raise RuntimeError('Unrelated metadata alteration')
    block=bound_source_motion({**c['before_motion'],'meta':c['after_meta']},source,meeting['id'])
    if block is None or block['source_block']!=identity['source_block'] or block['result']!=c['before_motion']['result']:raise RuntimeError('Current full native occurrence no longer exact')
    after=c['before_motion']
    if args.apply:
     cur.execute(f'UPDATE motions SET meta=%s WHERE id=%s RETURNING {MC}',(Json(c['after_meta']),mid));after=canon(cur.fetchone())
    changes.append({**c,'after_motion':after})
   receipt={'mode':'pending_commit' if args.apply else 'dry_run','at':datetime.now(timezone.utc).isoformat(),'plan_sha256':plan_hash,'review_sha256':review_hash,'apply_script_sha256':sha(Path(__file__)),'summary':plan['summary'],'changes':changes}
   save(PENDING if args.apply else OUT/'repeated-six-source-key-binding-preflight.json',receipt)
  if args.apply:db.commit();receipt['mode']='applied';save(RECEIPT,receipt)
  else:db.rollback()
  print(json.dumps(receipt['summary']))
 except BaseException:db.rollback();raise
 finally:db.close()
if __name__=='__main__':main()
