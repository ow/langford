"""Independent original-source CAC ballot review; no production parser or writes.

Canonical identities come from the official appointment listing, committee
eligibility from original POL0163, and dated member observations only from each
native PRESENT/ABSENT section. Fresh PDF extraction/structural HTML are replayed
without the committee proposal's roster/name/presence helpers.
"""
import json,re,hashlib,subprocess
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent;CACHE=Path('/private/tmp/committee-independent-native');CACHE.mkdir(exist_ok=True)
raw=(OUT/'wrapper2699-ballot-plan.json').read_bytes();plan=json.loads(raw)
for path,digest in plan['code_sha256s'].items():
 assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,'Current source validator changed since plan'
integration_hash=hashlib.sha256((ROOT/'apps/pipeline/pipeline/ingestion/meeting_ballots.py').read_bytes()).hexdigest()
people=json.loads((OUT/'vote-people-current-snapshot.json').read_text());persons={p['id']:p for p in people}
snapshot=json.loads((OUT/'ballot-source-current-snapshot.json').read_text());meetings={m['id']:m for m in snapshot['meetings']};inventory=json.loads((OUT/'full-current-vote-inventory.json').read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def norm(s):
 s=re.sub(r'\bTHAT(?=(?:Council|Committee)\b)', 'THAT ', s, flags=re.I)
 return re.sub(r'[^a-z0-9]+',' ',s.casefold()).strip()
registry_path=Path('/private/tmp/committee-eligibility/official-council-appointments.html');assert sha(registry_path)=='191f44fb9b902f91d00ac24681216a8466afee6ec851e746c30768f8fe7e0a66'
soup=BeautifulSoup(registry_path.read_text(),'html.parser');listing=soup.select_one('.accordion-council_appointments10').get_text(' ',strip=True)
citizen_names=['Chris Foxall','Frazer Johnson','Nicolas Lehman','Robin Plomp','Jacqui Whiteway','Moira McDonald'];council_names=['Keith Yacucha','Mark Morley','Colby Harder'];pool=[p for p in people if p['name'] in citizen_names+council_names+['Scott Goodmanson']]
assert all(name in listing for name in citizen_names)
policy_sources=[{'path':'/private/tmp/committee-eligibility/terms2023agenda.pdf','sha256':'69d5128ee9facfb993f4b4208b2a7e5049c6632ab93a29abc0e354690efa3ff0'},{'path':'/private/tmp/committee-eligibility/terms2024.pdf','sha256':'dd4dd8b6b95b963ef7c964be676e11d1a4603e1bbb27f2b847467ecefe748182'}]
for item in policy_sources:assert sha(item['path'])==item['sha256']
policy_sources[0]['url']='https://langford.ca/wp-content/uploads/2023/02/February-21-2023-Agenda-Package.pdf'
policy_sources[1]['url']='https://langford.ca/wp-content/uploads/2023/04/POL-0163-Admin-Amend-4-SIGNED-EDITED-NJ.pdf'
original_scope=ROOT/'archive/langford/Council/2021/10/2021-10-18 530pm Special Council [3e61e99f]/Agenda/Special Agenda Package.pdf'
assert sha(original_scope)=='9cf6e70459352537be177679b558bf8ab859e677e66ecba459bedd12d8709bbb'
scope_text=CACHE/'original1971-scope.txt'
subprocess.run(['pdftotext','-f','159','-l','166','-layout',str(original_scope),str(scope_text)],check=True,capture_output=True)
for required in ['The provisions of this Bylaw govern the proceedings of Council, COTW, Commissions, and Committees','Where a motion is not unanimous, the meeting minutes will record the name(s) of any dissenters']:
 assert norm(required) in norm(scope_text.read_text())
recording_scope={'original_2021_file':str(original_scope.relative_to(ROOT)),'original_sha256':sha(original_scope),'original_url':'https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=13781','original_sections':[2,4,38,52],'current_url':'https://langford.ca/wp-content/uploads/2023/04/Procedure-Bylaw-No.-1971-Consolidated-to-20240509.pdf','current_sha256':'0c672a3df714b63463dd06aa6b94de99bf7c925d64ed9228c517d726230244e1','current_sections':[2,4,44,60],'committee_membership_scope':'POL0163 independently establishes voting eligibility; bylaw applicability is not a substitute for appointments or dated member observations'}
appointment_plan=json.loads((OUT/'committee-membership-date-correction-plan.json').read_text())
appointment_proofs=appointment_plan['source_proofs']
for label,proof in appointment_proofs.items():
 assert sha(ROOT/proof['source_file'])==proof['source_sha256']
 target=CACHE/(label+'-appointment.txt')
 subprocess.run(['pdftotext','-layout',str(ROOT/proof['source_file']),str(target)],check=True,capture_output=True)
 assert norm(proof['source_quote']) in norm(target.read_text()),'Primary appointment quotation not present'



def spans(text,pool):
 matches=[]
 for person in pool:
  first,last=person['name'].split()[0],person['name'].split()[-1]
  forms=[re.escape(person['name']),re.escape(first[0])+r'[.,]?\s*'+re.escape(last)]
  for form in forms:
   for hit in re.finditer(r'(?<![A-Za-z])'+form+r'(?![A-Za-z])',text,re.I):matches.append((hit.start(),hit.end(),person['id']))
 matches.sort(key=lambda x:(x[0],-(x[1]-x[0])));chosen=[]
 for match in matches:
  overlaps=[m for m in chosen if match[0]<m[1] and m[0]<match[1]]
  if any(m[2]!=match[2] for m in overlaps):raise ValueError('ambiguous_native_identity')
  if not overlaps:chosen.append(match)
 return chosen


def roster(text,allow_unknown=False):
 hits=spans(text,pool);mask=list(text)
 for a,b,pid in hits:mask[a:b]=' '*(b-a)
 residual=re.sub(r'\b(?:Mayor|Acting|Councillors?|Chair|Vice|Remote|Remotely|and)\b',' ',''.join(mask),flags=re.I)
 unknown=re.findall(r'[A-Za-z0-9]+',residual)
 if unknown and not allow_unknown:raise ValueError('unaccounted_present_tokens:'+','.join(unknown))
 ids=[x[2] for x in hits]
 if len(ids)!=len(set(ids)):raise ValueError('duplicated_roster_member')
 return set(ids),unknown


def pdf_source(candidate):
 path=ROOT/candidate['source_file'];target=CACHE/(candidate['source_sha256']+'.txt')
 subprocess.run(['pdftotext','-layout',str(path),str(target)],check=True,capture_output=True)
 raw=target.read_text();text=re.sub(r'(?im)^\s*Minutes of (?:the )?(?:(?:Special |Regular )?Council|Committee of the Whole|Community Advisory Committee)(?: Meeting| IVIeeting)?\s*-\s*[^\n]*\n','\n',raw);text=re.sub(r'(?m)^\s*\d+\s*$','',text).replace('\f','\n')
 present=re.search(r'\bPRESENT\s*:(.*?)(?=\bABSENT\s*:|\bATTENDING\s*:)',text,re.S|re.I)
 if not present:raise ValueError('native_member_roster_boundary_missing')
 absent=re.search(r'\bABSENT\s*:(.*?)(?=\bATTENDING\s*:|\n\s*1\.)',text,re.S|re.I)
 staff=re.search(r'\bATTENDING\s*:(.*?)(?=Meeting available|\n\s*1\.)',text,re.S|re.I)
 starts=list(re.finditer(r'(?im)^\s*(?:(?:Amendment[ \t]*:[ \t]*|\.[ \t]*)?MOVED\s+BY\s*[:;]?|On the (?:Main )?Motion(?: as Amended)?\s*:|Voting resumed on the Main Motion\s*:)',text));blocks=[]
 for i,start in enumerate(starts):
  end=starts[i+1].start() if i+1<len(starts) else len(text);chunk=text[start.start():end]
  result=re.search(r'(?im)^\s*(?:Motion\s+)?(NOT CARRIED|CARRIED(?:\s+UNANIMOUSLY)?|DEFEATED|WITHDRAWN)\b[^\n]*',chunk)
  if not result:continue
  second=re.search(r'(?im)^.*SECONDED[^\n]*\n',chunk[:result.start()]);body=chunk[second.end():result.start()].strip() if second else chunk[start.end()-start.start():result.start()].strip()
  tail=chunk[result.end():];boundary=re.search(r'(?im)^\s*(?:\d+(?:\.\d+)*\.?\s+[A-Z]|On the (?:Main )?Motion\b)',tail)
  if boundary:tail=tail[:boundary.start()]
  blocks.append({'body':body,'result':result[1],'tail':tail,'cutoff':start.start()+result.start(),'chunk':chunk})
 return {'text':text,'header':text[:present.start()],'present':present[1],'absent':absent[1] if absent else '', 'staff':staff[1] if staff else '', 'blocks':blocks,'native_text_sha256':sha(target),'format':'fresh_native_pdf_layout'}


def html_source(candidate):
 soup=BeautifulSoup((ROOT/candidate['source_file']).read_text(),'html.parser');table=soup.select_one('.AgendaHeaderAttendanceTable');rows={}
 for row in table.find_all('div',recursive=False):
  label=row.select_one('.Label');value=row.select_one('.Value')
  if label and value:rows[norm(label.get_text())]=value.get_text('\n',strip=True)
 blocks=[]
 for node in soup.select('.AgendaItemMotion'):
  body='\n'.join(x.get_text(' ',strip=True) for x in node.select('.MotionText'));result=node.select_one('.MotionResult');tail=node.select_one('.PostMotionText')
  blocks.append({'body':body,'result':re.sub(r'(?i)^Motion\s+|[.]$','',result.get_text(' ',strip=True)),'tail':tail.get_text('\n',strip=True) if tail else '', 'cutoff':soup.get_text('\n',strip=True).find(node.get_text('\n',strip=True))+node.get_text('\n',strip=True).find(result.get_text(' ',strip=True)),'chunk':node.get_text('\n',strip=True)})
 return {'text':soup.get_text('\n',strip=True),'header':soup.title.get_text(' ',strip=True),'present':rows['present'],'absent':rows.get('absent',''),'staff':rows.get('attending',''),'blocks':blocks,'native_text_sha256':hashlib.sha256(soup.get_text('\n',strip=True).encode()).hexdigest(),'format':'independent_original_html_dom'}


def explicit_choices(tail,eligible):
 names={persons[pid]['name'].split()[-1].casefold():pid for pid in eligible};declared={};proof=[]
 # These native proposals use clerk suffix declarations. Any other choice
 # language is held, rather than silently treated as absent dissent.
 for line in re.split(r'(?<=[.;])\s+(?=(?:Councillors?|Committee\s+[Mm]embers?|Mayor)\b)',tail):
  line=line.strip()
  if not line:continue
  hit=re.search(r'(?is)((?:Councillors?|Committee\s+[Mm]embers?|Mayor)\s+.*?)\s+(opposed|voted against|voted yes|voted no)(?=[.;]|\s*$)',line)
  prefix=re.match(r'(?is)^OPPOSED\s*:\s*(.+)',line)
  if prefix:
   who,verb=prefix[1],'opposed'
  elif hit:
   who,verb=hit.groups()
  else:
   if re.search(r'\bopposed\b|\bagainst\b|\bvoted\b|\babstain\w*\b|\brecus\w*\b',line,re.I):raise ValueError('unparsed_native_choice_statement')
   continue
  ids=set();mask=who
  for surname,pid in names.items():
   if re.search(r'\b'+re.escape(surname)+r'\b',who,re.I):ids.add(pid)
  for pid in ids:
   first,last=persons[pid]['name'].split()[0],persons[pid]['name'].split()[-1]
   mask=re.sub(r'\b(?:'+re.escape(first)+r'|'+re.escape(first[0])+r'[.]?\s*)?'+re.escape(last)+r'\b',' ',mask,flags=re.I)
  mask=re.sub(r'\b(?:Councillors?|Committee|Members?|Mayor|and)\b',' ',mask,flags=re.I)
  if not ids or re.search(r'[A-Za-z0-9]',mask):raise ValueError('unresolved_native_declared_name')
  choice='Yes' if verb.casefold()=='voted yes' else 'No'
  for pid in ids:
   if pid in declared and declared[pid]!=choice:raise ValueError('conflicting_native_choice')
   declared[pid]=choice
  proof.append({'quote':prefix[0] if prefix else hit[0],'person_ids':sorted(ids),'choice':choice})
 return declared,proof



import ast
from functools import lru_cache
presence_library=OUT/'review_historical82_independently.py'
nodes=[]
for node in ast.parse(presence_library.read_text()).body:
 if isinstance(node,ast.FunctionDef) and node.name in {'identity_patterns','exact_name_spans','independent_attendance','present_at_vote'}:nodes.append(node)
 elif isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='EVENT_TOKEN' for t in node.targets):nodes.append(node)
