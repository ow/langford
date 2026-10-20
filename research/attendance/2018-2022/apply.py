"""Bounded attendance correction: default read-only, shadow rollback rehearsal,
atomic apply, and guarded inverse rollback. Never edits votes/transcripts/roles.

The original 89-meeting before-image and exact reviewed plan are required.
A pending receipt is persisted BEFORE commit; uncertain commits must be checked
with verify.py, never blindly retried. All SQL target identifiers are internal.
"""
import argparse, hashlib, json
from pathlib import Path
from datetime import datetime,timezone
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor,Json,execute_values
from pipeline import config

def canonical(value):return json.dumps(value,default=str,sort_keys=True,separators=(',',':'))
def normalized(value):return json.loads(canonical(value))
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def read_rows(cur,table,ids):
    cur.execute(sql.SQL('SELECT * FROM {} WHERE meeting_id=ANY(%s) ORDER BY id').format(sql.Identifier(table)),(ids,));return normalized(cur.fetchall())
def one_meeting(cur,table,mid):
    cur.execute(sql.SQL('SELECT id,status,meta,updated_at FROM {} WHERE id=%s').format(sql.Identifier(table)),(mid,));return normalized(cur.fetchone())
def protected(cur,ids):
    queries={
    'votes':('SELECT v.* FROM votes v JOIN motions mo ON mo.id=v.motion_id WHERE mo.meeting_id=ANY(%s)',(ids,)),
    'transcripts':('SELECT * FROM transcript_segments WHERE meeting_id=ANY(%s)',(ids,)),
    'memberships':('SELECT * FROM memberships',()),
    'people':('SELECT * FROM people',())}
    out={}
    for key,(query,args)in queries.items():
        cur.execute('SELECT count(*) count,md5(COALESCE(string_agg(row_to_json(t)::text,\'\' ORDER BY t.id),\'\')) hash FROM ('+query+') t',args)
        out[key]=dict(cur.fetchone())
    return out

def apply_rows(cur,atable,mtable,plan,before):
    old={(r['meeting_id'],r['person_id']):r for r in before['attendance']};desired={(r['meeting_id'],r['person_id']):r for r in plan['records']}
    current=read_rows(cur,atable,plan['finite_meeting_ids']);seen={(r['meeting_id'],r['person_id']):r for r in current}
    for key,row in seen.items():
        if key not in desired:assert row==old.get(key),f'Protected or unexpected attendance changed: {key}'
        else:
            wanted=desired[key]
            assert row==old.get(key)or all(row[k]==wanted[k]for k in ['attendance_mode','notes']),f'Stale target before-image: {key}'
    assert set(old)<=set(seen),'A before-image attendance row was deleted concurrently'
    changes=[]
    pending=[(key,row)for key,row in desired.items()if not(seen.get(key)and all(seen[key][k]==row[k]for k in ['attendance_mode','notes']))]
    updates=[(seen[key]['id'],row['attendance_mode'],row['notes'])for key,row in pending if key in seen]
    inserts=[(row['meeting_id'],row['person_id'],row['attendance_mode'],row['notes'])for key,row in pending if key not in seen]
    after=[]
    if updates:
        query=sql.SQL('UPDATE {} a SET attendance_mode=v.mode,notes=v.notes,updated_at=now() FROM (VALUES %s) v(id,mode,notes) WHERE a.id=v.id RETURNING a.*').format(sql.Identifier(atable)).as_string(cur)
        after.extend(execute_values(cur,query,updates,page_size=1000,fetch=True))
    if inserts:
        query=sql.SQL('INSERT INTO {} (meeting_id,person_id,attendance_mode,notes) VALUES %s RETURNING *').format(sql.Identifier(atable)).as_string(cur)
        after.extend(execute_values(cur,query,inserts,page_size=1000,fetch=True))
    assert len(after)==len(pending)
    for row in normalized(after):changes.append({'before':seen.get((row['meeting_id'],row['person_id'])),'after':row})
    mid=plan['cancellation']['meeting_id'];existing=one_meeting(cur,mtable,mid)
    base=next(m for m in before['meetings']if m['id']==mid)
    evidence={'schema':'meeting-cancellation/v1',**plan['cancellation']}
    wanted_meta={**(base['meta']or{}),'cancellation_evidence':evidence}
    meeting_change=None
    if existing['status']!='Cancelled'or existing['meta']!=wanted_meta:
        assert existing['status']==base['status']and existing['meta']==base['meta'],'Stale cancellation before-image'
        cur.execute(sql.SQL('UPDATE {} SET status=%s,meta=%s,updated_at=now() WHERE id=%s RETURNING id,status,meta,updated_at').format(sql.Identifier(mtable)),('Cancelled',Json(wanted_meta),mid))
        meeting_change={'before':existing,'after':normalized(cur.fetchone())}
    return changes,meeting_change

