"""Exact read-only native review of91 ballots; no production parser or DB calls.

Fresh Poppler originals + exhaustive named rosters + independently positioned
physical episode witnesses reviewed in the27-source native audit. No proposed
ballot's event list supplies attendance expectations. Unknown declarations hold.
"""
import ast,hashlib,json,re,subprocess
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
from functools import lru_cache
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent;CACHE=Path('/private/tmp/physical91-independent');CACHE.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
raw=(OUT/'physical91-ballot-plan.json').read_bytes();plan=json.loads(raw)
assert hashlib.sha256(raw).hexdigest()=='216255d99b57b9e7584e3eac1bee9ca2f8191a0ff105d3d93979a9c4bbfa6cba'
people=json.loads((OUT/'vote-people-current-snapshot.json').read_bytes());persons={p['id']:p for p in people}
snapshot=json.loads((OUT/'ballot-source-current-snapshot.json').read_bytes());meetings={m['id']:m for m in snapshot['meetings']};inventory=json.loads((OUT/'full-current-vote-inventory.json').read_bytes())
for p,h in plan['code_sha256s'].items():assert sha(ROOT/p)==h
# Reuse only the older independent native reader/name/declaration functions, not
# production helpers or that reader's attendance implementation.
libs={'review_repeated_key3_independently.py':{'spans','roster','pdf_source'},'review_historical82_independently.py':{'identity_patterns','exact_name_spans','decision_choices'}}
for file,names in libs.items():
 nodes=[n for n in ast.parse((OUT/file).read_text()).body if isinstance(n,ast.FunctionDef)and n.name in names]
 exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),file,'exec'),globals())
def norm(s):
 s=re.sub(r'\bTHAT(?=(?:Council|Committee)\b)','THAT ',s,flags=re.I)
 return re.sub(r'[^a-z0-9]+',' ',s.casefold()).strip()
# Primary original1971 scope + mandatory dissent naming; no pre2021 shortcut.
rule=ROOT/'archive/langford/Council/2021/10/2021-10-18 530pm Special Council [3e61e99f]/Agenda/Special Agenda Package.pdf'
assert sha(rule)=='9cf6e70459352537be177679b558bf8ab859e677e66ecba459bedd12d8709bbb'
ruletext=subprocess.run(['pdftotext','-f','159','-l','166','-layout',str(rule),'-'],capture_output=True,text=True,check=True).stdout
for quote in ['The provisions of this Bylaw govern the proceedings of Council, COTW, Commissions, and Committees','Where a motion is not unanimous, the meeting minutes will record the name(s) of any dissenters']:
 assert norm(quote)in norm(ruletext)
registry=Path('/private/tmp/committee-eligibility/official-council-appointments.html');assert sha(registry)=='191f44fb9b902f91d00ac24681216a8466afee6ec851e746c30768f8fe7e0a66'
listing=BeautifulSoup(registry.read_text(),'html.parser').select_one('.accordion-council_appointments10').get_text(' ',strip=True)
citizens={'Chris Foxall','Frazer Johnson','Nicolas Lehman','Robin Plomp','Jacqui Whiteway','Moira McDonald'};councillors={'Keith Yacucha','Mark Morley','Colby Harder'}
assert all(n in listing for n in citizens)
terms=Path('/private/tmp/committee-eligibility/terms2024.pdf');assert sha(terms)=='dd4dd8b6b95b963ef7c964be676e11d1a4603e1bbb27f2b847467ecefe748182'
termstext=subprocess.run(['pdftotext','-layout',str(terms),'-'],capture_output=True,text=True,check=True).stdout
terms_quotes=['The Mayor may attend any Committee meeting as an ex-officio voting member','Councillors who are not members of the Committee may attend and participate in any Committee meeting but may not vote','Committee decisions will be reached by a majority vote of members present','Committee quorum is a majority of appointed members, meaning fifty percent (50%) or greater, one of whom must be the Chair or Vice-Chair']
for quote in terms_quotes:assert norm(quote)in norm(termstext)
# Rebind original appointment proofs, not the present website to invented terms.
appts=json.loads((OUT/'committee-membership-date-correction-plan.json').read_bytes())['source_proofs']
for proof in appts.values():
 assert sha(ROOT/proof['source_file'])==proof['source_sha256']
 t=subprocess.run(['pdftotext','-layout',str(ROOT/proof['source_file']),'-'],capture_output=True,text=True,check=True).stdout
 assert norm(proof['source_quote'])in norm(t)
