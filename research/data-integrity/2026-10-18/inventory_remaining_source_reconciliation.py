"""Read-only full remaining-motion/source census; proposals are never writes.

Original PDF/official structural HTML, source order, agenda number and actors
are recorded. Exact matches and bounded token-supported corrections are
separated from unresolved mismatches; no fuzzy score proves identity.
"""
from pathlib import Path
import json,re,hashlib,subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import importlib.util

ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
snapshot=json.loads((OUT/'ballot-source-snapshot.json').read_text())
inventory=json.loads((OUT/'full-current-vote-inventory.json').read_text())
people=json.loads((OUT/'vote-people-snapshot.json').read_text())
meetings={m['id']:m for m in snapshot['meetings']}
voted={v['motion_id']for v in inventory['votes']}
remaining=[m for m in snapshot['motions']if m['result']and m['id']not in voted]
assert len(remaining)==inventory['totals']['result_without_individual_votes']
CACHE=Path('/private/tmp/remaining-source-reconciliation');CACHE.mkdir(exist_ok=True)
from pipeline.ingestion.official_ballots import html_minutes_text
from pipeline.ingestion.vote_evidence import normalize_text,critical_identity

OUTCOME=re.compile(r'(?im)^[ \t]*(?:Motion[ \t]+)?(NOT CARRIED|CARRIED(?:[ \t]+UNANIMOUSLY)?|DEFEATED|WITHDRAWN|TABLED)\b[^\n]*')

def source_for(mid):
 meeting=meetings[mid];folder=ROOT/meeting['archive_path']/'Minutes'
 pdf=list(folder.glob('*.pdf'));preferred=[p for p in pdf if 'signed'in p.name.lower()]or[p for p in pdf if p.name=='Minutes.pdf']or pdf
 if preferred:
  if len(preferred)!=1:return {'error':'ambiguous_native_pdf_inventory','files':[str(p.relative_to(ROOT))for p in preferred]}
  path=preferred[0];binary=path.read_bytes();digest=hashlib.sha256(binary).hexdigest();cache=CACHE/(digest+'.txt')
  try:
   if not cache.exists():subprocess.run(['pdftotext','-layout','-enc','UTF-8',str(path),str(cache)],check=True,timeout=60,capture_output=True)
   raw=cache.read_text();kind='original_pdf_layout'
  except Exception as error:return {'error':'native_pdf_extraction_failed','error_type':type(error).__name__}
 else:
  html=list(folder.glob('*.html'))
  if len(html)!=1:return {'error':'no_unique_original_pdf_or_html'}
  path=html[0];binary=path.read_bytes();digest=hashlib.sha256(binary).hexdigest()
  try:raw=html_minutes_text(path);kind='official_html_structural'
  except Exception as error:return {'error':'official_html_extraction_failed','error_type':type(error).__name__}
 text='\n'.join(line for line in raw.splitlines()if not re.match(r'^\s*Minutes of[^\n]*$',line,re.I)and not re.match(r'^\s*\d+\s*$',line)).replace('\f','\n')
 movers=list(re.finditer(r'(?im)^[ \t]*MOVED[ \t]+BY\s*[:;]?',text));blocks=[]
 for index,mover in enumerate(movers):
  end=movers[index+1].start()if index+1<len(movers)else len(text);block=text[mover.start():end];outcome=OUTCOME.search(block)
  if not outcome:continue
  before=block[:outcome.start()];seconder=re.search(r'(?im)^.*SECONDED[^\n]*\n',before)
  body=before[seconder.end():]if seconder else before
  beginning=re.search(r'\bTHAT(?=\b|Council\b|Committee\b)',body,re.I)
  if beginning:body=body[beginning.start():]
  else:continue
  # Standalone explicit vote/narrative lines are evidence outside the operative
  # body; retain them in the full immutable native block for later validation.
  suffix=re.search(r'(?im)^\s*(?:OPPOSED\s*:|(?:Mayor|Councillors?)\s+[^\n]*\b(?:opposed|gave a brief update)\b)',body)
  pre_vote=body[suffix.start():].strip()if suffix else ''
  if suffix:body=body[:suffix.start()]
  prefix=text[:mover.start()]
  headings=list(re.finditer(r'(?m)^[ \t]{0,10}(\d+(?:\.\d+)*)\.?\s+([A-Z][^\n]*)',prefix))
  number=headings[-1][1].strip('.')if headings else None;title=headings[-1][2].strip()if headings else None
  def actor(label):
   match=re.search(r'(?im)^\s*'+label+r'\s*[:;]?\s*([^\n]+)',block)
   return match[1].strip()if match else None
  blocks.append({'source_order':len(blocks),'source_offset':mover.start(),'motion_text':body.strip(),'result':outcome[1].upper(),'outcome_quote':outcome[0].strip(),
   'mover':actor(r'MOVED\s+BY'),'seconder':actor(r'SECONDED(?:\s+BY)?'),'item_order':number,'item_title':title,
   'before_outcome_vote_evidence':pre_vote,'after_outcome':block[outcome.end():].strip(),'source_block':block.strip()})
 urlpath=Path(str(path)+'.url');url=urlpath.read_text().strip()if urlpath.exists()else meeting.get('minutes_url')
 return {'source_file':str(path.relative_to(ROOT)),'source_url':url,'source_sha256':digest,'source_format':kind,'native_text_sha256':hashlib.sha256(raw.encode()).hexdigest(),'blocks':blocks}

