"""Read-only full-archive legacy/source identity proposals; no model verdicts.

Original 113-mapping inputs stay immutable. Source words are authoritative;
protected quantities/actions/negation differences are disclosed, never quietly
called equivalent. No insert, retirement, text correction or vote is applied.
"""
from pathlib import Path
from collections import Counter,defaultdict
from datetime import datetime,timezone
import hashlib,json,re,subprocess
from pipeline.ingestion.official_ballots import html_minutes_text

ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
FILES=['ballot-source-current-snapshot.json','current-full-ballot-audit.json','canonical-official-motion-inventory-v2.json']
raw={name:(OUT/name).read_bytes() for name in FILES};hashes={name:hashlib.sha256(body).hexdigest() for name,body in raw.items()}
data=json.loads(raw[FILES[0]]);audit=json.loads(raw[FILES[1]]);universe=json.loads(raw[FILES[2]])
assert audit['summary']['current_motion_snapshot_sha256']==hashes[FILES[0]],'Audit/snapshot mismatch: refresh before triage'
legacy={row['id']:row for row in data['motions']}
targets={row['motion_id'] for row in audit['motions'] if row['status']=='source_motion_not_exact_or_ambiguous'}

def norm(text):
    text=re.sub(r'\bTHAT(?=Council\b|Committee\b)','THAT ',text or'',flags=re.I)
    return re.sub(r'[^a-z0-9]+',' ',text.casefold()).strip()

STOP={'the','a','an','that','to','of','for','and','be','is','as','by','with','it','its','on','in','at','from','this','these','those','moved','seconded','motion','carried','therefore','resolved','council','committee','whole'}
ACTIONS={'approve','adopt','receive','authorize','include','exclude','remove','reduce','increase','amend','delete','retain','proceed','defer','table','refer','rescind','waive','terminate','deny','refuse','reject','direct','repeal','recommend','consider','postpone','appoint','issue'}
NEGATIONS={'not','never','unless','without','except','against'}

def numbers(text):
    return [part.replace(',','').lstrip('$') for part in re.findall(r'\$?\d[\d,]*(?:\.\d+)?%?',text or'')]

def words(text):
    return set(norm(text).split())-STOP

def critical(text):
    cleaned=re.sub(r'\bNo\.?\s*(?=\d)','number ',text or'',flags=re.I)
    tokens=norm(cleaned).split()
    return {'numbers':numbers(text),'actions':dict(Counter(t for t in tokens if t in ACTIONS)),
            'negation':dict(Counter(t for t in tokens if t in NEGATIONS or t=='no'))}

def actor_match(old,new):
    if not old or not new:return False
    def parts(value):
        value=re.sub(r'^(?:Acting\s+)?(?:Councillors?|Mayor|Committee\s+Member)\s*','',value,flags=re.I)
        return norm(value).split()
    a=parts(old);b=parts(new)
    return bool(a and b and a[-1]==b[-1] and (len(a)<2 or len(b)<2 or a[0][0]==b[0][0]))

def agenda_equal(old,new):return bool(old and new and str(old).strip('.')==str(new).strip('.'))

sources={row['meeting_id']:row for row in universe['sources']}
bymeeting=defaultdict(list);canonical={};native_text={}
for mid,source in sources.items():
    if source.get('error'):continue
    path=ROOT/source['source_file'];assert hashlib.sha256(path.read_bytes()).hexdigest()==source['source_sha256']
    text=subprocess.check_output(['pdftotext','-layout',str(path),'-'],text=True) if path.suffix.lower()=='.pdf' else html_minutes_text(path)
    text=re.sub(r'(?im)^\s*Minutes of[^\n]*\n','\n',text)
    native_text[mid]=re.sub(r'(?m)^\s*\d+\s*$','',text).replace('\f','\n')
for record in universe['canonical_motions']:
    source=dict(record);mid=source['meeting_id'];text=native_text[mid]
    header=source['source_block'].split(source['raw_motion_text'],1)[0]
    for field,role in [('mover','MOVED'),('seconder','SECONDED')]:
        found=re.search(r'(?im)^\s*'+role+r'(?:[ \t]+BY)?[ \t]*:?[ \t]*([^\n]+)',header)
        source[field]=found[1].strip() if found else None
    canonical[source['key']]=source;bymeeting[mid].append(source['key'])
# Native numeric agenda headers are hints only. Exclude the formal operative
# spans (numbered conditions are not agenda headings) and obvious streetnumbers.
for mid,keys in bymeeting.items():
    text=native_text[mid];formal_spans=[]
    for key in keys:
        s=canonical[key];start=text.find(s['source_block'],s['source_offset'])
        end=text.find(s['outcome_quote'],start,start+len(s['source_block'])) if start>=0 else -1
        if start>=0 and end>=0:formal_spans.append((start,end+len(s['outcome_quote'])))
    headings=[]
    for hit in re.finditer(r'(?m)^[ \t]*(\d+(?:\.\d+)*\.?)\s+([A-Z][^\n]{2,180})',text):
        number=hit[1].strip('.')
        if int(number.split('.')[0])>40 or any(a<=hit.start()<b for a,b in formal_spans):continue
        headings.append((hit.start(),number,hit[2].strip()))
    for key in keys:
        s=canonical[key];before=[h for h in headings if h[0]<s['source_offset']]
        s['agenda_number_hint']=before[-1][1] if before else None;s['agenda_title_hint']=before[-1][2] if before else None
        s['agenda_hint_not_authority_for_relink']=True
        s['critical']=critical(s['raw_motion_text']);s['body_tokens']=words(s['raw_motion_text'])

mapped={};used={};methods={}
def accept(mid,key,method):
    assert mid not in mapped and key not in used
    mapped[mid]=key;used[key]=mid;methods[mid]=method