def undo(cur,atable,mtable,changes,meeting_change):
    if changes:
        cur.execute(sql.SQL('SELECT * FROM {} WHERE id=ANY(%s)').format(sql.Identifier(atable)),([ch['after']['id']for ch in changes],))
        current={row['id']:row for row in normalized(cur.fetchall())}
        assert all(current.get(ch['after']['id'])==ch['after']for ch in changes),'Rollback target changed after apply'
    updates=[(ch['before']['id'],ch['before']['attendance_mode'],ch['before']['notes'])for ch in changes if ch['before']]
    inserts=[ch['after']['id']for ch in changes if ch['before']is None]
    if updates:
        query=sql.SQL('UPDATE {} a SET attendance_mode=v.mode,notes=v.notes,updated_at=now() FROM (VALUES %s) v(id,mode,notes) WHERE a.id=v.id').format(sql.Identifier(atable)).as_string(cur)
        execute_values(cur,query,updates,page_size=1000)
    if inserts:cur.execute(sql.SQL('DELETE FROM {} WHERE id=ANY(%s)').format(sql.Identifier(atable)),(inserts,))
    if meeting_change:
        old,new=meeting_change['before'],meeting_change['after'];assert one_meeting(cur,mtable,new['id'])==new,'Rollback cancellation changed after apply'
        cur.execute(sql.SQL('UPDATE {} SET status=%s,meta=%s,updated_at=%s WHERE id=%s').format(sql.Identifier(mtable)),(old['status'],Json(old['meta'])if old['meta']is not None else None,old['updated_at'],old['id']))

