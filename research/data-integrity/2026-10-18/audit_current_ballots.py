"""Replay ALL decided motions and every stored complete ballot, read-only.

Uses production validator + original native sources, fresh canonical identities
and memberships. A prior proof may bind a uniquely identical full source block;
any canonical-text correction is reported separately, never silently written.
"""
import json,hashlib
from pathlib import Path
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor
from pipeline.ingestion import official_ballots as engine
from pipeline.ingestion.meeting_ballots import evaluate_ballot
from pipeline.ingestion.vote_evidence import normalize_text,named_votes
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
snapshot=json.loads((OUT/'ballot-source-current-snapshot.json').read_text());people=json.loads((OUT/'vote-people-current-snapshot.json').read_text());full=json.loads((OUT/'complete-ballots-current-snapshot.json').read_text());inventory=json.loads((OUT/'full-current-vote-inventory.json').read_text())
meetings={m['id']:{**m,'municipality_slug':'langford'} for m in snapshot['meetings']};complete={m['id']:m for m in full['motions']};votes=defaultdict(list)
for vote in inventory['votes']:votes[vote['motion_id']].append(vote)
policy={**json.loads((ROOT/'apps/pipeline/pipeline/ingestion/policies/langford-voting.json').read_text()),**json.loads((OUT/'policy-refresh-verification.json').read_text()),'municipality_slug':'langford'}
if (OUT/'committee-policy-refresh-verification.json').exists():policy['committee_policy']=json.loads((OUT/'committee-policy-refresh-verification.json').read_text())['committee_policy']
def inspect(motion,source,meeting):
 result=evaluate_ballot(motion,{'status':'available','source':source,'meeting':meeting,'people':people,'memberships':snapshot['memberships'],'policy':policy})
 result.pop('proof',None)  # Full native evidence is already in the candidate.
 return result
