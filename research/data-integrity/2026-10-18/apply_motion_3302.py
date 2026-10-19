"""Recover the reviewed exact-match outcome only; keep a compare-before-write rollback.

Default dry-run. --apply performs one optimistic update. --rollback reverts only
if that exact update is still current. Does not touch votes or any other motion.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from pipeline import config
from supabase import create_client

ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
parser=argparse.ArgumentParser(description=__doc__)
mode=parser.add_mutually_exclusive_group();mode.add_argument('--apply',action='store_true');mode.add_argument('--rollback',action='store_true')
args=parser.parse_args()
db=create_client(config.SUPABASE_URL,config.SUPABASE_SECRET_KEY or config.SUPABASE_KEY)
receipt_file=OUT/'motion-3302-repair-receipt.json'
if args.rollback:
    receipt=json.loads(receipt_file.read_text())
    after=receipt['after'];before=receipt['before']
    response=db.table('motions').update({'result':before['result'],'meta':before['meta']}).eq('id',3302).eq('updated_at',after['updated_at']).execute()
    if len(response.data)!=1:raise RuntimeError('Rollback held: row changed since repair')
    receipt['rolled_back_at']=datetime.now(timezone.utc).isoformat();receipt_file.write_text(json.dumps(receipt,indent=2));print('Rolled back motion3302')
else:
    plan=json.loads((OUT/'vote-repair-plan.json').read_text())
    candidate=next(c for c in plan['outcome_candidates'] if c['motion_id']==3302)
    source=ROOT/candidate['source_file']
    if hashlib.sha256(source.read_bytes()).hexdigest()!=candidate['source_sha256']:raise RuntimeError('Source changed')
    before=db.table('motions').select('id,result,meta,updated_at,text_content,meeting_id').eq('id',3302).single().execute().data
    if before['result'] is not None or before['text_content']!=candidate['motion_text'] or candidate['match_score']!=1.0:raise RuntimeError('Row no longer matches reviewed candidate')
    metadata={**(before['meta'] or {}),'outcome_recovery':{'method':'exact_normalized_minutes_motion','source_file':candidate['source_file'],'source_sha256':candidate['source_sha256'],'source_quote':candidate['outcome_quote'],'source_motion_text':candidate['source_motion_text']}}
    receipt={'before':before,'proposed':{'result':candidate['proposed_result'],'meta':metadata},'source':candidate,'mode':'dry_run'}
    if args.apply:
        receipt_file.write_text(json.dumps(receipt,indent=2))
        response=db.table('motions').update(receipt['proposed']).eq('id',3302).is_('result','null').eq('updated_at',before['updated_at']).execute()
        if len(response.data)!=1:raise RuntimeError('Repair held: concurrent row update')
        receipt.update({'after':response.data[0],'mode':'applied','applied_at':datetime.now(timezone.utc).isoformat()});receipt_file.write_text(json.dumps(receipt,indent=2));print('Recovered motion3302 CARRIED; rollback receipt saved')
    else:print('Dry-run: exact source validated; motion3302 result null -> CARRIED')
