"""Read-only one-to-one mappings between source formal motions and legacy rows.

Source identity is authoritative; no fuzzy similarity, model verdict, vote
insertion, duplicate insertion or retirement is performed by this proposal.
"""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter,defaultdict
import json,re,hashlib

OUT=Path(__file__).parent
base=json.loads((OUT/'ballot-source-snapshot.json').read_text())
universe=json.loads((OUT/'canonical-official-motion-inventory.json').read_text())
legacy={r['id']:dict(r)for r in base['motions']};canonical={r['canonical_source_motion_key']:r for r in universe['canonical_motions']}
receiptpath=OUT/'source-correction-atomic-receipt.json'
if receiptpath.exists():
 for change in json.loads(receiptpath.read_text())['changes']:
  legacy[change['motion_id']]['text_content']=change['after_text'];legacy[change['motion_id']]['meta']=change['after_meta']

def norm(text):
 text=re.sub(r'\bTHAT(?=Council\b|Committee\b)','THAT ',text or'')
 text=re.sub(r'[^a-z0-9]+',' ',text.casefold()).strip()
 return text

def content(text):
 # Strip explicitly identified clerk wrappers from legacy text for matching
 # only. The proposed canonical source text and original DB text are retained.
 text=re.sub(r'^.*?\bTHAT(?=\b|Council\b|Committee\b)','THAT',text or'',count=1,flags=re.I)if re.match(r'^\s*MOVED BY\b',text or'',re.I)else text or''
 return re.split(r'\bMotion\s+(?:CARRIED|DEFEATED|WITHDRAWN)\b',text,maxsplit=1,flags=re.I)[0].strip()

stop={'the','a','an','that','to','of','for','and','be','is','as','by','with','it','its','on','in','at','from','this','these','those','moved','seconded','motion','carried','therefore','resolved','council','committee','whole'}
actions={'approve','adopt','receive','authorize','include','exclude','remove','reduce','increase','amend','delete','retain','proceed','defer','table','refer','rescind','waive','terminate','deny','refuse','reject','direct','repeal','recommend'}
negations={'not','no','never','unless','without','except','against'}

def numbers(text):return re.findall(r'\$?\d[\d,]*(?:\.\d+)?%?',text)

def actor_match(old,new):
 if not old or not new:return False
 a=norm(old).split();b=norm(new).split()
 if not a or not b or a[-1]!=b[-1]:return False
 a=[w for w in a[:-1]if w not in{'mayor','councillor','councillors','committee','member'}]
 b=[w for w in b[:-1]if w not in{'mayor','councillor','councillors','committee','member'}]
 return not a or not b or a[0][0]==b[0][0]

def supported(old,new):
 old=content(old);required=set(norm(old).split())-stop;available=set(norm(new).split())-stop
 return len(required)>=3 and numbers(old)==numbers(new)and required<=available

bymeeting=defaultdict(list)
for key,row in canonical.items():bymeeting[row['meeting_id']].append(key)
used={};mapped={};mappings=[]

def accept(mid,key,method,extra=None):
 assert mid not in mapped and key not in used
 row=legacy[mid];source=canonical[key];old=content(row['text_content']);oldwords=norm(old).split();newwords=norm(source['source_motion_text']).split()
 addedneg=(Counter(w for w in newwords if w in negations)-Counter(w for w in oldwords if w in negations))
 removedactions=(Counter(w for w in oldwords if w in actions)-Counter(w for w in newwords if w in actions))
 change_kind='exact_or_presentation_only'if norm(row['text_content'])==norm(source['source_motion_text'])else'source_correction_requires_independent_review'
 if'recommend'in newwords and'recommend'not in oldwords:change_kind='substantive_restore_omitted_recommendation'
 if re.search(r'foregoing motion be amended|main motion be amended',source['source_motion_text'],re.I)and not re.search(r'foregoing motion be amended|main motion be amended',old,re.I):change_kind='substantive_restore_omitted_amendment_wrapper'
 if addedneg:change_kind='substantive_source_adds_negation_or_condition_requires_review'
 if removedactions:change_kind='substantive_action_difference_requires_review'
 mapping={'legacy_motion_id':mid,'meeting_id':row['meeting_id'],'canonical_source_motion_key':key,'method':method,'correction_kind':change_kind,
  'original_motion_text':row['text_content'],'official_motion_text':source['source_motion_text'],'source_sha256':source['source_sha256'],'source_file':source['source_file'],
  'source_result':source['source_result'],'stored_result':row['result'],'stored_agenda_number':row.get('item_order'),'source_agenda_number':source['agenda_item_number'],
  'source_order':source['source_order'],'mover':source['mover'],'seconder':source['seconder'],'added_negation_or_conditions':dict(addedneg),'removed_action_tokens':dict(removedactions),
  'not_automatic_insert_or_retirement':True}
 if extra:mapping.update(extra)
 mapped[mid]=key;used[key]=mid;mappings.append(mapping)