paths=[ROOT/'apps/pipeline/pipeline/ingestion'/file for file in ['official_ballots.py','ballot_reconstruction.py','vote_evidence.py','meeting_ballots.py','committee_ballots.py','policies/langford-voting.json']]
hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
selected=[m for m in snapshot['motions'] if m['result']];ids=sorted({m['meeting_id'] for m in selected})
with ThreadPoolExecutor(max_workers=4) as pool:sources=dict(zip(ids,pool.map(lambda mid:engine.load_official_minutes(meetings[mid],root=ROOT,people=people,cache_dir=Path('/private/tmp/langford-ballot-source-audit')),ids)))
results=[];new=[];replayed=[];explicit_conflicts=[];date_mismatches=[];date_evidence_changes=[]
name_ids={p['name']:p['id'] for p in people}
for row in selected:
 mid=row['id'];source=sources[row['meeting_id']];motion={**row,**complete.get(mid,{})};old=complete.get(mid);proof=(old or {}).get('meta',{}).get('ballot_reconstruction',{})
 result=inspect(motion,source,meetings[row['meeting_id']])
 if old and source.get('local_date'):
  if proof.get('source_date')!=source['local_date']:
   date_mismatches.append({'motion_id':mid,'prior_source_date':proof.get('source_date'),'current_native_header_date':source['local_date'],'prior_source_sha256':proof.get('source_sha256'),'current_source_sha256':source.get('source_sha256')})
  prior_evidence=proof.get('source_date_evidence');current_evidence=source.get('source_date_evidence')
  if prior_evidence!=current_evidence:
   prior_quote=(prior_evidence or {}).get('source_quote','')
   date_evidence_changes.append({'motion_id':mid,'classification':'missing_optional_native_header_evidence' if not prior_evidence else 'prior_date_quote_not_in_current_native_header' if prior_quote and normalize_text(prior_quote) not in normalize_text(source.get('source_header','')) else 'date_evidence_metadata_changed','prior_evidence':prior_evidence,'current_evidence':current_evidence,'current_source_date':source['local_date']})
 binding=None
 if old and not source.get('error') and proof.get('source_sha256')==source.get('source_sha256'):
  prior_block=normalize_text(proof.get('source_block',''))
  block_matches=[b for b in source['blocks'] if normalize_text(b['source_block'])==prior_block]
  binding_method='same_binary_hash_and_unique_entire_normalized_source_block'
  if not block_matches and prior_block:
   block_matches=[b for b in source['blocks'] if prior_block.startswith(normalize_text(b['source_block']))]
   binding_method='same_binary_hash_and_unique_full_current_block_prefix_of_preserved_block'
  if len(block_matches)==1:
   binding=block_matches[0]
   for declaration in named_votes(binding,[p['name'] for p in people]):
    pid=name_ids[declaration['person_name']];current=[v for v in votes[mid] if v['person_id']==pid]
    if current and current[0]['vote']!=declaration['vote']:
     explicit_conflicts.append({'motion_id':mid,'vote_id':current[0]['id'],'person_id':pid,'current_choice':current[0]['vote'],'official_choice':declaration['vote'],'source_quote':declaration['source_quote'],'source_file':source['source_file'],'source_sha256':source['source_sha256']})
   if result['status']=='source_motion_not_exact_or_ambiguous':
    result=inspect({**motion,'text_content':binding['motion_text']},source,meetings[row['meeting_id']])
    result['prior_proof_exact_block_binding']={'method':binding_method,'original_motion_text':motion['text_content'],'official_motion_text':binding['motion_text']}
 if old:
  actual={(v['person_id'],v['vote']) for v in votes[mid]}
  if result['status']=='reconstructable_candidate':
   expected={(v['person_id'],v['vote']) for v in result['votes']}
   status='verified_existing_complete' if actual==expected else 'existing_complete_choice_mismatch'
   if status=='verified_existing_complete' and normalize_text(result['source_motion_text'])!=normalize_text(motion['text_content']):status='verified_choices_canonical_body_correction_proposed'
   replayed.append({**result,'validation_status':status,'current_vote_ids':[v['id'] for v in votes[mid]],'current_choices':sorted(actual),'expected_choices':sorted(expected)})
  else:replayed.append({**result,'validation_status':'existing_complete_held_under_current_guard','current_vote_ids':[v['id'] for v in votes[mid]]})
 elif result['status']=='reconstructable_candidate':
  expected={v['person_id']:v['vote'] for v in result['votes']}
  if any(v['person_id'] not in expected or v['vote']!=expected[v['person_id']] for v in votes[mid]):result['status']='existing_partial_choice_conflict'
  else:
   result['new_choice_rows']=[v for v in result['votes'] if v['person_id'] not in {oldvote['person_id'] for oldvote in votes[mid]}]
   result['current_votes']=votes[mid];new.append(result)
 results.append(result)
for path in paths:
 if hashes[str(path.relative_to(ROOT))]!=hashlib.sha256(path.read_bytes()).hexdigest():raise RuntimeError('Production guard changed during replay; no new audit written')
summary={'database_writes':0,'decided_motions':len(selected),'complete_ballots_replayed':len(replayed),'complete_replay':dict(Counter(r['validation_status'] for r in replayed)),'explicit_named_choice_conflicts':len(explicit_conflicts),'existing_proof_source_date_mismatches':len(date_mismatches),'existing_date_evidence_changes':dict(Counter(r['classification'] for r in date_evidence_changes)),'new_complete_ballot_candidates':len(new),'new_choice_rows':sum(len(r['new_choice_rows']) for r in new),'whole_archive_statuses':dict(Counter(r['status'] for r in results)),'remaining_without_complete_statuses':dict(Counter(r['status'] for r in results if r['motion_id'] not in complete)),'code_sha256s':hashes,'current_motion_snapshot_sha256':hashlib.sha256((OUT/'ballot-source-current-snapshot.json').read_bytes()).hexdigest(),'current_vote_inventory_sha256':hashlib.sha256((OUT/'full-current-vote-inventory.json').read_bytes()).hexdigest()}
(OUT/'current-full-ballot-audit.json').write_text(json.dumps({'summary':summary,'motions':results,'existing_complete_replay':replayed,'explicit_choice_conflicts':explicit_conflicts,'existing_proof_source_date_mismatches':date_mismatches,'existing_date_evidence_changes':date_evidence_changes,'new_candidates':new},indent=2));print(json.dumps(summary,indent=2),flush=True)