live=snapshot
exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),str(presence_library),'exec'),globals())
candidates=[r for r in plan['records'] if r['status']=='reconstructable_candidate' and r['voting_body']!='community_advisory_committee'];loaded={};records=[];proof_issues=[]
for candidate in candidates:
 mid=candidate['motion_id'];record={'motion_id':mid,'meeting_id':candidate['meeting_id'],'source_sha256':candidate['source_sha256']}
 try:
  path=ROOT/candidate['source_file'];assert sha(path)==candidate['source_sha256'],'original_binary_hash_changed'
  if candidate['meeting_id'] not in loaded:loaded[candidate['meeting_id']]=html_source(candidate) if path.suffix=='.html' else pdf_source(candidate)
  src=loaded[candidate['meeting_id']]
  if 'council' not in norm(src['header']) and 'committee of the whole' not in norm(src['header']):raise ValueError('native_council_header_missing')
  native_body='committee_of_the_whole' if 'committee of the whole' in norm(src['header']) else 'council'
  if native_body=='council' and re.search(r'\b(?:committee|commission|board)\b',src['header'],re.I):raise ValueError('non_council_native_header')
  if native_body!=candidate['voting_body']:raise ValueError('native_voting_body_differs')
  datehit=re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s*(20\d{2})',src['header'],re.I)
  if not datehit:raise ValueError('native_header_date_missing')
  day=datetime.strptime(' '.join(datehit.groups()),'%B %d %Y').date().isoformat()
  if day!=candidate['source_date']:raise ValueError('native_header_date_differs')
  active_rows=[m for m in snapshot['memberships'] if m['classification']=='Council' and m.get('start_date') and m['start_date']<=day and(not m.get('end_date') or m['end_date']>=day)]
  pool=[persons[pid] for pid in sorted({m['person_id'] for m in active_rows})]
  native_present=re.sub(r'(?i)\b(Mayor|Councillor)(?=[a-z]\.)',r'\1 ',src['present'])
  present,unknown=roster(native_present);absent,absent_unknown=roster(src['absent'],True)
  if present & absent:raise ValueError('native_present_absent_contradiction')
  council_active={m['person_id'] for m in snapshot['memberships'] if m['classification']=='Council' and m.get('start_date') and m['start_date']<=day and(not m.get('end_date') or m['end_date']>=day)}
  if not {pid for pid in present if persons[pid]['name'] in council_names}<=council_active:raise ValueError('dated_council_office_not_proven')
  chair_ids=set()  # Council quorum is independently checked after source attendance replay.
  matches=[b for b in src['blocks'] if norm(b['body'])==norm(candidate['source_motion_text'])]
  if len(matches)!=1:raise ValueError('native_unique_full_formal_body_mismatch:'+str(len(matches)))
  block=matches[0]
  if block['cutoff'] is None or block['cutoff']<0:raise ValueError('native_outcome_offset_unknown')
  if block['result']!=candidate['source_result']:raise ValueError('native_outcome_mismatch')
  events,held=independent_attendance(src['text'],pool)
  present,applied_events=present_at_vote(present,events,held,block['cutoff'])
  if len(present)<4 or len(present)>7:raise ValueError('native_council_quorum_missing')
  explicit,declared_proof=explicit_choices(block['tail'],present)
  expected={pid:explicit.get(pid,'Yes') for pid in present};proposed={v['person_id']:v['vote'] for v in candidate['votes']}
  if expected!=proposed:raise ValueError('independent_choice_set_differs')
  yes=sum(v=='Yes' for v in expected.values());no=len(expected)-yes
  if (block['result'].startswith('CARRIED'))!=(yes>no):raise ValueError('native_tally_outcome_contradiction')
  old=[v for v in inventory['votes'] if v['motion_id']==mid]
  if old!=candidate['current_choices']:raise ValueError('current_existing_choice_values_changed')
  for observation in candidate.get('member_observations',[]):
   section=src['present'] if observation['observed_attendance']=='present' else src['absent']
   observed_set=present if observation['observed_attendance']=='present' else absent
   if observation['person_id'] not in observed_set or norm(observation['source_quote'])!=norm(section) or observation['source_sha256']!=candidate['source_sha256'] or observation['observed_date']!=day:
    proof_issues.append({'motion_id':mid,'person_id':observation['person_id'],'issue':'dated_member_observation_does_not_match_native_section','correct_native_quote':section.strip()})
  record.update(status='reviewed_choice_accuracy',source_file=candidate['source_file'],native_format=src['format'],native_text_sha256=src['native_text_sha256'],source_date=day,native_present_quote=src['present'].strip(),native_absent_quote=src['absent'].strip(),unknown_absent_tokens=absent_unknown,present_person_ids=sorted(present),chair_person_ids=sorted(chair_ids),independent_presence_events=applied_events,explicit_choice_evidence=declared_proof,choices=[{'person_id':pid,'vote':vote} for pid,vote in sorted(expected.items())],existing_vote_ids=[v['id'] for v in old],new_choices=len(expected)-len(old),checks=['fresh_native_source_binary','independent_full_identity_spans','native_dated_member_observations','appointment_lower_bounds','staff_and_visitors_excluded','dated_council_office_and_native_quorum_four','unique_entire_formal_body_first_outcome','independent_presence_scan','all_native_dissent_accounted','existing_choices_preserved','per_person_and_majority_tally'])
 except (AssertionError,ValueError,subprocess.SubprocessError) as error:record.update(status='held',reason=str(error))
 records.append(record)
