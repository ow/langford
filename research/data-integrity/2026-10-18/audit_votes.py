"""Read-only audit and source-backed repair plan. Never applies database changes.

Run from repo root with PYTHONPATH=apps/pipeline apps/pipeline/.venv/bin/python
research/data-integrity/2026-10-18/audit_votes.py [--refresh]
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from pipeline.ingestion.vote_evidence import match_minutes_motion

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).parent

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh',action='store_true',help='Read live DB; no writes')
    args=parser.parse_args()
    snapshot=OUT/'motions-audit.json'
    if args.refresh:
        from pipeline import config
        from supabase import create_client
        db=create_client(config.SUPABASE_URL,config.SUPABASE_SECRET_KEY or config.SUPABASE_KEY)
        rows=[]
        for start in range(0,100000,1000):
            page=db.table('motions').select('id,meeting_id,agenda_item_id,text_content,result,disposition,yes_votes,no_votes,meta,votes(person_id,vote),meetings(meeting_date,title,municipality_id)').order('id').range(start,start+999).execute().data
            rows+=page
            if len(page)<1000:break
        snapshot.write_text(json.dumps(rows,indent=2))
        people=db.table('people').select('id,name').order('id').range(0,9999).execute().data
        (OUT/'vote-people-snapshot.json').write_text(json.dumps(people,indent=2))
    rows=json.loads(snapshot.read_text())
    files=list((ROOT/'archive/langford').glob('**/minutes.md'))
    by_date={}
    for file in files:by_date.setdefault(file.parent.name[:10],[]).append(file)
    proposals=[];unknown=[];ballots=[]
    for motion in rows:
        votes=motion['votes'];c=Counter(v['vote'] for v in votes)
        if votes:
            ballots.append({'motion_id':motion['id'],'meeting_id':motion['meeting_id'],'result':motion['result'],'recorded_choices':dict(c),'classification':'partial_or_unverified','contradicts_majority_display':str(motion['result']).startswith('CARR') and c['No']>c['Yes']})
        if motion['result']:continue
        matches=[]
        for file in by_date.get(motion['meetings']['meeting_date'][:10],[]):
            source=match_minutes_motion(motion['text_content'],file.read_text())
            if source:matches.append((source,file))
        if len(matches)==1:
            source,file=matches[0]
            proposals.append({'motion_id':motion['id'],'meeting_id':motion['meeting_id'],'previous_result':None,'proposed_result':source['result'],'match_score':source['match_score'],'source_file':str(file.relative_to(ROOT)),'source_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'motion_text':motion['text_content'],'source_motion_text':source['motion_text'],'outcome_quote':source['outcome_quote'],'source_block':source['source_block']})
        else:
            text=motion['text_content'].casefold()
            category='unresolved'
            if any(x in text for x in ('called the meeting','call to order','public hearing opened','public hearing closed','public hearing for','hearing opened','hearing was opened','no motion','no council motion','adjourned the meeting','meeting adjourned','meeting was adjourned')):category='likely_narration_not_a_motion'
            elif any(x in text for x in ('notice of motion','whereas ')):category='possible_notice_requires_source_check'
            elif 'adjourn' in text:category='adjournment_no_stated_result'
            unknown.append({'motion_id':motion['id'],'meeting_id':motion['meeting_id'],'meeting_date':motion['meetings']['meeting_date'],'text':motion['text_content'],'classification':category,'matching_sources':len(matches)})
    totals={'motions':len(rows),'with_result':sum(bool(m['result']) for m in rows),'result_without_individual_votes':sum(bool(m['result']) and not m['votes'] for m in rows),'with_individual_votes':len(ballots),'individual_vote_rows':sum(len(m['votes']) for m in rows),'carried_with_only_or_more_opposition':sum(b['contradicts_majority_display'] for b in ballots),'missing_result':len(proposals)+len(unknown),'source_backed_outcome_candidates':len(proposals),'held_missing_result':len(unknown),'held_categories':dict(Counter(m['classification'] for m in unknown))}
    plan={'summary':totals,'safety':'Dry-run only. No inferred Yes votes, no attendance ballots, no deletions. Results are candidate recovery with source hashes; recheck old value/hash before apply. All existing individual ballots are partial/unverified unless separately proven complete.','outcome_candidates':proposals,'held_missing_result':unknown,'existing_ballots':ballots}
    (OUT/'vote-repair-plan.json').write_text(json.dumps(plan,indent=2))
    print(json.dumps(totals,indent=2))

if __name__=='__main__':main()