physical=json.loads((OUT/'presence27-native-physical-replay.json').read_bytes());assert physical['helper_sha256']==plan['code_sha256s']['apps/pipeline/pipeline/ingestion/ballot_reconstruction.py']
manual={r['meeting_id']:r for r in physical['records']}
census=json.loads((OUT/'presence179-native-source-census.json').read_bytes())
bare_quotes={(r['meeting_id'],e['offset']):e['native_paragraph']for r in census['records']for e in r['events']}
# The complete literal episode registry was independently read against every
# native paragraph in27-source review. Rebind each witness to fresh text offsets,
# preserve actor/state/order and reject ambiguous repeated paragraph occurrences.
def anchor(text,quote):
 words=list(re.finditer(r'[a-z0-9]+',text.casefold()));needle=re.findall(r'[a-z0-9]+',quote.casefold());tokens=[w.group()for w in words]
 hits=[i for i in range(len(tokens)-len(needle)+1)if tokens[i:i+len(needle)]==needle]
 if len(hits)>1:
  exact=[]
  for i in hits:
   a=words[i].start();b=words[i+len(needle)-1].end()
   before=list(re.finditer(r'\n[ \t]*\n',text[:a]));after=re.search(r'\n[ \t]*\n',text[b:])
   start=before[-1].end()if before else 0;end=b+after.start()if after else len(text)
   if norm(text[start:end])==norm(quote):exact.append(i)
  hits=exact
 if len(hits)!=1:raise ValueError('native_witness_not_unique:'+str(len(hits))+':'+quote[:80])
 i=hits[0];return words[i].start(),words[i+len(needle)-1].end()
def episodes(src,mid):
 events=[];seen={}
 if mid in manual:
  for e in manual[mid]['events']:
   a,b=anchor(src['text'],e['native_paragraph']);part=src['text'][a:b]
   # Exactphysicalverb + native witness actors: separate independently anchored
   # occurrences of an inline exit and return retain their relative order.
   verb=e['verb'];hits=list(re.finditer(r'\b'+r'\s+'.join(map(re.escape,verb.split()))+r'\b',part,re.I))
   if len(hits)!=1:raise ValueError('physical_verb_not_unique_in_native_witness')
   last=persons[e['person_id']]['name'].split()[-1]
   named=re.sub(r'\b(Councillor|Mayor)(?=[A-Z][a-z])',r'\1 ',part)
   if not re.search(r'\b'+re.escape(last)+r'\b',named,re.I):raise ValueError('physical_witness_actor_missing')
   position=a+hits[0].start();key=(position,e['person_id'])
   if key in seen:raise ValueError('duplicate_physical_identity_at_same_source_position')
   seen[key]=True;events.append({'offset':position,'person_id':e['person_id'],'state':e['state'],'verb':verb,'native_quote':part})
  holds=[]
  for h in manual[mid]['retained_holds']:
   a,b=anchor(src['text'],bare_quotes[(mid,h['offset'])]);matches=list(re.finditer(r'conflict\s+of\s+interest',src['text'][a:b],re.I))
   if len(matches)!=1:raise ValueError('unscoped_declaration_witness_ambiguous')
   holds.append({'offset':a+matches[0].start(),'native_quote':src['text'][a:b]})
 else:
  assert mid==192
  # Additional source outside original27: two literal named movements, no
  # other member movement (road-network connection wording is nonphysical).
  for verb,state in [('left','absent'),('returned','present')]:
   pattern=r'Councillor Harder(?: at 8:15 pm[.])?\s+'+verb+r'\s+(?:to\s+)?the meeting[^\n]*(?:\n\s*interest[^\n]*)?'
   hits=list(re.finditer(pattern,src['text'],re.I))
   if len(hits)!=1:raise ValueError('192_literal_event_missing_or_repeated')
   h=hits[0];events.append({'offset':h.start()+re.search(r'\b'+verb+r'\b',h.group(),re.I).start(),'person_id':21,'state':state,'verb':verb,'native_quote':h.group()})
  holds=[]
 events.sort(key=lambda e:(e['offset'],e['person_id']))
 return events,holds