# Exact body mappings require uniqueness on both sides of the same meeting.
exact_edges={mid:[key for key in bymeeting[row['meeting_id']]if norm(row['text_content'])==norm(canonical[key]['source_motion_text'])]for mid,row in legacy.items()}
reverse=Counter(key for keys in exact_edges.values()for key in keys)
for mid,keys in exact_edges.items():
 if len(keys)==1 and reverse[keys[0]]==1:accept(mid,keys[0],'unique_exact_source_body')

# All substantive tokens and protected quantities must be supported in one
# formal source motion; both actor fields must match. This can repair a stale
# agenda number without pretending that its new number alone proves identity.
while True:
 edges={}
 for mid,row in legacy.items():
  if mid in mapped:continue
  eligible=[key for key in bymeeting[row['meeting_id']]if key not in used and actor_match(row.get('mover'),canonical[key]['mover'])and actor_match(row.get('seconder'),canonical[key]['seconder'])and supported(row['text_content'],canonical[key]['source_motion_text'])]
  same=[key for key in eligible if str(row.get('item_order')or'').strip('.')==str(canonical[key]['agenda_item_number']or'').strip('.')]
  edges[mid]=same or eligible
 reverse=Counter(key for keys in edges.values()for key in keys)
 ready=[(mid,keys[0])for mid,keys in edges.items()if len(keys)==1 and reverse[keys[0]]==1]
 if not ready:break
 for mid,key in ready:accept(mid,key,'unique_actor_quantity_and_all_substantive_tokens',{'agenda_number_changed':str(legacy[mid].get('item_order')or'').strip('.')!=str(canonical[key]['agenda_item_number']or'').strip('.')})

unresolved=[]
for mid,row in legacy.items():
 if mid in mapped:continue
 available=[key for key in bymeeting[row['meeting_id']]if key not in used]
 numbered=[key for key in available if str(row.get('item_order')or'').strip('.')==str(canonical[key]['agenda_item_number']or'').strip('.')]
 actors=[key for key in available if actor_match(row.get('mover'),canonical[key]['mover'])and actor_match(row.get('seconder'),canonical[key]['seconder'])]
 scoped=[key for key in numbered if key in actors]
 candidates=scoped or actors or numbered
 if len(scoped)==1:stage='one_agenda_actor_source_requires_substantive_review'
 elif len(actors)==1:stage='one_meeting_actor_source_requires_agenda_and_substantive_review'
 elif candidates:stage='multiple_possible_source_mappings_require_review'
 elif exact_edges[mid]:stage='duplicate_legacy_or_source_exact_body'
 elif not available:stage='no_unmapped_source_node; possible_legacy_duplicate_or_narrative'
 else:stage='no_agenda_or_actor_anchor; source_order_and_primary_text_review_required'
 unresolved.append({'legacy_motion_id':mid,'meeting_id':row['meeting_id'],'original_motion_text':row['text_content'],'result':row['result'],'item_order':row.get('item_order'),
  'mover':row.get('mover'),'seconder':row.get('seconder'),'status':stage,'candidate_source_keys':candidates,'exact_source_keys':exact_edges[mid]})
unmapped=[key for key in canonical if key not in used]
result={'mode':'read_only_one_to_one_source_to_legacy_mapping_proposals','at':datetime.now(timezone.utc).isoformat(),
 'input_sha256':{f:hashlib.sha256((OUT/f).read_bytes()).hexdigest()for f in['ballot-source-snapshot.json','canonical-official-motion-inventory.json','source-correction-atomic-receipt.json']},'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 'summary':{'legacy_motions':len(legacy),'canonical_source_formal_decisions':len(canonical),'one_to_one_mapping_proposals':len(mappings),'mapping_methods':dict(Counter(m['method']for m in mappings)),
  'correction_kinds':dict(Counter(m['correction_kind']for m in mappings)),'unresolved_legacy_rows':len(unresolved),'unresolved_stages':dict(Counter(r['status']for r in unresolved)),
  'unmapped_source_decisions':len(unmapped),'inserts_or_retirements':0,'paid_model_calls':0},'mappings':mappings,'unresolved_legacy':unresolved,'unmapped_canonical_source_keys':unmapped}
(OUT/'canonical-motion-legacy-mapping-proposals.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result['summary'],indent=2),flush=True)
