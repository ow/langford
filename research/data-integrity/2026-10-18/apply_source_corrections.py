"""Atomic reviewed official-motion corrections and complete documentary ballots.

Default prepares an exact live CAS plan; --apply consumes that frozen plan.
--rollback reverses only unchanged records inserted/updated by this transaction.
No summaries, transcript rows, meeting records or legacy motion IDs are changed.
"""
from pathlib import Path
from datetime import datetime,timezone
from collections import defaultdict
import argparse,json,hashlib,re
import psycopg2
from psycopg2.extras import RealDictCursor,Json,execute_values
from pipeline import config
from pipeline.ingestion.vote_evidence import normalize_text,outcome_family

ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');parser.add_argument('--rollback',action='store_true');args=parser.parse_args()
if args.apply and args.rollback:parser.error('Choose one mutation')
planpath=OUT/'source-correction-atomic-plan.json';receiptpath=OUT/'source-correction-atomic-receipt.json'
reviewpath=OUT/'extra-source-anchor-independent-review.json';reviewbytes=reviewpath.read_bytes();reviewhash=hashlib.sha256(reviewbytes).hexdigest();review=json.loads(reviewbytes)
selected=[r for r in review['records']if r['status']=='reviewed_source_correction'];assert len(selected)==40
proposals={r['motion_id']:r for filename in['source-anchor-reconciliation.json','semantic-ballot-proposals.json']for r in json.loads((OUT/filename).read_text())['motions']if r['status']=='reconstructable_candidate'}
policy={**json.loads((ROOT/'apps/pipeline/pipeline/ingestion/policies/langford-voting.json').read_text()),**json.loads((OUT/'policy-refresh-verification.json').read_text())}
scriptsha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
serial=lambda data:json.loads(json.dumps(data,default=str))

def source_guard(record):
 assert hashlib.sha256((ROOT/record['source_file']).read_bytes()).hexdigest()==record['source_sha256'],'official_source_changed'