loaded={};records=[]
for c in plan['records']:
 record={'motion_id':c['motion_id'],'meeting_id':c['meeting_id'],'source_sha256':c['source_sha256']}
 try:
  mid=c['meeting_id'];path=ROOT/c['source_file'];assert sha(path)==c['source_sha256']
  if mid not in loaded:
   src=pdf_source(c);src['events'],src['holds']=episodes(src,mid);loaded[mid]=src
  src=loaded[mid];header=src['header'];is_cac=c['voting_body']=='community_advisory_committee'
  assert ('community advisory committee'in norm(header))if is_cac else ('council minutes'in norm(header)and'committee'not in norm(header))
  datehit=re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s*(20\d{2})',header,re.I);assert datehit
  day=datetime.strptime(' '.join(datehit.groups()),'%B %d %Y').date().isoformat();assert day==c['source_date']and day>='2021-10-18'
  assert abs((datetime.fromisoformat(day)-datetime.fromisoformat(meetings[mid]['meeting_date'])).days)<=1
  active={m['person_id']for m in snapshot['memberships']if m['classification']=='Council'and m.get('start_date')and m['start_date']<=day and(not m.get('end_date')or m['end_date']>=day)}
  pool=[p for p in people if p['name']in citizens|councillors|{'Scott Goodmanson'}]if is_cac else[persons[pid]for pid in active]
  native_present=re.sub(r'(?i)\b(Mayor|Councillor)(?=[a-z][.])',r'\1 ',src['present'])
  initial,unknown=roster(native_present);absent,absent_unknown=roster(src['absent'],True)
  assert not initial&absent
  if not is_cac:assert initial<=active
  else:
   assert day>='2024-07-15'
   assert {pid for pid in initial if persons[pid]['name']in councillors}<=active
   assert all(persons[pid]['name']in citizens|councillors|{'Scott Goodmanson'}for pid in initial)
   assert all(persons[pid]['name']!='Scott Goodmanson'or pid in active for pid in initial)
  # First recorded result binds complete operative body; ambiguous repeats need
  # unique complete formal witness, including actors and neighboring content.
  matches=[b for b in src['blocks']if norm(b['body'])==norm(c['source_motion_text'])]
  if len(matches)>1:matches=[b for b in matches if norm(b['chunk'])==norm(c['source_block'])]
  if len(matches)!=1:raise ValueError('full_formal_body_identity_not_unique:'+str(len(matches)))
  block=matches[0];assert block['result']==c['source_result']
  cutoff=block['cutoff'];assert not[h for h in src['holds']if h['offset']<cutoff],'earlier_unscoped_conflict_declaration'
  present=set(initial);first={}
  for e in src['events']:first.setdefault(e['person_id'],e)
  for pid,e in first.items():
   if e['state']=='present':
    if e['verb']in{'arrived','joined'}:present.discard(pid)
    elif cutoff<e['offset']:raise ValueError('initial_state_before_first_return_unknown')
   if e['verb'].startswith('remained')and cutoff<e['offset']:raise ValueError('absence_observation_not_initial_exit')
  applied=[]
  for e in src['events']:
   if e['offset']>=cutoff:break
   if e['state']=='present':present.add(e['person_id'])
   else:present.discard(e['person_id'])
   applied.append(e)
  chairs=set()
  if is_cac:
   for line in native_present.splitlines():
    if re.search(r'\bChair\b',line,re.I):chairs.update(pid for _,_,pid in spans(line,pool)if persons[pid]['name']in councillors)
   appointees={pid for pid in present if persons[pid]['name']in citizens|councillors}
   assert len(appointees)>=5 and present&chairs
   assert all(pid in initial or pid in absent for pid in present)
   for o in c['member_observations']:
    section=src['present']if o['observed_attendance']=='present'else src['absent'];ids=initial if o['observed_attendance']=='present'else absent
    assert o['person_id']in ids and norm(o['source_quote'])==norm(section)and o['source_sha256']==c['source_sha256']and o['observed_date']==day
  else:assert 4<=len(present)<=7 and present<=active
  native_block={'tail':block['tail']};declared,declarations=decision_choices(native_block,pool)
  assert set(declared)<=present,'named_dissenter_not_present'
  expected={pid:declared.get(pid,'Yes')for pid in present};proposed={v['person_id']:v['vote']for v in c['votes']}
  assert expected==proposed,'independent_voter_or_choice_set_differs'
  for choice in c['votes']:
   assert choice['person_name']==persons[choice['person_id']]['name']
   assert choice['evidence']==('explicit_named'if choice['person_id']in declared else'inferred_official_dissent_recording_rule')
   assert norm(choice['source_quote'])in norm(src['text']),'per_choice_quote_not_native'
  yes=sum(v=='Yes'for v in expected.values());assert block['result'].startswith('CARRIED')==(yes>len(expected)-yes),'tally_outcome_conflict'
  old=[v for v in inventory['votes']if v['motion_id']==c['motion_id']]
  assert {(v['id'],v['person_id'],v['vote'],v['updated_at'])for v in old}=={(v['id'],v['person_id'],v['vote'],v['updated_at'])for v in c['current_choices']}
  assert all(expected[v['person_id']]==v['vote']for v in old)
  record.update(status='reviewed',source_file=c['source_file'],source_url=c['source_url'],native_text_sha256=src['native_text_sha256'],source_date=day,native_header=header,native_present_quote=src['present'],native_absent_quote=src['absent'],native_staff_quote=src['staff'],initial_present_ids=sorted(initial),present_at_vote_ids=sorted(present),chair_ids=sorted(chairs),independent_physical_events=applied,native_formal_body=block['body'],native_formal_result=block['result'],native_declared_choices=declarations,choices=[{'person_id':pid,'vote':v}for pid,v in sorted(expected.items())],existing_vote_ids=[v['id']for v in old],new_choices=len(expected)-len(old),checks=['fresh_original_pdf_sha256','native_own_header_date_body','exhaustive_roster_identity_tokens','dated_council_offices_or_dated_CAC_observation','staff_visitors_excluded','source_verified_full_physical_registry_independent_offsets','complete_formal_body_first_result_unique','all_named_dissent_accounted','primary1971_dissent_rule_scope','Council_or_CAC_quorum','existing_ids_values_preserved'])
 except(AssertionError,ValueError,subprocess.SubprocessError)as error:record.update(status='held',reason=str(error))
 records.append(record)
