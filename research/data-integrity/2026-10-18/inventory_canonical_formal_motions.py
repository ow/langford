"""Canonical source universe independent of AI-created legacy motion records.

Read-only PDF/HTML inventory. Versioned identities bind meeting, original source
hash, native span/DOM node, agenda, actors and source order. No DB/AI calls.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from collections import Counter,defaultdict
import ast,hashlib,json,re,subprocess
from bs4 import BeautifulSoup
from pipeline.ingestion.official_ballots import html_minutes_text
from pipeline.ingestion.vote_evidence import normalize_text

ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent;CACHE=Path('/private/tmp/remaining-source-reconciliation');CACHE.mkdir(exist_ok=True)
snapshot=json.loads((OUT/'ballot-source-snapshot.json').read_text());meetings={m['id']:m for m in snapshot['meetings']}
OUTCOME=re.compile(r'(?im)^[ \t]*(?:Motion[ \t]+)?(NOT CARRIED|CARRIED(?:[ \t]+UNANIMOUSLY)?|DEFEATED|WITHDRAWN|TABLED)\b[^\n]*')
# Reuse only the read-only file/extraction function, not its legacy-motion census.
# Canonical inventory retains all formal body words after the seconder, including
# recitals; no first-THAT heuristic is allowed to truncate a WHEREAS clause.
loader=(OUT/'inventory_remaining_source_reconciliation.py').read_text()
loader=loader.replace("  beginning=re.search(r'\\bTHAT(?=\\b|Council\\b|Committee\\b)',body,re.I)\n  if beginning:body=body[beginning.start():]\n  else:continue", "  if len(body.strip())<10:continue")
module=ast.parse(loader);function=next(node for node in module.body if isinstance(node,ast.FunctionDef)and node.name=='source_for')
exec(compile(ast.Module(body=[function],type_ignores=[]),'<canonical native loader>','exec'),globals())
ids=sorted(meetings)
with ThreadPoolExecutor(max_workers=4)as pool:sources=dict(zip(ids,pool.map(source_for,ids)))
canonical=[];source_inventory=[]
for mid,source in sources.items():
 if source.get('error'):source_inventory.append({'meeting_id':mid,**source});continue
 source_inventory.append({'meeting_id':mid,**{k:v for k,v in source.items()if k!='blocks'},'formal_decisions':len(source['blocks'])})
 dom_nodes=[]
 if source['source_format']=='official_html_structural':
  dom_nodes=BeautifulSoup((ROOT/source['source_file']).read_text(),'html.parser').select('.AgendaItemMotion')
 for block in source['blocks']:
  anchor={'meeting_id':mid,'source_sha256':source['source_sha256'],'source_file':source['source_file'],'source_format':source['source_format'],'source_url':source['source_url'],
   'native_text_sha256':source['native_text_sha256'],'native_mover_offset':block['source_offset'],'source_order':block['source_order'],'agenda_item_number':block['item_order'],
   'agenda_item_title':block['item_title'],'mover':block['mover'],'seconder':block['seconder'],'source_motion_text':block['motion_text'],'source_result':block['result'],
   'source_block':block['source_block'],'outcome_quote':block['outcome_quote'],'before_outcome_vote_evidence':block['before_outcome_vote_evidence'],'after_outcome':block['after_outcome']}
  if dom_nodes:
   matches=[]
   for i,node in enumerate(dom_nodes):
    body='\n'.join(part.get_text(' ',strip=True)for part in node.select('.MotionText'))
    if normalize_text(body)==normalize_text(block['motion_text']):matches.append((i,node))
   if len(matches)==1:
    i,node=matches[0];anchor.update({'dom_motion_index':i,'dom_node_sha256':hashlib.sha256(str(node).encode()).hexdigest()})
   else:anchor['dom_mapping_status']='not_unique_or_export_wrapper_difference'
  key_data={k:anchor.get(k)for k in['meeting_id','source_sha256','native_mover_offset','source_order','dom_motion_index','agenda_item_number','mover','seconder']}
  anchor['canonical_source_motion_key']=hashlib.sha256(json.dumps(key_data,sort_keys=True).encode()).hexdigest()
  anchor['source_motion_text_sha256']=hashlib.sha256(anchor['source_motion_text'].encode()).hexdigest()
  legacy=[m for m in snapshot['motions']if m['meeting_id']==mid and normalize_text(m['text_content'])==normalize_text(anchor['source_motion_text'])]
  anchor['exact_legacy_motion_ids']=[m['id']for m in legacy]
  anchor['mapping_status']='one_exact_legacy_motion'if len(legacy)==1 else'multiple_exact_legacy_motions'if len(legacy)>1 else'no_exact_legacy_motion'
  canonical.append(anchor)
result={'mode':'read_only_canonical_official_formal_motion_universe','at':datetime.now(timezone.utc).isoformat(),
 'source_snapshot_sha256':hashlib.sha256((OUT/'ballot-source-snapshot.json').read_bytes()).hexdigest(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 'summary':{'meetings':len(meetings),'canonical_formal_decisions':len(canonical),'mapping_status':dict(Counter(c['mapping_status']for c in canonical)),
 'source_errors':dict(Counter(s['error']for s in source_inventory if s.get('error'))),'no_live_inserts_or_retirements':True},'sources':source_inventory,'canonical_motions':canonical}
(OUT/'canonical-official-motion-inventory.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result['summary'],indent=2),flush=True)