ids=sorted({m['meeting_id']for m in remaining})
with ThreadPoolExecutor(max_workers=4)as workers:sources=dict(zip(ids,workers.map(source_for,ids)))
stop={'the','a','an','that','to','of','for','and','be','is','as','by','with','it','its','on','in','at','from','this','these','those','moved','seconded','motion','carried','therefore','resolved'}

def supported(old,new):
 # Source identity candidates only: later independent review must prove all
 # body/actions/negation/qualifiers and ballot eligibility before persistence.
 return critical_identity(old)[0]==critical_identity(new)[0]and(set(normalize_text(old).split())-stop)<=(set(normalize_text(new).split())-stop)

def actors_match(row,block):
 for field in ['mover','seconder']:
  expected=normalize_text(row.get(field)).split();actual=normalize_text(block.get(field)).split()
  if expected and(not actual or expected[-1]not in actual):return False
 return True

records=[]
for motion in remaining:
 source=sources[motion['meeting_id']];r={'motion_id':motion['id'],'meeting_id':motion['meeting_id'],'original_motion_text':motion['text_content'],'result':motion['result'],
  'stored_item_order':motion.get('item_order'),'stored_item_title':motion.get('item_title'),'stored_mover':motion.get('mover'),'stored_seconder':motion.get('seconder')}
 if source.get('error'):r.update({'status':source['error'],'source_error':source});records.append(r);continue
 r.update({k:source[k]for k in ['source_file','source_url','source_sha256','source_format','native_text_sha256']})
 exact=[b for b in source['blocks']if normalize_text(b['motion_text'])==normalize_text(motion['text_content'])]
 numbered=[b for b in source['blocks']if b['item_order']==str(motion.get('item_order')or'').strip('.')]
 actors=[b for b in numbered if actors_match(motion,b)]
 identity=[b for b in actors if supported(motion['text_content'],b['motion_text'])]
 if len(exact)==1:stage='unique_exact_native_formal_body';candidates=exact
 elif len(exact)>1:stage='duplicate_exact_native_formal_body';candidates=exact
 elif len(identity)==1:stage='unique_agenda_actor_token_supported_source_correction';candidates=identity
 elif len(identity)>1:stage='ambiguous_token_supported_anchors';candidates=identity
 elif not source['blocks']:stage='no_native_formal_decisions_extracted';candidates=[]
 elif not motion.get('item_order'):stage='missing_stored_agenda_number';candidates=[]
 elif not numbered:stage='no_formal_decision_at_stored_agenda_number';candidates=[]
 elif not actors:stage='agenda_actor_mismatch';candidates=numbered
 elif len(actors)==1:stage='single_agenda_actor_candidate_requires_substantive_reconciliation';candidates=actors
 else:stage='multiple_agenda_actor_candidates_require_source_order_and_identity';candidates=actors
 r.update({'status':stage,'candidates':candidates,'native_formal_decisions':len(source['blocks'])});records.append(r)
result={'mode':'read_only_full_remaining_source_reconciliation_census_no_model_calls_no_DB_writes','at':datetime.now(timezone.utc).isoformat(),
 'input_sha256':{f:hashlib.sha256((OUT/f).read_bytes()).hexdigest()for f in ['ballot-source-snapshot.json','full-current-vote-inventory.json']},'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 'summary':{'remaining_decided_motions_without_rows':len(records),'source_meetings':len(sources),'classification':dict(Counter(r['status']for r in records)),
 'proposals_are_not_ballot_certification':True},'records':records}
(OUT/'remaining-source-reconciliation-census.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result['summary'],indent=2),flush=True)
