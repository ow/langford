"""Validate/apply reviewed complete documentary ballots, atomically and reversibly.

No inferred writes by default. --meeting may select reviewed pilot meetings.
Existing choices are never overwritten: conflicts hold the whole ballot.
"""
import argparse
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor,Json,execute_values
from pipeline import config
from pipeline.ingestion.vote_evidence import normalize_text,outcome_family

ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--apply',action='store_true');parser.add_argument('--rollback',action='store_true');parser.add_argument('--meeting',type=int,action='append');parser.add_argument('--receipt',type=Path,default=OUT/'full-ballot-repair-receipt.json');args=parser.parse_args()
if args.apply and args.rollback:parser.error('Choose apply or rollback')
if args.receipt.exists() and json.loads(args.receipt.read_text()).get('mode')=='applied' and not args.rollback:raise RuntimeError('Applied receipt already exists; do not overwrite rollback evidence')
plan_bytes=(OUT/'full-ballot-audit.json').read_bytes();plan=json.loads(plan_bytes);snapshot=json.loads((OUT/'ballot-source-snapshot.json').read_text());prior={m['id']:m for m in snapshot['motions']};rule=json.loads((OUT/'ballot-recording-rule.json').read_text())
selected=[m for m in plan['motions'] if m['status']=='reconstructable_candidate' and (not args.meeting or m['meeting_id'] in args.meeting)]
held=[];changes=[];already_complete=[]
if not args.rollback:
    checks={'parser_sha256':ROOT/'apps/pipeline/pipeline/ingestion/ballot_reconstruction.py','motion_gate_sha256':ROOT/'apps/pipeline/pipeline/ingestion/vote_evidence.py','audit_script_sha256':OUT/'audit_full_ballots.py'}
    for key,file in checks.items():
        if hashlib.sha256(file.read_bytes()).hexdigest()!=plan['summary'].get(key):raise RuntimeError('Plan code version changed; rerun and independently review')