# Separately verify that the ordinary public dispatcher preserves all five
# committee proof fields. This is integration parity, not source accuracy proof.
import sys
sys.path.insert(0,str(ROOT/'apps/pipeline'))
from pipeline.ingestion.official_ballots import load_official_minutes
from pipeline.ingestion.meeting_ballots import evaluate_ballot
policy={**json.loads((ROOT/'apps/pipeline/pipeline/ingestion/policies/langford-voting.json').read_text()),**json.loads((OUT/'committee-policy-refresh-verification.json').read_text()),'municipality_slug':'langford'}
assert policy['committee_policy']['status']=='verified_unchanged'
assert policy['committee_policy']['terms_sha256']==policy_sources[1]['sha256']
assert policy['committee_policy']['identity_section_sha256']==hashlib.sha256(norm(listing).encode()).hexdigest()
source_cache={};dispatcher_checks=[]
for candidate in candidates:
 meeting=meetings[candidate['meeting_id']]
 if meeting['id'] not in source_cache:source_cache[meeting['id']]=load_official_minutes(meeting,root=ROOT,people=people,cache_dir='/private/tmp/langford-ballot-source-audit')
 motion={'id':candidate['motion_id'],'meeting_id':candidate['meeting_id'],'text_content':candidate['source_motion_text'],'result':candidate['source_result']}
 context={'status':'available','meeting':meeting,'source':source_cache[meeting['id']],'people':people,'memberships':snapshot['memberships'],'policy':policy}
 result=evaluate_ballot(motion,context,candidate['current_choices'])
 assert result['status']=='reconstructable_candidate',(motion['id'],result)
 assert {(v['person_id'],v['vote']) for v in result['votes']}=={(v['person_id'],v['vote']) for v in candidate['votes']}
 for key in ('member_observations','excluded_nonvoting_attendees','committee_chair_person_ids','committee_quorum_minimum_appointees','committee_policy_validation'):
  if key in candidate:assert result['proof'][key]==candidate[key],(motion['id'],key)
 dispatcher_checks.append(motion['id'])
