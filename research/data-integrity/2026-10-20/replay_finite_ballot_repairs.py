"""Offline evaluator for the 496-case receipt-backed first repair batch.

Input receipts and cached public minutes stay private/local. No database client
is constructed; socket access is denied. Output contains full proof/metadata and
must be kept local. This evaluates evidence; it does not authorize data writes.
"""
from pathlib import Path
import sys,json,hashlib,collections,socket
import argparse
parser = argparse.ArgumentParser(description="Replay the finite ballot census without DB, network, model, or OCR calls")
parser.add_argument('--evidence-root', type=Path, required=True)
parser.add_argument('--sources', type=Path, required=True, help="Frozen cached source-context JSON")
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
ORIG=args.evidence_root.resolve();CODE=Path(__file__).resolve().parents[3];sys.path.insert(0,str(CODE/'apps/pipeline'))
from pipeline.ingestion.canonical_motions import loaded_ballot_guard_digest
from pipeline.ingestion.meeting_ballots import evaluate_ballot,merge_ballot_evidence
from pipeline.ingestion.source_claims import build_claim_inventory
D=lambda x:hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
def read(p):return json.loads((ORIG/p).read_text())
d=read('.private/research/four-restoration-executor-v3/typed-parity-baseline-v3.json')['rows'];motions={r['id']:r for r in d['motions']}
for s in [read('.private/research/restored-four-ballot-plan-v1/fresh-actual-restored-four-ballot-before-v1.json')['state'],read('.private/research/restored-four-ballot-executor-v1/restored-four-ballot-applied-v1.json')['after'],read('.private/research/raw-two-ballot-executor-v1/raw-two-ballot-applied-v1.json')['after']]:motions.update({r['id']:r for r in s['scoped_full_rows']['motions']})
assert sorted([{'id':r['id'],'sha256':D(r)}for r in motions.values()],key=lambda r:r['id'])==s['all_motion_fingerprints']; votes=s['all_full_vote_rows'];assert sorted([{'id':r['id'],'sha256':D(r)}for r in votes],key=lambda r:r['id'])==s['all_vote_fingerprints']
orgs={r['id']:r for r in s['roster_policy_context']['organizations']};people=s['roster_policy_context']['people'];pp={r['id']:r for r in people};members=[{**r,'name':pp[r['person_id']]['name'],'classification':orgs[r['organization_id']]['classification']}for r in s['roster_policy_context']['memberships']];meet={r['id']:r for r in s['all_meetings']}
done=lambda r:(r.get('meta')or{}).get('individual_vote_coverage')=='reconstructed_complete';complete=[r for r in motions.values()if done(r)];targets={r['id'] for r in motions.values() if r['result'] and not done(r) and meet[r['meeting_id']]['municipality_id']==1 and '2022-11-07'<=meet[r['meeting_id']]['meeting_date']<'2026-10-20'};selected=[r for r in motions.values()if r['id']in targets or done(r)];assert len(complete)==1348
policy=read('.private/research/transcription-adapter-parity-v1/policy.json');policy['committee_policy']=read('.private/research/roster-unknown/occurrence-and-clock-final-v2/final-complete-parity-and-current-guard-partition.json')['policy']['committee_policy']
sourcepath=args.sources.resolve();sources=json.loads(sourcepath.read_text())
assert len(targets)==496, 'Frozen baseline changed; do not broaden or silently rebase this batch'
# Disable network for the pure evaluation pass. No DB client is constructed.
socket.socket=lambda *a,**k:(_ for _ in()).throw(RuntimeError('network forbidden'))
results=[]
for mid in sorted({r['meeting_id']for r in selected}):
 m={**meet[mid],'classification':orgs[meet[mid]['organization_id']]['classification'],'municipality_slug':'langford'};source=sources[str(mid)];claims=build_claim_inventory([r for r in motions.values()if r['meeting_id']==mid],meeting_id=mid,expected_count=sum(r['meeting_id']==mid for r in motions.values()));context={'status':'available','meeting':m,'source':source,'people':people,'memberships':members,'policy':policy,'meeting_claim_inventory':claims}
 for row in [r for r in selected if r['meeting_id']==mid]:
  existing=[v for v in votes if v['motion_id']==row['id']];result=evaluate_ballot(row,context,existing);choices,meta=merge_ballot_evidence(row,[],context,{'motion':row,'votes':existing});results.append({'motion_id':row['id'],'meeting_id':mid,'previously_complete':done(row),'status':result['status'],'candidate':result,'merged_choices':choices,'merged_meta':meta,'existing_choices_sha256':D(existing),'persisted_proof':(row.get('meta')or{}).get('ballot_reconstruction')})
out={'guard_sha256':loaded_ballot_guard_digest(),'source_contexts_sha256':hashlib.sha256(sourcepath.read_bytes()).hexdigest(),'target_count':len(targets),'complete_count':len(complete),'complete_choice_rows':sum(v['motion_id']in {r['id']for r in complete}for v in votes),'target_partition':dict(collections.Counter(r['status']for r in results if not r['previously_complete'])),'complete_partition':dict(collections.Counter(r['status']for r in results if r['previously_complete'])),'results':results,'database_writes':0,'model_calls':0}
p=args.output;p.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k!='results'},indent=2))
