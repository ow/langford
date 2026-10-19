"""Read-only failure-stage/token census; no model or database calls."""
import json,runpy,hashlib
from collections import Counter
from pathlib import Path
from pipeline.ingestion.vote_evidence import critical_identity,normalize_text
folder=Path(__file__).parent
ctx=runpy.run_path(str(folder/'audit_source_anchors.py'))
counts=Counter();examples={};staged=[]
for m in ctx['rows']:
 s=ctx['sources'][m['meeting_id']]
 if s.get('error'):counts['source_error']+=1;continue
 expected=str(m.get('item_order') or '').strip().strip('.')
 numbered=[b for b in s['blocks'] if expected and ctx['item_number'](b,s)==expected]
 actors=[b for b in numbered if ctx['actor_matches'](b,'mover',m.get('mover')) and ctx['actor_matches'](b,'seconder',m.get('seconder'))]
 identity=[b for b in actors if critical_identity(m['text_content'])==critical_identity(b['motion_text'])]
 if not expected:stage='missing_agenda_number'
 elif not numbered:stage='no_source_block_at_agenda_number'
 elif not actors:stage='actor_mismatch_or_missing_source_actor'
 elif not identity:stage='critical_quantity_action_or_negation_mismatch'
 elif len(identity)>1:stage='multiple_identity_compatible_blocks'
 else:stage='single_identity_compatible_block'
 counts[stage]+=1
 row={'motion_id':m['id'],'meeting_id':m['meeting_id'],'item_number':expected,'stored_text':m['text_content'],'source_alternatives':[b['motion_text'] for b in (identity or actors or numbered)],'stage':stage}
 examples.setdefault(stage,[])
 if len(examples[stage])<5:examples[stage].append(row)
 if stage=='single_identity_compatible_block':staged.append(row)
result={'base_plan_sha256':hashlib.sha256((folder/'full-ballot-audit.json').read_bytes()).hexdigest(),'statuses':dict(counts),'examples':examples,'bounded_semantic_comparison':{'candidates':len(staged),'characters':sum(len(r['stored_text'])+sum(map(len,r['source_alternatives'])) for r in staged),'approx_input_tokens_at_four_characters_per_token':sum(len(r['stored_text'])+sum(map(len,r['source_alternatives'])) for r in staged)//4,'paid_model_calls':0,'database_writes':0},'staged':staged}
(folder/'source-anchor-diagnostics.json').write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k not in ('examples','staged')},indent=2))
