"""Source/ballot checks for semantic proposals only; no writes or model calls."""
import json,hashlib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import audit_full_ballots as a
from pipeline.ingestion.vote_evidence import critical_identity
OUT=Path(__file__).parent
plan=json.loads((OUT/'semantic-anchor-reconciliation.json').read_text());rows=[r for r in plan['records'] if r['status']=='two_pass_equivalent_proposal']
ids=sorted({r['proposal']['meeting_id'] for r in rows})
with ThreadPoolExecutor(max_workers=4) as pool:sources=dict(zip(ids,pool.map(a.source_for,[a.meetings[mid] for mid in ids])))
original={m['id']:m for m in a.data['motions']};results=[]
for row in rows:
 proposal=row['proposal'];motion=original[proposal['motion_id']];source=sources[motion['meeting_id']]
 if source.get('error'):results.append({'motion_id':motion['id'],'status':source['error']});continue
 source_hash=row['passes']['1']['source_sha256']
 blocks=[b for b in source['blocks'] if hashlib.sha256(b['motion_text'].encode()).hexdigest()==source_hash]
 if len(blocks)!=1:results.append({'motion_id':motion['id'],'status':'semantic_anchor_not_unique_in_current_official_source'});continue
 block=blocks[0]
 if critical_identity(motion['text_content'])!=critical_identity(block['motion_text']):raise RuntimeError('Protected identity changed')
 inspected=a.inspect_motion({**motion,'text_content':block['motion_text']},source)
 inspected['semantic_anchor_proposal']={'original_motion_text':motion['text_content'],'official_motion_text':block['motion_text'],'source_motion_sha256':source_hash,'two_pass_results':row['passes'],'source_item_number':proposal['item_number'],'source_mover':motion.get('mover'),'source_seconder':motion.get('seconder'),'proposal_only_requires_independent_source_anchor_review':True}
 results.append(inspected)
report={'database_writes':0,'additional_model_calls':0,'paid_text_cost_usd':plan['budget']['actual_usd'],'summary':dict(Counter(r['status'] for r in results)),'proposed_choices':sum(len(r.get('votes',[])) for r in results if r['status']=='reconstructable_candidate'),'motions':results}
(OUT/'semantic-ballot-proposals.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='motions'},indent=2),flush=True)