def main():
    a=argparse.ArgumentParser();a.add_argument('mode',choices=['preflight','rehearse','apply','rollback']);a.add_argument('--plan',required=True);a.add_argument('--before',required=True);a.add_argument('--receipt',required=True);args=a.parse_args()
    plan=json.loads(Path(args.plan).read_text());before=json.loads(Path(args.before).read_text());receipt_path=Path(args.receipt)
    assert hashlib.sha256(Path(args.before).read_bytes()).hexdigest()==plan['before_sha256']
    assert len(plan['finite_meeting_ids'])==89 and len(plan['records'])==605
    assert set(r['person_id']for r in plan['records'])=={143,133,134,135,136,35,137}
    for source in plan['sources']:assert hashlib.sha256(Path(source['file_path']).read_bytes()).hexdigest()==source['source_sha256']
    for r in plan['records']:
        e=json.loads(r['notes']);assert e['meeting_id']==r['meeting_id']and e['person_id']==r['person_id']
    c=psycopg2.connect(config.DATABASE_URL,connect_timeout=15);c.set_session(readonly=args.mode=='preflight',isolation_level='REPEATABLE READ')
    try:
      with c.cursor(cursor_factory=RealDictCursor)as q:
        q.execute("SET LOCAL lock_timeout='5s'");q.execute("SET LOCAL statement_timeout='60s'")
        ids=plan['finite_meeting_ids'];baseline_rows=read_rows(q,'attendance',ids);baseline_meeting=one_meeting(q,'meetings',123);p_before=protected(q,ids)
        if args.mode=='preflight':
            assert baseline_rows==before['attendance'],'Attendance snapshot changed; review fresh before-image before proceeding'
            receipt={'outcome':'preflight_passed','before_attendance_sha256':digest(baseline_rows),'protected':p_before,'target_records':len(plan['records'])};c.rollback()
        elif args.mode=='rehearse':
            assert baseline_rows==before['attendance'],'Attendance snapshot changed'
            q.execute('CREATE TEMP SEQUENCE attendance_rehearsal_seq')
            q.execute('CREATE TEMP TABLE attendance_rehearsal (LIKE attendance INCLUDING DEFAULTS INCLUDING CONSTRAINTS)')
            q.execute("ALTER TABLE attendance_rehearsal ALTER COLUMN id SET DEFAULT nextval('pg_temp.attendance_rehearsal_seq')")
            q.execute('INSERT INTO attendance_rehearsal SELECT * FROM attendance WHERE meeting_id=ANY(%s)',(ids,))
            q.execute("SELECT setval('pg_temp.attendance_rehearsal_seq',COALESCE((SELECT max(id)FROM attendance_rehearsal),0)+1,false)")
            q.execute('CREATE TEMP TABLE meeting_rehearsal AS SELECT id,status,meta,updated_at FROM meetings WHERE id=123')
            q.execute('CREATE TRIGGER rehearsal_attendance_timestamp BEFORE UPDATE ON attendance_rehearsal FOR EACH ROW EXECUTE FUNCTION public.update_timestamp()')
            q.execute('CREATE TRIGGER rehearsal_meeting_timestamp BEFORE UPDATE ON meeting_rehearsal FOR EACH ROW EXECUTE FUNCTION public.update_timestamp()')
            changes,meeting_change=apply_rows(q,'attendance_rehearsal','meeting_rehearsal',plan,before)
            again,again_meeting=apply_rows(q,'attendance_rehearsal','meeting_rehearsal',plan,before)
            assert not again and again_meeting is None,'Re-apply is not idempotent'
            undo(q,'attendance_rehearsal','meeting_rehearsal',changes,meeting_change)
            logical=lambda rows:[{k:v for k,v in row.items()if k!='updated_at'}for row in rows]
            assert logical(read_rows(q,'attendance_rehearsal',ids))==logical(baseline_rows)
            assert logical([one_meeting(q,'meeting_rehearsal',123)])==logical([baseline_meeting])
            assert read_rows(q,'attendance',ids)==baseline_rows and one_meeting(q,'meetings',123)==baseline_meeting
            assert protected(q,ids)==p_before
            receipt={'outcome':'shadow_rollback_rehearsal_passed','attendance_changes':len(changes),'inserts':sum(ch['before']is None for ch in changes),'updates':sum(ch['before']is not None for ch in changes),'idempotent_second_apply_changes':0,'restored_business_before_image_sha256':digest(logical(baseline_rows)),'timestamp_behavior':'Existing updated_at trigger retained during apply and rollback','protected':p_before,'live_writes':0};c.rollback()
        elif args.mode=='apply':
            q.execute('SELECT id FROM attendance WHERE meeting_id=ANY(%s) FOR UPDATE',(ids,));q.fetchall()
            q.execute('SELECT id FROM meetings WHERE id=123 FOR UPDATE');q.fetchall()
            changes,meeting_change=apply_rows(q,'attendance','meetings',plan,before)
            assert protected(q,ids)==p_before,'Protected rows changed within correction transaction'
            if receipt_path.exists():
                prior=json.loads(receipt_path.read_text())
                assert prior['outcome']=='committed'and prior['plan_sha256']==hashlib.sha256(Path(args.plan).read_bytes()).hexdigest(),'Check uncertain/different receipt before proceeding'
                assert not changes and meeting_change is None,'Do not overwrite an earlier rollback receipt'
                receipt={**prior,'idempotent_reapply_changes':0};c.rollback()
            else:
                receipt={'outcome':'pending_commit','at':datetime.now(timezone.utc).isoformat(),'plan_sha256':hashlib.sha256(Path(args.plan).read_bytes()).hexdigest(),'protected':p_before,'changes':changes,'meeting_change':meeting_change}
                receipt_path.write_text(json.dumps(receipt,indent=2)+'\n');c.commit()
                receipt['outcome']='committed';receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
        else:
            prior=json.loads(receipt_path.read_text());assert prior['outcome']=='committed'
            undo(q,'attendance','meetings',prior['changes'],prior['meeting_change']);assert protected(q,ids)==p_before
            c.commit();receipt={'outcome':'rollback_committed','restored_attendance':len(prior['changes'])};receipt_path=receipt_path.with_suffix('.rollback.json')
      receipt['plan_sha256']=hashlib.sha256(Path(args.plan).read_bytes()).hexdigest()
      receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
      print(json.dumps({k:v for k,v in receipt.items()if k not in ['changes','meeting_change']},default=str))
    finally:c.close()
if __name__=='__main__':main()
