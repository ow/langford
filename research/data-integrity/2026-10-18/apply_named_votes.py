"""Atomic insert of reviewed, explicit named opposition, with a guarded rollback.

Default dry-run validates live rows and local source hashes. --apply inserts only
missing No votes; never infers other choices or overwrites any vote. --rollback
reverts only unchanged rows inserted by this exact run and restores prior meta.
"""
import argparse
from collections import defaultdict
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor,Json
from pipeline import config
from pipeline.ingestion.vote_evidence import normalize_text

ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group();mode.add_argument('--apply',action='store_true');mode.add_argument('--rollback',action='store_true');args=parser.parse_args()
receipt_path=OUT/'named-vote-repair-receipt.json'
if receipt_path.exists() and json.loads(receipt_path.read_text()).get('mode') == 'applied' and not args.rollback:
    raise RuntimeError('Applied receipt already exists; use audit for verification or --rollback to undo this exact run')
connection=psycopg2.connect(config.DATABASE_URL,connect_timeout=15)
try:
    with connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cur:
            if args.rollback:
                receipt=json.loads(receipt_path.read_text())
                for change in receipt['changes']:
                    if change.get('reverted_reason'):continue
                    cur.execute('SELECT meta,updated_at FROM motions WHERE id=%s FOR UPDATE',(change['motion_id'],));current=cur.fetchone()
                    if current['meta']!=change['after_meta'] or str(current['updated_at'])!=change['after_updated_at']:raise RuntimeError('Rollback held: motion changed')
                    for row in change['inserted_votes']:
                        cur.execute('DELETE FROM votes WHERE id=%s AND motion_id=%s AND person_id=%s AND vote=%s AND updated_at=%s RETURNING id',(row['id'],row['motion_id'],row['person_id'],row['vote'],row['updated_at']))
                        if not cur.fetchone():raise RuntimeError('Rollback held: inserted vote changed')
                    cur.execute('UPDATE motions SET meta=%s WHERE id=%s',(Json(change['before_meta']),change['motion_id']))
                receipt['rolled_back_at']=datetime.now(timezone.utc).isoformat();receipt_path.write_text(json.dumps(receipt,indent=2,default=str));print('Rolled back inserted named votes')
            else:
                plan=json.loads((OUT/'named-vote-repair-plan.json').read_text());snapshot={m['id']:m for m in json.loads((OUT/'motions-audit.json').read_text())}
                grouped=defaultdict(list)
                for candidate in plan['candidates']:
                    path=ROOT/candidate['source_file'];source=path.read_text()
                    if hashlib.sha256(path.read_bytes()).hexdigest()!=candidate['source_sha256'] or candidate['source_quote'] not in source:raise RuntimeError('Source changed or quote missing')
                    grouped[candidate['motion_id']].append(candidate)
                changes=[]
                for mid,candidates in sorted(grouped.items()):
                    cur.execute('SELECT id,meeting_id,text_content,result,meta,updated_at FROM motions WHERE id=%s FOR UPDATE',(mid,));motion=cur.fetchone()
                    if motion['text_content']!=snapshot[mid]['text_content'] or motion['result']!=snapshot[mid]['result']:raise RuntimeError('Motion changed')
                    evidence=[];new=[]
                    for candidate in candidates:
                        if motion['meeting_id']!=candidate['meeting_id'] or normalize_text(motion['text_content'])!=normalize_text(candidate['matched_motion_text']):raise RuntimeError('Source motion no longer exact')
                        cur.execute('SELECT name FROM people WHERE id=%s',(candidate['person_id'],));person=cur.fetchone()
                        if not person or person['name']!=candidate['person_name']:raise RuntimeError('Person identity changed')
                        cur.execute('SELECT vote FROM votes WHERE motion_id=%s AND person_id=%s',(mid,candidate['person_id']));prior=cur.fetchone()
                        if prior:
                            if prior['vote']!='No':raise RuntimeError('Conflicting vote already exists')
                            continue
                        evidence.append({**candidate,'method':'explicit_named_vote','partial_record':True})
                        if args.apply:
                            cur.execute("INSERT INTO votes(motion_id,person_id,vote) VALUES(%s,%s,'No') RETURNING id,motion_id,person_id,vote,updated_at",(mid,candidate['person_id']));new.append(dict(cur.fetchone()))
                    if not evidence:continue
                    before=motion['meta'];after={**(before or {}),'individual_vote_coverage':'named_only','named_vote_backfill':(before or {}).get('named_vote_backfill',[])+evidence}
                    changed={'motion_id':mid,'before_meta':before,'before_updated_at':str(motion['updated_at']),'after_meta':after,'inserted_votes':new,'evidence':evidence}
                    if args.apply:
                        cur.execute('UPDATE motions SET meta=%s WHERE id=%s RETURNING updated_at',(Json(after),mid));changed['after_updated_at']=str(cur.fetchone()['updated_at'])
                    changes.append(changed)
                receipt={'mode':'applied' if args.apply else 'dry_run','at':datetime.now(timezone.utc).isoformat(),'changes':changes,'inserted_votes':sum(len(c['inserted_votes']) for c in changes),'candidate_votes':sum(len(c['evidence']) for c in changes)}
                receipt_path.write_text(json.dumps(receipt,indent=2,default=str));print(json.dumps({'mode':receipt['mode'],'motions':len(changes),'candidate_votes':receipt['candidate_votes'],'inserted_votes':receipt['inserted_votes']}))
finally:connection.close()