def assign_unique(edges,method):
    reverse=Counter(key for keys in edges.values() for key in keys)
    ready=[(mid,keys[0]) for mid,keys in edges.items() if len(keys)==1 and reverse[keys[0]]==1]
    for mid,key in ready:accept(mid,key,method)
    return len(ready)

# Reserve identities across the entire current archive, not merely the target
# holds. Otherwise a target could steal an already-certified source decision.
exact={mid:[key for key in bymeeting[row['meeting_id']] if norm(row['text_content'])==norm(canonical[key]['raw_motion_text'])] for mid,row in legacy.items()}
assign_unique(exact,'unique_exact_native_body_all_archive')
for result in audit['motions']:
    mid=result['motion_id']
    if mid in mapped or result['status']!='reconstructable_candidate':continue
    keys=[key for key in bymeeting[result['meeting_id']] if key not in used and canonical[key]['source_sha256']==result['source_sha256'] and norm(canonical[key]['source_block'])==norm(result['source_block'])]
    if len(keys)==1:accept(mid,keys[0],'existing_shared_validator_unique_full_source_block')

while True:
    edges={}
    for mid,row in legacy.items():
        if mid in mapped:continue
        protected=critical(row['text_content']);tokens=words(row['text_content'])
        candidates=[key for key in bymeeting[row['meeting_id']] if key not in used and actor_match(row.get('mover'),canonical[key]['mover']) and actor_match(row.get('seconder'),canonical[key]['seconder']) and protected['numbers']==canonical[key]['critical']['numbers'] and len(tokens)>=3 and tokens<=canonical[key]['body_tokens']]
        same=[key for key in candidates if agenda_equal(row.get('item_order'),canonical[key]['agenda_number_hint'])]
        edges[mid]=same or candidates
    if not assign_unique(edges,'unique_actor_quantities_all_legacy_body_tokens'):break

proposals=[];unresolved=[]
for mid in sorted(targets):
    row=legacy[mid]
    if mid in mapped:
        keys=[mapped[mid]];stage='one_to_one_source_mapping_proposed';method=methods[mid]
    else:
        available=[key for key in bymeeting[row['meeting_id']] if key not in used]
        actors=[key for key in available if actor_match(row.get('mover'),canonical[key]['mover']) and actor_match(row.get('seconder'),canonical[key]['seconder'])]
        grouped=[key for key in actors if agenda_equal(row.get('item_order'),canonical[key]['agenda_number_hint'])]
        same_numbers=[key for key in (grouped or actors) if critical(row['text_content'])['numbers']==canonical[key]['critical']['numbers']]
        keys=grouped or actors or [key for key in available if agenda_equal(row.get('item_order'),canonical[key]['agenda_number_hint'])]
        if len(same_numbers)==1:
            stage='single_actor_quantity_source_requires_substantive_identity_review';keys=same_numbers
        elif len(grouped)==1:stage='single_agenda_actor_source_with_critical_difference_requires_review'
        elif exact[mid]:stage='repeated_legacy_or_repeated_source_body'
        elif len(keys)>1:stage='multiple_source_identity_candidates'
        elif len(keys)==1:stage='single_agenda_only_source_not_proven'
        elif not bymeeting[row['meeting_id']]:stage='source_unavailable_or_no_parsed_formal_decision'
        else:stage='no_remaining_agenda_actor_source_identity'
        method=None
    entry={'motion_id':mid,'meeting_id':row['meeting_id'],'agenda_item_id':row['agenda_item_id'],'original_motion_text':row['text_content'],
        'stored_result':row.get('result'),'stored_agenda_number':row.get('item_order'),'stored_mover':row.get('mover'),'stored_seconder':row.get('seconder'),
        'status':stage,'mapping_method':method,'protected_original':critical(row['text_content']),'candidates':[],'writes_authorized_by_this_report':False}
    for key in keys:
        s=canonical[key];oldcritical=entry['protected_original'];newcritical=s['critical']
        entry['candidates'].append({field:s.get(field) for field in ('key','source_file','source_url','source_sha256','source_offset','source_order','raw_motion_text','source_block','outcome_quote','source_result','mover','seconder','agenda_number_hint','agenda_title_hint','agenda_hint_not_authority_for_relink','formal_source_kind')}|{
            'protected_source':newcritical,'numbers_equal':oldcritical['numbers']==newcritical['numbers'],'negation_equal':oldcritical['negation']==newcritical['negation'],
            'actions_equal':oldcritical['actions']==newcritical['actions'],'missing_legacy_tokens':sorted(words(row['text_content'])-s['body_tokens']),
            'added_source_tokens':sorted(s['body_tokens']-words(row['text_content']))})
    (proposals if mid in mapped else unresolved).append(entry)
for name,body in raw.items():
    if (OUT/name).read_bytes()!=body:raise RuntimeError('Input changed during triage: '+name)
report={'mode':'read_only_1177_legacy_source_identity_triage_v2','at':datetime.now(timezone.utc).isoformat(),'input_sha256':hashes,
    'summary':{'target_holds':len(targets),'all_archive_reserved_identities':len(mapped),'one_to_one_target_proposals':len(proposals),
        'proposal_methods':dict(Counter(e['mapping_method'] for e in proposals)),
        'remaining_statuses':dict(Counter(e['status'] for e in unresolved)),
        'target_formal_source_kinds':dict(Counter(e['candidates'][0]['formal_source_kind'] for e in proposals)),
        'live_writes':0,'paid_model_calls':0,'independent_source_review_required':True},'proposals':proposals,'unresolved':unresolved}
(OUT/'legacy-source-identity-triage-v2.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report['summary'],indent=2))
