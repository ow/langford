"""Read-only counterfactual census, NOT an eligibility certificate or apply plan."""
import json,sys,hashlib
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent;sys.path.insert(0,str(ROOT/'apps/pipeline'))
from pipeline.ingestion.official_ballots import load_official_minutes,inspect_motion
from pipeline.ingestion.vote_evidence import normalize_text,named_votes
snapshot=json.loads((OUT/'ballot-source-current-snapshot.json').read_text());people=json.loads((OUT/'vote-people-current-snapshot.json').read_text());audit=json.loads((OUT/'current-full-ballot-audit.json').read_text());motions={r['id']:r for r in snapshot['motions']};meetings={r['id']:{**r,'municipality_slug':'langford'} for r in snapshot['meetings']}
policy={**json.loads((ROOT/'apps/pipeline/pipeline/ingestion/policies/langford-voting.json').read_text()),**json.loads((OUT/'policy-refresh-verification.json').read_text()),'municipality_slug':'langford'}
selected=[r for r in audit['motions'] if r['status']=='dated_council_membership_unavailable'];sources={};records=[]
for row in selected:
 meeting=meetings[row['meeting_id']];motion=motions[row['motion_id']]
 if meeting['id'] not in sources:sources[meeting['id']]=load_official_minutes(meeting,root=ROOT,people=people,cache_dir='/private/tmp/langford-ballot-source-audit')
 source=sources[meeting['id']];day=source['local_date'];blocks=source['index'].get(normalize_text(motion['text_content']),[]);assert len(blocks)==1;block=blocks[0]
 # Deliberate research-only upper-bound probe: treat every already resolved canonical
 # name as dated eligible, solely to reveal the next guard. This does NOT certify
 # native role labels, independent full identity, membership, or permission to write.
 probe=[{'person_id':p['id'],'name':p['name'],'role':'Councillor','classification':'Council','start_date':day,'end_date':day} for p in people]
 result=inspect_motion(motion,{k:v for k,v in source.items() if k not in ('presence_events','unknown_presence_events')},meeting=meeting,people=people,memberships=probe,policy=policy)
 explicit=named_votes(block,[p['name'] for p in people]);yes=sum(v['vote']=='Yes' for v in explicit);no=sum(v['vote']=='No' for v in explicit)
 category='explicit_unanimity' if 'UNANIMOUS' in block['result'] else 'complete_explicit_named' if result.get('inference_basis')=='every_present_voter_explicitly_named' else 'plain_outcome_older_rule_unproven'
 records.append({'motion_id':motion['id'],'meeting_id':meeting['id'],'source_date':day,'source_file':source['source_file'],'source_sha256':source['source_sha256'],'source_motion_text':block['motion_text'],'source_result':block['result'],'native_roster_quote':source['roster_quote'],'counterfactual_next_status':result['status'],'recording_evidence_category':category,'explicit_yes':yes,'explicit_no':no,'potential_unique_passed_majority_constraint':bool(no and not yes and 'CARRIED'==block['result'] and len(source['present'])-no==len(source['present'])//2+1)})
out={'mode':'read_only_counterfactual_upper_bound_no_eligibility_or_write_authorization','summary':{'motions':len(records),'meetings':len(sources),'next_guard_statuses':dict(Counter(r['counterfactual_next_status'] for r in records)),'recording_evidence_categories':dict(Counter(r['recording_evidence_category'] for r in records)),'potential_unique_passed_majority_constraints':sum(r['potential_unique_passed_majority_constraint'] for r in records),'database_writes':0},'limitations':['No term intervals created or proposed.','Research-only all-canonical-name eligibility probe cannot establish public office.','Every future per-meeting office observation needs exhaustive native role labels plus independent canonical identity proof.','Plain historical CARRIED remains held without primary819 recording-completeness evidence.'],'records':records}
f=OUT/'historical-office-observation-census.json';f.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out['summary'],indent=2));print(hashlib.sha256(f.read_bytes()).hexdigest())
