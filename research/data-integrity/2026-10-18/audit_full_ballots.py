"""Read-only ballot audit using the SAME validator as regular ingestion.

The original independently reviewed implementation is immutable historical
artifact audit_full_ballots_frozen_20261018.py. No model calls or DB writes.
Only independently certified candidates can enter the new production proposal.
"""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib,json
from pipeline.ingestion import official_ballots
from pipeline.ingestion.vote_evidence import normalize_text
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent;CACHE=Path('/private/tmp/langford-ballot-source-audit')
data=json.loads((OUT/'ballot-source-snapshot.json').read_text());people=json.loads((OUT/'vote-people-snapshot.json').read_text())
meetings={m['id']:{**m,'municipality_slug':'langford'} for m in data['meetings']}
policy={**json.loads((ROOT/'apps/pipeline/pipeline/ingestion/policies/langford-voting.json').read_text()),**json.loads((OUT/'policy-refresh-verification.json').read_text()),'municipality_slug':'langford'}

def source_for(meeting):
 return official_ballots.load_official_minutes(meeting,root=ROOT,people=people,cache_dir=CACHE)

def inspect_motion(motion,source):
 return official_ballots.inspect_motion(motion,source,meeting=meetings[motion['meeting_id']],people=people,memberships=data['memberships'],policy=policy)

def main():
 review_path=OUT/'remaining-ballot-independent-review.json';review_bytes=review_path.read_bytes();review=json.loads(review_bytes)
 original_bytes=(OUT/'full-ballot-audit.json').read_bytes()
 if hashlib.sha256(original_bytes).hexdigest()!=review['candidate_plan_sha256']:raise RuntimeError('Original reviewed plan changed')
 reviewed={r['motion_id']:r for r in review['records'] if r['status']=='reviewed'}
 paths={'parser_sha256':ROOT/'apps/pipeline/pipeline/ingestion/ballot_reconstruction.py','motion_gate_sha256':ROOT/'apps/pipeline/pipeline/ingestion/vote_evidence.py','official_validator_sha256':ROOT/'apps/pipeline/pipeline/ingestion/official_ballots.py','policy_file_sha256':ROOT/'apps/pipeline/pipeline/ingestion/policies/langford-voting.json','audit_script_sha256':Path(__file__)}
 hashes={key:hashlib.sha256(path.read_bytes()).hexdigest() for key,path in paths.items()}
 selected=[m for m in data['motions'] if m['result']];ids=sorted({m['meeting_id'] for m in selected})
 with ThreadPoolExecutor(max_workers=4) as pool:sources=dict(zip(ids,pool.map(source_for,[meetings[mid] for mid in ids])))
 results=[]
 for motion in selected:
  result=inspect_motion(motion,sources[motion['meeting_id']]);mid=motion['id']
  if result['status']=='reconstructable_candidate':
   independent=reviewed.get(mid)
   if not independent:result={**result,'status':'not_in_independently_certified_remaining_scope'}
   elif result['source_sha256']!=independent['source_sha256'] or normalize_text(result['source_motion_text'])!=normalize_text(independent['source_motion_text']) or {(v['person_id'],v['vote']) for v in result['votes']}!={(v['person_id'],v['vote']) for v in independent['choices']}:
    result={**result,'status':'shared_validator_disagrees_with_independent_review'}
   else:result['independent_review']={'review_sha256':hashlib.sha256(review_bytes).hexdigest(),'source_body':independent['source_body'],'scope_basis':independent['scope_basis'],'checks':independent['checks']}
  results.append(result)
 for key,path in paths.items():
  if hashlib.sha256(path.read_bytes()).hexdigest()!=hashes[key]:raise RuntimeError('Shared validator changed during audit; no new plan written')
 summary={**hashes,'proposal_status':'new_shared_validator_and_independent_review_intersection','independent_review_sha256':hashlib.sha256(review_bytes).hexdigest(),'original_reviewed_plan_sha256':hashlib.sha256(original_bytes).hexdigest(),'resulted_motions':len(results),'classification':dict(Counter(r['status'] for r in results)),'proposed_vote_rows':sum(len(r['votes']) for r in results if r['status']=='reconstructable_candidate'),'independently_reviewed_ids':len(reviewed)}
 (OUT/'full-ballot-reviewed-plan.json').write_text(json.dumps({'summary':summary,'motions':results},indent=2));print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':main()