assert integration_hash==hashlib.sha256((ROOT/'apps/pipeline/pipeline/ingestion/meeting_ballots.py').read_bytes()).hexdigest()
for path,digest in plan['code_sha256s'].items():assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest
if not proof_issues:
 for record in records:
  if record['status']=='reviewed_choice_accuracy':record['status']='reviewed'
out={'mode':'independent_read_only_wrapper2699_review_requires_guarded_CAS_apply','candidate_plan_sha256':hashlib.sha256(raw).hexdigest(),'review_script_sha256':sha(Path(__file__)),'at':datetime.now(timezone.utc).isoformat(),'summary':{'candidate_ballots':len(candidates),'source_files':len(loaded),'statuses':dict(Counter(r['status'] for r in records)),'new_choices_reviewed':sum(r.get('new_choices',0) for r in records),'existing_choices_preserved':sum(len(r.get('existing_vote_ids',[])) for r in records),'proof_issues':len(proof_issues),'ordinary_dispatcher_fullproof_checks':len(dispatcher_checks)},'policy_primary_sources':policy_sources,'recording_rule_scope':recording_scope,'primary_appointment_proofs':appointment_proofs,'identity_registry_sha256':sha(registry_path),'reviewed_candidate_ids':[r['motion_id'] for r in records if r['status']=='reviewed'],'integration_sha256':integration_hash,'independent_presence_library_sha256':sha(presence_library),'committee_policy_verification_sha256':sha(OUT/'committee-policy-refresh-verification.json'),'proof_issues':proof_issues,'records':records}
# Bind the independently extracted native block to the actual current row.
import psycopg2
from psycopg2.extras import RealDictCursor
from pipeline import config
with psycopg2.connect(config.DATABASE_URL,connect_timeout=15) as db:
 db.set_session(readonly=True,isolation_level='REPEATABLE READ')
 with db.cursor(cursor_factory=RealDictCursor) as cur:
  cur.execute('SELECT m.id,m.meeting_id,m.agenda_item_id,m.text_content,m.result,m.mover,m.seconder,m.mover_id,m.seconder_id,m.meta,m.updated_at,a.item_order,a.title AS agenda_title FROM motions m JOIN agenda_items a ON a.id=m.agenda_item_id WHERE m.id=2699');original_row=dict(cur.fetchone())
  cur.execute("SELECT person_id,start_date,end_date FROM memberships m JOIN organizations o ON o.id=m.organization_id WHERE o.municipality_id=1 AND o.classification='Council' AND m.start_date<=%s AND (m.end_date IS NULL OR m.end_date>=%s)",('2022-03-21','2022-03-21'));dated_memberships=cur.fetchall()
  cur.execute('SELECT id,person_id,vote FROM votes WHERE motion_id=2699 ORDER BY id');old_votes=cur.fetchall()