for p,h in plan['code_sha256s'].items():assert sha(ROOT/p)==h
summary={'candidate_ballots':len(records),'source_files':len(loaded),'statuses':dict(Counter(r['status']for r in records)),'proof_issues':sum(r['status']!='reviewed'for r in records),'new_choices_reviewed':sum(r.get('new_choices',0)for r in records),'existing_choices_preserved':sum(len(r.get('existing_vote_ids',[]))for r in records)}
out={'mode':'independent_read_only_physical91_native_review','candidate_plan_sha256':hashlib.sha256(raw).hexdigest(),'review_script_sha256':sha(Path(__file__)),'summary':summary,'reviewed_candidate_ids':[r['motion_id']for r in records if r['status']=='reviewed'],'integration_sha256':sha(ROOT/'apps/pipeline/pipeline/ingestion/meeting_ballots.py'),'native_physical_registry_sha256':sha(OUT/'presence27-native-physical-replay.json'),'independent_reader_dependencies':{p:sha(OUT/p)for p in libs},'policy_original_sha256':sha(rule),'committee_terms_sha256':sha(terms),'committee_terms_native_quotes':terms_quotes,'appointment_proofs':appts,'records':records}
applier=OUT/'apply_physical91_ballots.py';assert sha(applier)=='d5e55081663a00f57adae7afa58dbfdc47092df66e2513f65673f6972cef1814'
out['apply_script_sha256']=sha(applier)
out['apply_script_review']={'status':'reviewed','template':'apply_repeated_key3_ballots.py','checks':['immutable_plan_review_before_bytes','exact91IDs607missing20preserved','SERIALIZABLE_and_full_motion_vote_catalog_CAS_locks','live_source_policy_membership_per_choice_replay','append_only_existing_vote_IDs_preserved','metadata_only_no_text_result_agenda_writes','durable_precommit_receipt','guarded_exact_afterstate_rollback_SQLNULL_precision']}
p=OUT/'physical91-independent-review.json';p.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(summary));print('review_sha256',sha(p));print(json.dumps([{'motion_id':r['motion_id'],'reason':r['reason']}for r in records if r['status']=='held']))