with psycopg2.connect(config.DATABASE_URL,connect_timeout=15) as db:
 with db.cursor(cursor_factory=RealDictCursor) as cur:
  if args.rollback:
   receipt=json.loads(args.receipt.read_text());ids=[c['motion_id'] for c in receipt['changes']]
   cur.execute('SELECT id,meta,updated_at FROM motions WHERE id=ANY(%s) FOR UPDATE',(ids,));current={r['id']:r for r in cur.fetchall()}
   for c in receipt['changes']:
    if current[c['motion_id']]['meta']!=c['after_meta'] or str(current[c['motion_id']]['updated_at'])!=c['after_updated_at']:raise RuntimeError('Rollback held: motion changed')
   inserted=[v for c in receipt['changes'] for v in c['inserted_votes']]
   if inserted:
    cur.execute('SELECT id,motion_id,person_id,vote,updated_at FROM votes WHERE id=ANY(%s) FOR UPDATE',([r['id'] for r in inserted],));live={r['id']:r for r in cur.fetchall()}
    for old in inserted:
     if old['id'] not in live or any(str(live[old['id']][key])!=str(old[key]) for key in ('motion_id','person_id','vote','updated_at')):raise RuntimeError('Rollback held: inserted vote changed')
    cur.execute('DELETE FROM votes WHERE id=ANY(%s)',([r['id'] for r in inserted],))
   execute_values(cur,'UPDATE motions AS m SET meta=v.meta FROM (VALUES %s) AS v(id,meta) WHERE m.id=v.id',[(c['motion_id'],Json(c['before_meta'])) for c in receipt['changes']],template='(%s,%s::jsonb)')
   receipt['rolled_back_at']=datetime.now(timezone.utc).isoformat();args.receipt.write_text(json.dumps(receipt,indent=2,default=str));print('Rolled back',len(inserted),'inserted choices')
  else:
   ids=[m['motion_id'] for m in selected]
   cur.execute('SELECT id,meeting_id,text_content,result,meta,updated_at FROM motions WHERE id=ANY(%s) FOR UPDATE',(ids,));current={r['id']:r for r in cur.fetchall()}
   cur.execute('SELECT id,motion_id,person_id,vote,updated_at FROM votes WHERE motion_id=ANY(%s) FOR UPDATE',(ids,));existing={}
   for row in cur.fetchall():existing.setdefault(row['motion_id'],{})[row['person_id']]=row
   cur.execute('SELECT id,name FROM people');names={r['id']:r['name'] for r in cur.fetchall()}
   cur.execute("SELECT m.person_id,m.start_date,m.end_date FROM memberships m JOIN organizations o ON o.id=m.organization_id WHERE o.municipality_id=1 AND o.classification='Council'");live_memberships=list(cur.fetchall())
   source_hashes={}
   for m in selected:
    path=ROOT/m['source_file']
    if m['source_file'] not in source_hashes:source_hashes[m['source_file']]=hashlib.sha256(path.read_bytes()).hexdigest()
    if source_hashes[m['source_file']]!=m['source_sha256']:raise RuntimeError('Official source changed')
    if not rule['enabled_from']<=m['source_date']<=rule['enabled_through'] and 'UNANIMOUS' not in m['source_result']:raise RuntimeError('Rule not validated for source date')
    row=current.get(m['motion_id'])
    if not row or row['meeting_id']!=m['meeting_id'] or row['text_content']!=prior[m['motion_id']]['text_content'] or outcome_family(row['result'])!=outcome_family(m['source_result']):raise RuntimeError('Motion changed or mismatched')
    choices={v['person_id']:v['vote'] for v in m['votes']}
    if 'UNANIMOUS' in m['source_result'] and any(vote!='Yes' for vote in choices.values()):
     held.append({'motion_id':m['motion_id'],'reason':'unanimous_result_conflicts_with_named_choice'});continue
    if any(names.get(v['person_id'])!=v['person_name'] for v in m['votes']):raise RuntimeError('Canonical identity changed')
    if m['membership_evidence']=='dated_db_council_membership':
     active={entry['person_id'] for entry in live_memberships if entry['start_date'] and str(entry['start_date'])<=m['source_date'] and (not entry['end_date'] or str(entry['end_date'])>=m['source_date'])}
     if not set(choices)<=active:
      held.append({'motion_id':m['motion_id'],'reason':'live_membership_no_longer_supports_roster'});continue
    old=existing.get(m['motion_id'],{})
    if any(person not in choices or vote['vote']!=choices[person] for person,vote in old.items()):
     held.append({'motion_id':m['motion_id'],'reason':'existing_vote_conflicts_with_reconstructed_ballot'});continue
    if (row['meta'] or {}).get('individual_vote_coverage')=='reconstructed_complete' and (row['meta'] or {}).get('ballot_reconstruction',{}).get('source_sha256')==m['source_sha256'] and set(old)==set(choices):
     already_complete.append(m['motion_id']);continue
    proof={key:m[key] for key in ('source_file','source_format','source_url','source_sha256','source_date','stored_date','source_result','source_motion_text','source_block','roster_quote','membership_evidence','presence_events','initial_arrival_adjustments','votes')}
    proof['votes']=[dict(v) for v in m['votes']]
    if 'UNANIMOUS' in m['source_result']:
     for vote in proof['votes']:
      if vote['evidence'].startswith('inferred_'):vote['evidence']='inferred_explicit_unanimity'
     proof['inference_basis']='explicit_unanimity_with_validated_per_vote_roster'
    else:proof['inference_basis']='official_dissent_recording_convention_with_validated_per_vote_roster'
    proof['choice_provenance']={f"person_{v['person_id']}":v['evidence'] for v in proof['votes']}
    proof.update({'rule_id':rule['rule_id'],'bylaw_url':rule['bylaw_url'],'bylaw_sha256':rule['bylaw_sha256'],'policy_checked_as_of':rule['validated_as_of'],'method':'documentary_reconstruction_not_explicit_rollcall'})
    metadata={**(row['meta'] or {}),'individual_vote_coverage':'reconstructed_complete','ballot_reconstruction':proof}
    changes.append({'motion_id':m['motion_id'],'before_meta':row['meta'],'before_updated_at':str(row['updated_at']),'before_votes':list(old.values()),'after_meta':metadata,'new_choices':[(m['motion_id'],v['person_id'],v['vote']) for v in m['votes'] if v['person_id'] not in old],'inserted_votes':[]})
   if args.apply and changes:
    insert_rows=[r for c in changes for r in c['new_choices']]
    inserted=[]
    if insert_rows:
     inserted=execute_values(cur,'INSERT INTO votes(motion_id,person_id,vote) VALUES %s ON CONFLICT(motion_id,person_id) DO NOTHING RETURNING id,motion_id,person_id,vote,updated_at',insert_rows,page_size=500,fetch=True)
     if len(inserted)!=len(insert_rows):raise RuntimeError('Concurrent vote insertion; transaction held')
    for vote in inserted:next(c for c in changes if c['motion_id']==vote['motion_id'])['inserted_votes'].append(dict(vote))
    updated=execute_values(cur,'UPDATE motions AS m SET meta=v.meta FROM (VALUES %s) AS v(id,meta) WHERE m.id=v.id RETURNING m.id,m.updated_at',[(c['motion_id'],Json(c['after_meta'])) for c in changes],template='(%s,%s::jsonb)',page_size=500,fetch=True)
    timestamps={r['id']:r['updated_at'] for r in updated}
    for c in changes:c['after_updated_at']=str(timestamps[c['motion_id']])
   receipt={'mode':'applied' if args.apply else 'dry_run','created_at':datetime.now(timezone.utc).isoformat(),'summary':{'selected_motions':len(selected),'validated_motions':len(changes),'held':len(held),'already_complete':len(already_complete),'new_vote_rows':sum(len(c['new_choices']) for c in changes)},'held':held,'changes':changes,'plan_sha256':hashlib.sha256(plan_bytes).hexdigest(),'apply_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
   args.receipt.write_text(json.dumps(receipt,indent=2,default=str));print(json.dumps(receipt['summary']))