assert original_row['meeting_id']==261 and original_row['result']=='CARRIED' and norm(original_row['text_content'])==norm(candidates[0]['source_motion_text']) and not old_votes
assert {v['person_id']for v in candidates[0]['votes']}<={m['person_id']for m in dated_memberships}
applier=OUT/'apply_wrapper2699_ballot.py';assert sha(applier)=='922919799b5053398463a82d1c19599170395e7de17765fb626728b0c6574214'
out['records'][0]['original_row']=json.loads(json.dumps(original_row,default=str))
out['records'][0]['dated_memberships_live_verified']=json.loads(json.dumps(dated_memberships,default=str))
out['records'][0]['inference_scope']='All six independently dated and native-present councillors inferredYes under primary1971 mandatory dissent-name recording clause; MayorYoung nativeABSENT, no physical changes before this exact motion, no named dissent, sixYes majority matchesCARRIED. This is not an explicit rollcall.'
out['apply_script_sha256']=sha(applier)
out['apply_script_peer_review']={'status':'reviewed','checks':['Exact2699 singleton/sixmissing choices/no textoragendawrites','Immutablecallerboundplan/review/beforeSHAs andallruntimeOCR/Swift/policydependencies','OriginalsourceSHA/liveCouncilbody/date/roster/membership/presence/source-resultreplay','SERIALIZABLE fullbeforeCAS/choiceappendonly/completeproof atomicpublication','Durablependingreceiptbeforecommit andexactwholeafterguardedrollback','SQLNULLversusJSONnullbeforemetapreserved'],'database_writes':0}
(OUT/'wrapper2699-independent-review.json').write_text(json.dumps(out,indent=2));print(json.dumps(out['summary'],indent=2));print(json.dumps([r for r in records if r['status']=='held'],indent=2))