with psycopg2.connect(config.DATABASE_URL,connect_timeout=20)as db:
 db.set_session(isolation_level='SERIALIZABLE')
 with db.cursor(cursor_factory=RealDictCursor)as cur:
  if args.rollback:
   receipt=json.loads(receiptpath.read_text());assert receipt['mode']=='applied'
   for change in receipt['changes']:
    cur.execute('SELECT id,text_content,result,meta,updated_at FROM motions WHERE id=%s FOR UPDATE',(change['motion_id'],));row=serial(dict(cur.fetchone()))
    assert row==change['after_motion'],'rollback_motion_concurrently_changed'
    for vote in change['inserted_votes']:
     cur.execute('SELECT id,motion_id,person_id,vote,updated_at FROM votes WHERE id=%s FOR UPDATE',(vote['id'],));assert serial(dict(cur.fetchone()))==vote,'rollback_inserted_vote_changed'
    cur.execute('DELETE FROM votes WHERE id=ANY(%s)',([v['id']for v in change['inserted_votes']],))
    cur.execute('UPDATE motions SET text_content=%s,result=%s,meta=%s WHERE id=%s',(change['before_motion']['text_content'],change['before_motion']['result'],Json(change['before_motion']['meta']),change['motion_id']))
   db.commit()
   receipt['rolled_back_at']=datetime.now(timezone.utc).isoformat();receiptpath.write_text(json.dumps(receipt,indent=2)+'\n');print('Rolled back',len(receipt['changes']),'source corrections')
  elif not args.apply:
   assert not receiptpath.exists(),'do_not_replace_applied_rollback_receipt'
   ids=[r['motion_id']for r in selected]
   cur.execute('SELECT id,meeting_id,agenda_item_id,text_content,result,meta,updated_at FROM motions WHERE id=ANY(%s) FOR UPDATE',(ids,));current={r['id']:serial(dict(r))for r in cur.fetchall()}
   assert len(current)==40
   cur.execute('SELECT id,motion_id,person_id,vote,updated_at FROM votes WHERE motion_id=ANY(%s) ORDER BY id FOR UPDATE',(ids,));existing=defaultdict(list)
   for row in cur.fetchall():existing[row['motion_id']].append(serial(dict(row)))
   cur.execute('SELECT id,name FROM people');names={r['id']:r['name']for r in cur.fetchall()}
   cur.execute("SELECT m.person_id,m.start_date,m.end_date FROM memberships m JOIN organizations o ON o.id=m.organization_id WHERE o.municipality_id=1 AND o.classification='Council'");members=list(cur.fetchall())
   changes=[]
   for record in selected:
    mid=record['motion_id'];row=current[mid];source_guard(record);proposal=proposals[mid]
    assert row['meeting_id']==record['meeting_id']and row['text_content']==record['original_motion_text'],'motion_body_changed'
    assert outcome_family(row['result'])==outcome_family(proposal['source_result']),'motion_outcome_conflicts'
    active={m['person_id']for m in members if m['start_date']and str(m['start_date'])<=record['source_date']and(not m['end_date']or str(m['end_date'])>=record['source_date'])}
    choices={v['person_id']:v['vote']for v in record['choices']};assert choices.keys()<=active and len(choices)>=4,'current_dated_membership_mismatch'
    assert all(choices.get(v['person_id'])==v['vote']for v in existing[mid]),'current_existing_choice_conflict'
    assert policy['enabled_from']<=record['source_date']<=policy['enabled_through']or'UNANIMOUS'in proposal['source_result'],'procedure_scope_date_unverified'
    explicit={pid for proof in record['named_choice_proof']for pid in proof['person_ids']};oldproof={v['person_id']:v for v in proposal['votes']};votes=[]
    for pid,vote in sorted(choices.items()):
     assert oldproof[pid]['person_name']==names[pid],'canonical_person_changed'
     evidence='explicit_named'if pid in explicit else'inferred_explicit_unanimity'if'UNANIMOUS'in proposal['source_result']else'inferred_official_dissent_recording_rule'
     quote=oldproof[pid]['source_quote']if pid in explicit else record['outcome_quote']
     assert normalize_text(quote)in normalize_text(record['source_block']),'choice_quote_not_in_exact_native_block'
     votes.append({'person_id':pid,'person_name':names[pid],'vote':vote,'evidence':evidence,'source_quote':quote})
    body='committee_of_the_whole'if record['source_body']=='Committee of the Whole'else'council'
    proof={k:record[k]for k in['source_file','source_url','source_sha256','source_date','source_motion_text','source_block','roster_quote','native_text_sha256']}
    proof.update({'source_format':proposal['source_format'],'source_result':proposal['source_result'],'stored_date':proposal['stored_date'],'source_classification':record['source_body'],'voting_body':body,
     'outcome_role':'committee_guidance_or_recommendation'if body=='committee_of_the_whole'else'council_decision','scope_basis':policy.get('committee_of_the_whole_scope')if body=='committee_of_the_whole'else'official_council_header_and_dated_council_membership',
     'membership_evidence':'dated_db_council_membership','presence_events':record['independent_events'],'votes':votes,'choice_provenance':{f"person_{v['person_id']}":v['evidence']for v in votes},
     'rule_id':'explicit_unanimity'if'UNANIMOUS'in proposal['source_result']else policy['rule_id'],'basis':'explicit_unanimity_with_per_vote_roster'if'UNANIMOUS'in proposal['source_result']else'validated_dissent_recording_rule_with_per_vote_roster',
     'bylaw_url':policy['bylaw_url'],'bylaw_sha256':policy['bylaw_sha256'],'policy_checked_as_of':policy['validated_as_of'],'policy_status':policy['policy_status'],'method':'documentary_reconstruction_not_explicit_rollcall',
     'independent_review':{'file':str(reviewpath.relative_to(ROOT)),'sha256':reviewhash,'reviewer_sha256':review['reviewer_sha256']}})
    correction={**record['required_provenance'],'correction_kind':record['source_correction_kind'],'official_motion_text':record['source_motion_text'],'qualification_review':record['qualification_review'],
     'source_sha256':record['source_sha256'],'source_url':record['source_url'],'native_agenda_item':record['native_agenda_item'],'actors':record['actors'],'review_sha256':reviewhash}
    meta={**(row['meta']or{}),'source_motion_correction':correction,'individual_vote_coverage':'reconstructed_complete','ballot_reconstruction':proof}
    meta['vote_record']={**meta.get('vote_record',{}),'coverage':'reconstructed_complete'}
    changes.append({'motion_id':mid,'before_motion':row,'before_votes':existing[mid],'after_text':record['source_motion_text'],'after_meta':meta,
     'new_choices':[(mid,pid,vote)for pid,vote in sorted(choices.items())if pid not in{v['person_id']for v in existing[mid]}],'inserted_votes':[]})
   # A text correction must not leave an adoption derived solely from that old
   # wording. Flag full-history lifecycle review and refuse apply if affected.
   cur.execute('SELECT DISTINCT a.matter_id FROM agenda_items a JOIN motions m ON m.agenda_item_id=a.id WHERE m.id=ANY(%s) AND a.matter_id IS NOT NULL',(ids,));matterids=[r['matter_id']for r in cur.fetchall()]
   cur.execute('SELECT id,status,meta FROM matters WHERE id=ANY(%s)',(matterids,));matters=[serial(dict(r))for r in cur.fetchall()]
   stale=[r for r in matters if(r['meta']or{}).get('lifecycle_evidence',{}).get('motion_id')in ids]
   plan={'mode':'guarded_dry_run','created_at':datetime.now(timezone.utc).isoformat(),'review_sha256':reviewhash,'apply_script_sha256':scriptsha,'changes':changes,'affected_matters':matters,'lifecycle_review_required':stale,
    'summary':{'motions':len(changes),'new_vote_rows':sum(len(c['new_choices'])for c in changes),'existing_vote_rows_preserved':sum(len(c['before_votes'])for c in changes),'affected_matters':len(matters),'potential_stale_lifecycle':len(stale)}}
   planpath.write_text(json.dumps(plan,indent=2)+'\n');print(json.dumps(plan['summary']),flush=True)
  else:
   assert not receiptpath.exists(),'applied_receipt_exists'
   plan=json.loads(planpath.read_text());assert plan['review_sha256']==reviewhash and plan['apply_script_sha256']==scriptsha,'frozen_review_or_script_changed'
   assert not plan['lifecycle_review_required'],'source_correction_requires_matter_lifecycle_review_first'
   for change in plan['changes']:
    source_guard(next(r for r in selected if r['motion_id']==change['motion_id']))
    cur.execute('SELECT id,meeting_id,agenda_item_id,text_content,result,meta,updated_at FROM motions WHERE id=%s FOR UPDATE',(change['motion_id'],));assert serial(dict(cur.fetchone()))==change['before_motion'],'CAS_motion_changed'
    cur.execute('SELECT id,motion_id,person_id,vote,updated_at FROM votes WHERE motion_id=%s ORDER BY id FOR UPDATE',(change['motion_id'],));assert serial(list(cur.fetchall()))==change['before_votes'],'CAS_existing_votes_changed'
   insertions=[v for c in plan['changes']for v in c['new_choices']]
   inserted=execute_values(cur,'INSERT INTO votes(motion_id,person_id,vote) VALUES %s RETURNING id,motion_id,person_id,vote,updated_at',insertions,fetch=True)if insertions else[]
   assert len(inserted)==len(insertions)
   for change in plan['changes']:
    change['inserted_votes']=[serial(dict(v))for v in inserted if v['motion_id']==change['motion_id']]
    cur.execute('UPDATE motions SET text_content=%s,meta=%s WHERE id=%s RETURNING id,text_content,result,meta,updated_at',(change['after_text'],Json(change['after_meta']),change['motion_id']));change['after_motion']=serial(dict(cur.fetchone()))
   db.commit()
   receipt={**plan,'mode':'applied','applied_at':datetime.now(timezone.utc).isoformat(),'plan_sha256':hashlib.sha256(planpath.read_bytes()).hexdigest()}
   receiptpath.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt['summary']),flush=True)
