"""Read-only shared-original-source CAC candidate census; no database writes."""
from pathlib import Path
from collections import Counter,defaultdict
import json,hashlib
from pipeline.ingestion.official_ballots import load_official_minutes
from pipeline.ingestion.committee_ballots import inspect_committee_motion
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
snapshot=json.loads((OUT/'ballot-source-current-snapshot.json').read_text());people=json.loads((OUT/'vote-people-current-snapshot.json').read_text());people=people.get('people',people)if isinstance(people,dict)else people
votes=json.loads((OUT/'full-current-vote-inventory.json').read_text())['votes'];existing=defaultdict(list)
for v in votes:existing[v['motion_id']].append(v)
meetings={m['id']:{**m,'municipality_slug':'langford'}for m in snapshot['meetings']if m['type']=='Advisory Committee'}
policy={**json.loads((ROOT/'apps/pipeline/pipeline/ingestion/policies/langford-voting.json').read_text()),**json.loads((OUT/'policy-refresh-verification.json').read_text()),'municipality_slug':'langford'}
policy.update(json.loads((OUT/'committee-policy-refresh-verification.json').read_text()))
sources={mid:load_official_minutes(m,root=ROOT,people=people,cache_dir='/private/tmp/committee-source-audit')for mid,m in meetings.items()};records=[]
for motion in snapshot['motions']:
 if motion['meeting_id']not in meetings:continue
 result=inspect_committee_motion(motion,sources[motion['meeting_id']],meeting=meetings[motion['meeting_id']],people=people,memberships=snapshot['memberships'],policy=policy)
 result['current_choices']=existing[motion['id']]
 if result['status']=='reconstructable_candidate':
  choices={v['person_id']:v['vote']for v in result['votes']}
  if any(choices.get(v['person_id'])!=v['vote']for v in existing[motion['id']]):result['status']='existing_choice_conflicts_with_reconstruction'
  else:result['new_choices']=[v for v in result['votes']if v['person_id']not in{v['person_id']for v in existing[motion['id']]}]
 records.append(result)
files=['apps/pipeline/pipeline/ingestion/committee_ballots.py','apps/pipeline/pipeline/ingestion/official_ballots.py','apps/pipeline/pipeline/ingestion/ballot_reconstruction.py','apps/pipeline/pipeline/ingestion/vote_evidence.py']
summary={'meetings':len(meetings),'motions':len(records),'statuses':dict(Counter(r['status']for r in records)),'candidate_ballots':sum(r['status']=='reconstructable_candidate'for r in records),'new_choices':sum(len(r.get('new_choices',[]))for r in records if r['status']=='reconstructable_candidate'),'database_writes':0}
result={'mode':'read_only_CAC_candidates_require_independent_native_review_before_CAS_apply','summary':summary,'inputs_sha256':{n:hashlib.sha256((OUT/n).read_bytes()).hexdigest()for n in ['ballot-source-current-snapshot.json','vote-people-current-snapshot.json','full-current-vote-inventory.json','committee-policy-refresh-verification.json']},'code_sha256s':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest()for n in files},'records':records}
(OUT/'committee-ballot-candidate-plan.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(summary))
