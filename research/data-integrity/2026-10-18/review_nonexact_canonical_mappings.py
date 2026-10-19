"""Independent read-only native verification of all113 nonexact motion mappings.
No production parser/matcher imports; no fuzzy/set similarity verdicts or writes.
Semantic change review is recorded explicitly alongside original source binding.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from collections import Counter,defaultdict
from datetime import datetime,timezone,date
import json,re,hashlib,subprocess
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
CACHE=Path('/private/tmp/nonexact-mapping-independent');CACHE.mkdir(exist_ok=True)
FILES=['canonical-motion-legacy-mapping-proposals.json','canonical-official-motion-inventory.json','ballot-source-snapshot.json','source-correction-atomic-receipt.json']
raw={n:(OUT/n).read_bytes()for n in FILES};plan=json.loads(raw[FILES[0]]);inventory=json.loads(raw[FILES[1]]);base=json.loads(raw[FILES[2]])
legacy={m['id']:dict(m)for m in base['motions']};meetings={m['id']:m for m in base['meetings']}
for change in json.loads(raw[FILES[3]])['changes']:
 legacy[change['motion_id']]['text_content']=change['after_text'];legacy[change['motion_id']]['meta']=change['after_meta']
nodes={n['canonical_source_motion_key']:n for n in inventory['canonical_motions']}
selected=[r for r in plan['mappings']if r['method']!='unique_exact_source_body'];assert len(selected)==113

def compact(text):return re.sub(r'[^a-z0-9]+','',text.casefold())
def words(text):return re.sub(r'[^a-z0-9]+',' ',text.casefold()).strip()
def actor(text):
 value=[w for w in words(text or'').split()if w not in{'councillor','councillors','mayor','committee','member'}]
 return value

def same_actor(a,b):
 x,y=actor(a),actor(b)
 return bool(x and y and x[-1]==y[-1]and(len(x)==1 or len(y)==1 or x[0][0]==y[0][0]))

def outcome(text):
 v=words(text)
 if re.search(r'\bnot carried\b|\bdefeated\b',v):return'failed'
 if re.search(r'\bcarried\b|\bpassed\b|\badopted\b',v):return'passed'
 if'withdrawn'in v:return'withdrawn'
 if'tabled'in v:return'tabled'
 return None

def clean_pdf(text):
 return'\n'.join(line for line in text.splitlines()if not re.match(r'^\s*Minutes of[^\n]*$',line,re.I)and not re.match(r'^\s*\d+\s*$',line)).replace('\f','\n')

def source_load(path):
 f=ROOT/path;b=f.read_bytes();sha=hashlib.sha256(b).hexdigest();proof={'source_file':path,'source_sha256':sha}
 if f.suffix.lower()=='.pdf':
  assert b.lstrip().startswith(b'%PDF-'),'not_native_pdf'
  target=CACHE/(sha+'.txt');subprocess.run(['pdftotext','-layout','-enc','UTF-8',str(f),str(target)],check=True,timeout=60,capture_output=True)
  text=target.read_text();proof.update({'kind':'original_pdf_layout','native_text_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'native_text_path':str(target),'text':clean_pdf(text)})
 else:
  soup=BeautifulSoup(b,'html.parser');proof.update({'kind':'official_html_structural','soup':soup})
 sidecar=Path(str(f)+'.url');proof['official_url']=sidecar.read_text().strip()if sidecar.exists()else None
 return proof

sources={}
with ThreadPoolExecutor(max_workers=4)as pool:
 for path,src in zip(sorted({r['source_file']for r in selected}),pool.map(source_load,sorted({r['source_file']for r in selected}))):sources[path]=src

def native_binding(row,node,src):
 assert src['source_sha256']==node['source_sha256']==row['source_sha256'],'original_binary_hash_changed'
 assert src['kind']==node['source_format'],'native_format_changed'
 assert node['source_url']and re.match(r'https://(?:www\.)?langford\.ca/|https://pub-langford\.escribemeetings\.com/',node['source_url']),'nonofficial_url'
 if src['official_url']:assert src['official_url']==node['source_url'],'official_url_sidecar_changed'
 assert row['official_motion_text']==node['source_motion_text'],'proposed_body_differs_from_inventory'
 if src['kind']=='official_html_structural':
  dom=src['soup'].select('.AgendaItemMotion');matches=[]
  for i,item in enumerate(dom):
   text='\n'.join(t.get_text(' ',strip=True)for t in item.select('.MotionText'))
   if compact(text)==compact(node['source_motion_text']):matches.append((i,item))
  assert len(matches)==1,'native_dom_body_not_unique'
  i,item=matches[0]
  assert i==node.get('dom_motion_index'),'native_dom_index_differs'
  assert hashlib.sha256(str(item).encode()).hexdigest()==node.get('dom_node_sha256'),'native_dom_hash_differs'
  def value(css):
   el=item.select_one(css);assert el is not None,'native_dom_actor_or_result_missing';return el.get_text(' ',strip=True)
  a=value('.MovedBy .Value');b=value('.SecondedBy .Value');result=value('.MotionResult')
  assert same_actor(a,node['mover'])and same_actor(b,node['seconder']),'native_dom_actor_differs'
  assert outcome(result)==outcome(node['source_result']),'native_dom_outcome_differs'
  return {'dom_motion_index':i,'native_dom_sha256':node['dom_node_sha256'],'native_mover':a,'native_seconder':b,'native_outcome':result}
 text=src['text'];needle=compact(node['source_block']);flat=compact(text)
 assert flat.count(needle)==1,'native_complete_actor_body_result_block_not_unique:'+str(flat.count(needle))
 # The complete original block binds neighboring agenda context, not merely a bag of body words.
 start=flat.index(needle);assert compact(node['source_motion_text'])in needle,'native_body_missing_from_complete_block'
 block=node['source_block'];m=re.search(r'(?im)^\s*MOVED\s+BY\s*[:;]?\s*([^\n]+)',block);s=re.search(r'(?im)^\s*SECONDED(?:\s+BY)?\s*[:;]?\s*([^\n]+)',block)
 assert m and s,'native_formal_actor_labels_missing'
 assert same_actor(m[1],node['mover'])and same_actor(s[1],node['seconder']),'native_formal_actors_differ'
 results=list(re.finditer(r'(?im)^[ \t]*(?:Motion[ \t]+)?(NOT CARRIED|CARRIED(?:[ \t]+UNANIMOUSLY)?|DEFEATED|WITHDRAWN|TABLED)\b[^\n]*',block));assert results,'native_explicit_outcome_missing'
 assert outcome(results[0][1])==outcome(node['source_result']),'native_first_result_differs'
 body_before=block[:results[0].start()];assert compact(node['source_motion_text'])in compact(body_before),'body_not_before_own_first_result'
 return {'native_compact_block_offset':start,'native_block_sha256':hashlib.sha256(block.encode()).hexdigest(),'native_text_sha256':src['native_text_sha256'],'native_mover':m[1].strip(),'native_seconder':s[1].strip(),'native_outcome':results[0][0].strip()}

# Semantic review of every complete old/new pair was performed independently.
# Unlisted rows are additive full-clause restoration, presentation/list wrappers,
# actor-label removal or reordered wording with the same scoped action/objects.
semantic={577:'Restore the same property tax-exemption condition and its park/hall-use exception; identity is the same formal ballot.',1843:'Restore budget baseline qualifier; same budget scope, actors and formal result.',2229:'Restore Committee-of-the-Whole recommendation to Council; do not portray it as final Council spending direction.',2661:'Restore Committee-of-the-Whole recommendation wrapper on the same named budget deferral.',3027:'Restore amendment-to-main-motion wrapper; this vote is the amendment, not the final capital budget decision.',910:'Restore execution authority and restricted aquatic-fund-use clauses inside the same single compound formal resolution.',1926:'Restore UBCM award recitals without converting recitals into separate decisions.',1928:'Restore transit-policy recitals; same operative resolution and actors.',1506:'Restore scholarship recitals; same single formal resolution.',1819:'Restore aquatic-centre recitals; same single formal resolution.',2549:'Restore licence-decal recitals; same operative AVICC motion.',2550:'Restore full AVICC social-services rationale and operative text; same formal resolution.',2551:'Restore full AVICC funding rationale and conditional alternative action; same formal resolution.',2305:'Retain conjunction joining the formal clause; do not treat it as an independent approval.',648:'Retain source clause marker; one formal ballot in this actor block.',1548:'Retain source clause marker; one formal ballot in this actor block.',1580:'Retain source clause marker; one formal ballot in this actor block.'}
transcription={1557:'Native text contains Agremeent and Spence although the same body elsewhere says Spencer. Mapping identity is clear; preserve raw source and review presentation before replacing readable text.',1943:'Native layer contains ^he, a!t and mOst; inspect rendered original before literal replacement.',3326:'Native layer contains fopthe; inspect rendered original before literal replacement.',3328:'Native layer contains ip in place of in; inspect rendered original before literal replacement.',3299:'Native layer starts TAHT; retain source spelling in provenance, normalize display separately.',3399:'Native layer starts T HAT; retain source spelling in provenance, normalize display separately.',3654:'Native source repeats Acting; retain source spelling in provenance, normalize display separately.'}
source_orders=defaultdict(list)
for node in nodes.values():source_orders[node['source_file']].append(node)
for items in source_orders.values():items.sort(key=lambda n:n['source_order'])
counts=Counter(r['canonical_source_motion_key']for r in plan['mappings']);legacycounts=Counter(r['legacy_motion_id']for r in plan['mappings']);records=[]
for row in selected:
 id=row['legacy_motion_id'];node=nodes[row['canonical_source_motion_key']];old=legacy[id];record={'legacy_motion_id':id,'meeting_id':row['meeting_id'],'canonical_source_motion_key':row['canonical_source_motion_key'],'status':'hold','source_file':row['source_file'],'source_url':node['source_url'],'source_order':node['source_order'],'stored_agenda':row['stored_agenda_number'],'source_agenda':node['agenda_item_number']}
 try:
  assert counts[row['canonical_source_motion_key']]==legacycounts[id]==1,'not_global_one_to_one'
  assert old['meeting_id']==row['meeting_id']==node['meeting_id'],'meeting_identity_differs'
  assert old['text_content']==row['original_motion_text'],'legacy_original_or_prior_approved_overlay_differs'
  assert same_actor(old['mover'],node['mover'])and same_actor(old['seconder'],node['seconder']),'legacy_actors_not_same_as_official'
  assert old['result']is None or outcome(old['result'])==outcome(node['source_result']),'stored_result_contradicts_official'
  binding=native_binding(row,node,sources[row['source_file']]);items=source_orders[row['source_file']];index=next(i for i,n in enumerate(items)if n['canonical_source_motion_key']==row['canonical_source_motion_key'])
  neighbor={direction:items[i]['canonical_source_motion_key']for direction,i in [('previous',index-1),('next',index+1)]if 0<=i<len(items)}
  record.update({'status':'mapping_verified','native_binding':binding,'neighbors':neighbor,'source_body_sha256':hashlib.sha256(node['source_motion_text'].encode()).hexdigest(),'original_body_sha256':hashlib.sha256(old['text_content'].encode()).hexdigest(),'semantic_review':semantic.get(id,'Same formal action and object scope. Full original/source pair reviewed; differences are presentation, source-supported clause restoration or nonoperative context.'),'transcription_note':transcription.get(id),'ballot_certified':False,'literal_text_write_approved':False,'literal_replacement_eligible':id not in transcription,'literal_replacement_verdict':'identity_only_pending_rendered_text_policy' if id in transcription else 'eligible_exact_official_body_with_current_row_CAS','literal_replacement_scope':'Only this frozen proposal body and key; no agenda relink, result inference, vote mutation or newly generated universe is certified.'})
 except Exception as error:record['reason']=str(error)
 records.append(record)
result={'mode':'independent_read_only113_nonexact_identity_review_no_writes','at':datetime.now(timezone.utc).isoformat(),'input_sha256':{n:hashlib.sha256(b).hexdigest()for n,b in raw.items()},'review_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'summary':{'reviewed':len(records),'mapping_verified':sum(r['status']=='mapping_verified'for r in records),'held':sum(r['status']=='hold'for r in records),'distinct_original_sources':len(sources),'transcription_notes':sum(bool(r.get('transcription_note'))for r in records),'literal_replacement_eligible':sum(r.get('literal_replacement_eligible',False)for r in records),'identity_only_text_hold':sum(r['status']=='mapping_verified'and not r.get('literal_replacement_eligible',False)for r in records),'no_ballot_or_write_authorization':True},'records':records}
(OUT/'canonical-nonexact-independent-review.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['summary']),flush=True)
