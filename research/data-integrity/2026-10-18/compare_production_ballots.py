"""Read-only parity check against the frozen, independently reviewed ballot audit."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from pipeline.ingestion.official_ballots import load_official_minutes,inspect_motion

ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
snapshot=json.loads((OUT/'ballot-source-snapshot.json').read_text())
prior=json.loads((OUT/'full-ballot-audit.json').read_text())
people=json.loads((OUT/'vote-people-snapshot.json').read_text())
policy=json.loads((OUT/'ballot-recording-rule.json').read_text())
policy.update({'municipality_slug':'langford','policy_status':'verified_unchanged'})
meetings={row['id']:{**row,'municipality_slug':'langford'} for row in snapshot['meetings']}
motions={row['id']:row for row in snapshot['motions']}
ids=sorted({row['meeting_id'] for row in prior['motions']})
def load(mid):return load_official_minutes(meetings[mid],root=ROOT,people=people,cache_dir='/private/tmp/langford-ballot-source-audit')
with ThreadPoolExecutor(max_workers=4) as pool:sources=dict(zip(ids,pool.map(load,ids)))
differences=[];counts=Counter();accepted=[]
for old in prior['motions']:
    motion=motions[old['motion_id']]
    now=inspect_motion(motion,sources[motion['meeting_id']],meeting=meetings[motion['meeting_id']],people=people,memberships=snapshot['memberships'],policy=policy)
    counts[now['status']]+=1
    if now['status']!=old['status']:
        differences.append({'motion_id':motion['id'],'before':old['status'],'production':now['status']})
    elif now['status']=='reconstructable_candidate':
        if [(v['person_id'],v['vote']) for v in now['votes']]!=[(v['person_id'],v['vote']) for v in old['votes']]:
            raise RuntimeError(f"Ballot choices changed for {motion['id']}")
        accepted.append(motion['id'])
result={'scope':'frozen_audit_input_no_DB_writes','classification':dict(counts),'identical_accepted_ballots':len(accepted),'differences':differences}
(OUT/'production-ballot-parity.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
