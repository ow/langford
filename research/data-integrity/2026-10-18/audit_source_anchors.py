"""Read-only reconciliation of abbreviated motions to uniquely scoped source anchors.

No model calls, writes or fuzzy auto-matches. Requires exact agenda item number,
compatible mover/seconder where supplied, protected quantity/action/negation
identity and every proposed substantive token supported by the verbatim quote.
"""
import json,re,hashlib
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import audit_full_ballots as audit
from pipeline.ingestion.vote_evidence import normalize_text,match_motion_record

OUT=Path(__file__).parent
old=json.loads((OUT/'full-ballot-audit.json').read_text())
held={m['motion_id'] for m in old['motions'] if m['status']=='source_motion_not_exact_or_ambiguous'}
rows=[m for m in audit.data['motions'] if m['id'] in held];ids=sorted({m['meeting_id'] for m in rows})
with ThreadPoolExecutor(max_workers=4) as pool:sources=dict(zip(ids,pool.map(audit.source_for,[audit.meetings[mid] for mid in ids])))
results=[]

def item_number(block,source):
 offset=source['text'].find(block['source_block'])
 if offset<0:return None
 # Top-level and decimal agenda headings, excluding deeply indented numbered
 # conditions in the previous motion. Ambiguous/missing headings stay held.
 headings=list(re.finditer(r'(?m)^[ \t]{0,10}(\d+(?:\.\d+)*)\.?\s+[A-Z][^\n]*',source['text'][:offset]))
 return headings[-1][1].strip('.') if headings else None


def actor_matches(block,field,actor):
 if not actor:return True
 pattern=r'MOVED\s+BY\s*:?\s*([^\n]+)' if field=='mover' else r'SECONDED\s*(?:BY)?\s*:?\s*([^\n]+)'
 found=re.search(pattern,block['source_block'],re.I)
 return bool(found and re.search(r'\b'+re.escape(normalize_text(actor).split()[-1])+r'\b',normalize_text(found[1])))

for motion in rows:
 source=sources[motion['meeting_id']]
 if source.get('error'):continue
 expected=str(motion.get('item_order') or '').strip().strip('.')
 candidates=[]
 for block in source['blocks']:
  if not expected or item_number(block,source)!=expected:continue
  if not actor_matches(block,'mover',motion.get('mover')) or not actor_matches(block,'seconder',motion.get('seconder')):continue
  anchor=match_motion_record({'motion_text':motion['text_content'],'motion_source_quote':block['motion_text']},block['source_block'])
  if anchor:candidates.append(block)
 if len(candidates)!=1:
  results.append({'motion_id':motion['id'],'meeting_id':motion['meeting_id'],'status':'held_no_unique_scoped_verbatim_anchor','eligible_alternatives':len(candidates)});continue
 block=candidates[0]
 scoped={**source,'index':{**source['index'],normalize_text(block['motion_text']):[block]}}
 inspected=audit.inspect_motion({**motion,'text_content':block['motion_text']},scoped)
 inspected['source_anchor_reconciliation']={'original_motion_text':motion['text_content'],'official_motion_text':block['motion_text'],'agenda_item_order':expected,'agenda_item_title':motion.get('item_title'),'mover':motion.get('mover'),'seconder':motion.get('seconder'),'method':'unique_same_agenda_number_actor_consistency_exact_critical_identity_supported_tokens','eligible_alternatives':1}
 results.append(inspected)
summary={'scope':len(rows),'statuses':dict(Counter(m['status'] for m in results)),'proposed_choices':sum(len(m.get('votes',[])) for m in results),'paid_model_calls':0,'database_writes':0,'base_plan_sha256':hashlib.sha256((OUT/'full-ballot-audit.json').read_bytes()).hexdigest()}
(OUT/'source-anchor-reconciliation.json').write_text(json.dumps({'summary':summary,'motions':results},indent=2));print(json.dumps(summary,indent=2))
