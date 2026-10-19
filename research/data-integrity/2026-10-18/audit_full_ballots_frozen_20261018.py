"""Read-only full-source ballot reconstruction audit; no model calls or DB writes.

Uses original PDF layout, official present roster, ordered departure/return notes,
exact motion matching and the cited Langford dissent-recording convention.
"""
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib,json,re,subprocess
from pathlib import Path
from pipeline.ingestion.vote_evidence import minutes_motion_blocks,normalize_text,named_votes,outcome_family
from pipeline.ingestion.ballot_reconstruction import validate_roster_entries,physical_presence_events,voters_before_vote

ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
CACHE=Path('/private/tmp/langford-ballot-source-audit');CACHE.mkdir(exist_ok=True)
data=json.loads((OUT/'ballot-source-snapshot.json').read_text())
people=json.loads((OUT/'vote-people-snapshot.json').read_text())
meetings={m['id']:m for m in data['meetings']}
surnames=defaultdict(list)
for p in people:
 parts=normalize_text(p['name']).split()
 if len(parts)>=2 and len(parts[-1])>=3:surnames[parts[-1]].append(p)


def resolve_names(text):
 found=[];ambiguous=[]
 for surname,ps in surnames.items():
  if re.search(r'\b'+re.escape(surname)+r'\b',normalize_text(text)):
   candidates=ps
   initial=re.search(r'\b([A-Z])\.\s*'+re.escape(surname)+r'\b',text,re.I)
   if initial and len(candidates)>1:candidates=[p for p in candidates if p['name'][0].casefold()==initial[1].casefold()]
   if len(candidates)==1:found.append(candidates[0])
   else:ambiguous.append(surname)
 return found,ambiguous


def html_minutes_text(path):
 from bs4 import BeautifulSoup,Tag
 soup=BeautifulSoup(path.read_text(),'html.parser')
 title=soup.title.get_text(' ',strip=True) if soup.title else ''
 table=soup.select_one('.AgendaHeaderAttendanceTable')
 if not table:raise ValueError('official_html_attendance_structure_missing')
 parts=[title]
 for row in table.find_all('div',recursive=False):
  label=row.select_one('.Label');value=row.select_one('.Value')
  if label and value:
   parts.append(label.get_text(' ',strip=True))
   entries=value.select('li')
   parts.extend(e.get_text(' ',strip=True) for e in entries)
   if not entries:parts.append(value.get_text(' ',strip=True))
 def walk(node):
  if not isinstance(node,Tag):return
  classes=set(node.get('class',[]))
  if 'AgendaItemTitleRow' in classes:
   counter=node.select_one('.AgendaItemCounter');title=node.select_one('.AgendaItemTitle')
   parts.append((counter.get_text(' ',strip=True) if counter else '')+' '+(title.get_text(' ',strip=True) if title else ''));return
  if 'AgendaItemMotion' in classes:
   def text(selector):
    item=node.select_one(selector);return item.get_text(' ',strip=True) if item else ''
   pre=text('.PreMotionText');post=text('.PostMotionText')
   if pre:parts.append(pre)
   # Structural delimiters mark an official formal motion even when the clerk
   # omitted names (allowed by the procedure bylaw); no names are invented.
   parts.extend(['MOVED BY: '+text('.MovedBy .Value'),'SECONDED: '+text('.SecondedBy .Value'),text('.MotionText'),text('.MotionResult')])
   if post:parts.append(post)
   return
  if 'AgendaItemMinutes' in classes:
   parts.append(node.get_text(' ',strip=True));return
  for child in node.children:walk(child)
 body=soup.select_one('.AgendaItems')
 if not body:raise ValueError('official_html_motion_structure_missing')
 walk(body)
 return '\n'.join(parts)


def source_for(meeting):
 folder=ROOT/(meeting['archive_path'] or 'missing')
 files=list((folder/'Minutes').glob('*.pdf'))
 if files:
  signed=[f for f in files if 'signed' in f.name.lower()]
  preferred=signed or [f for f in files if f.name=='Minutes.pdf'] or files
  if len(preferred)!=1:return {'error':'ambiguous_original_minutes_pdf','files':[str(f.relative_to(ROOT)) for f in preferred]}
  path=preferred[0];digest=hashlib.sha256(path.read_bytes()).hexdigest();cache=CACHE/(digest+'.txt')
  if not cache.exists():
   subprocess.run(['pdftotext','-layout',str(path),str(cache)],check=True,timeout=40,capture_output=True)
  text=cache.read_text(errors='replace');source_format='original_pdf_layout'
 else:
  html=list((folder/'Minutes').glob('*.html'))
  if len(html)!=1:return {'error':'no_original_minutes_pdf_or_unique_official_html'}
  path=html[0];digest=hashlib.sha256(path.read_bytes()).hexdigest()
  try:text=html_minutes_text(path)
  except ValueError as error:return {'error':str(error)}
  source_format='official_html_structural'
 if len(text.strip())<100:return {'error':'pdf_requires_ocr'}
 # Remove repeated page headers and footer-only page numbers, preserving order.
 clean=re.sub(r'(?im)^\s*Minutes of[^\n]*\n','\n',text)
 clean=re.sub(r'(?m)^\s*\d+\s*$','',clean).replace('\f','\n')
 # Only roster in the PRESENT block, never staff/absent/all names from header.
 present=re.search(r'\bPRESENT\s*:',clean,re.I) or re.search(r'\bPRESENT\b',clean,re.I)
 if not present:return {'error':'present_header_not_extracted','source_file':str(path.relative_to(ROOT))}
 tail=clean[present.end():]
 end=re.search(r'\b(?:ATTENDING|ABSENT|REGRETS)\s*:?|\n\s*(?:1\.|CALL TO ORDER|TERRITORIAL)',tail,re.I)
 if not end:return {'error':'present_header_boundary_unknown'}
 roster_quote=tail[:end.start()]
 roster,ambiguous=validate_roster_entries(roster_quote,people)
 # Retain unknown name-looking role mentions for audit; avoid quietly dropping a voter.
 unknown=[]
 role_names=re.findall(r'\b(?:Mayor|Councillors?|Committee [Mm]ember|Members?)\s*:?\s*((?:[A-Z]\.\s*)?[A-Z][a-zA-Z-]+)',roster_quote)
 for token in role_names:
  if not any(normalize_text(token).split()[-1]==normalize_text(p['name']).split()[-1] for p in roster):unknown.append(token)
 # Legacy roster commas have unprefixed initials; every initial/surname must resolve.
 for initial,surname in re.findall(r'\b([A-Z])\.\s*([A-Z][A-Za-z-]+)',roster_quote):
  matches=surnames.get(normalize_text(surname),[])
  resolved,_=resolve_names(initial+'. '+surname)
  if len(resolved)!=1:unknown.append(initial+'. '+surname)
 date_match=re.search(r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(20\d{2})\b',clean[:1400],re.I)
 local_date=datetime.strptime(' '.join(date_match.groups()),'%B %d %Y').date().isoformat() if date_match else None
 blocks=list(minutes_motion_blocks(clean));index=defaultdict(list)
 for block in blocks:index[normalize_text(block['motion_text'])].append(block)
 sidecar=Path(str(path)+'.url');url=sidecar.read_text().strip() if sidecar.exists() else meeting.get('minutes_url')
 return {'text':clean,'source_format':source_format,'source_file':str(path.relative_to(ROOT)),'source_url':url,'source_sha256':digest,'local_date':local_date,'stored_date':meeting['meeting_date'],'present':roster,'roster_quote':roster_quote.strip(),'roster_unknown':unknown,'ambiguous_names':ambiguous,'blocks':blocks,'index':index}


def event_timeline(source,roster_ids):
 known={p['id']:p for p in source['present']}
 for membership in data['memberships']:
  if membership['classification']=='Council' and membership['start_date'] and source['local_date'] and membership['start_date']<=source['local_date'] and (not membership['end_date'] or membership['end_date']>=source['local_date']):
   if membership['person_id'] not in known:
    known[membership['person_id']]={'id':membership['person_id'],'name':membership['name']}
 return physical_presence_events(source['text'],list(known.values()))


def inspect_motion(motion,source):
 result={'motion_id':motion['id'],'meeting_id':motion['meeting_id'],'result':motion['result']}
 if source.get('error'):return {**result,'status':source['error']}
 candidates=source['index'].get(normalize_text(motion['text_content']),[])
 if len(candidates)!=1:return {**result,'status':'source_motion_not_exact_or_ambiguous','exact_candidates':len(candidates)}
 block=candidates[0]
 if outcome_family(motion['result'])!=outcome_family(block['result']):return {**result,'status':'outcome_conflict'}
 if outcome_family(block['result']) not in ('passed','failed'):return {**result,'status':'not_a_yes_no_decision'}
 if source['roster_unknown'] or source['ambiguous_names']:return {**result,'status':'roster_unknown_names','unknown':source['roster_unknown']+source['ambiguous_names']}
 present={p['id'] for p in source['present']}
 if not 3<=len(present)<=7:return {**result,'status':'roster_size_or_non_council_committee'}
 meeting=meetings[motion['meeting_id']]
 if meeting['classification']!='Council':return {**result,'status':'committee_membership_rules_need_validation'}
 local_date=source['local_date']
 if not local_date:return {**result,'status':'source_date_unknown'}
 # Bylaw1971 original section38 / consolidated section44 effective Oct18,2021.
 if local_date<'2021-10-18' and 'UNANIMOUS' not in block['result']:return {**result,'status':'historical_recording_convention_not_yet_verified'}
 if 'presence_events' not in source:
  source['presence_events'],source['unknown_presence_events']=event_timeline(source,present)
 events,unknown=source['presence_events'],source['unknown_presence_events']
 position=source['text'].find(block['source_block'])
 if position<0:return {**result,'status':'source_offset_unknown'}
 position += block['source_block'].find(block['outcome_quote'])
 earlier_unknown=[event for event in unknown if event['offset']<position]
 if earlier_unknown:return {**result,'status':'unparsed_presence_event','events':earlier_unknown[:5]}
 present,initial_adjustments=voters_before_vote(present,events,position)
 if present is None:return {**result,'status':'initial_presence_unknown','events':initial_adjustments}
 # Membership crosscheck when database has dated council service, source date wins.
 memberships=[m for m in data['memberships'] if m['classification']=='Council' and m['start_date'] and m['start_date']<=local_date and(not m['end_date'] or m['end_date']>=local_date)]
 ids={m['person_id'] for m in memberships}
 if ids and not present<=ids:return {**result,'status':'council_membership_mismatch','present':sorted(present),'active_members':sorted(ids)}
 if len(present)<4:return {**result,'status':'possible_no_quorum'}
 explicit=named_votes(block,[p['name'] for p in people])
 named={next(p['id'] for p in people if p['name']==v['person_name']):v for v in explicit}
 if any(p not in present for p in named):return {**result,'status':'named_choice_voter_not_present'}
 # Do not treat unresolved OPPOSED lines or nonstandard source vote notation as none.
 after=block['after_outcome'];head='\n'.join(after.splitlines()[:9])
 opposition=re.search(r'(?im)^\s*(?:OPPOSED\s*:|(?:Mayor|Councillor|Councillors)\s+[^\n]{0,160}\bopposed\b)',head)
 if opposition and not any(v['vote']=='No' for v in explicit):return {**result,'status':'unresolved_dissent_names'}
 if any(v['vote'] in ('Abstain','Recused') for v in explicit):return {**result,'status':'special_vote_or_recusal_needs_scope'}
 votes=[]
 for pid in sorted(present):
  v=named.get(pid)
  votes.append({'person_id':pid,'person_name':next(p['name'] for p in people if p['id']==pid),'vote':v['vote'] if v else 'Yes','evidence':'explicit_named' if v else 'inferred_official_dissent_recording_rule','source_quote':v['source_quote'] if v else block['outcome_quote']})
 yes=sum(v['vote']=='Yes' for v in votes);no=sum(v['vote']=='No' for v in votes)
 if (outcome_family(block['result'])=='passed')!=(yes>no):return {**result,'status':'reconstructed_tally_conflicts_with_outcome','yes':yes,'no':no}
 # Special supermajority decisions need separate threshold verification.
 if re.search(r'extend.*meeting|reconsider|sustain.*chair|presiding|appeal.*chair|chair.*appeal|ruling.*chair',block['motion_text'],re.I):return {**result,'status':'special_voting_threshold_needs_validation'}
 return {**result,'status':'reconstructable_candidate','source_result':block['result'],'votes':votes,'yes':yes,'no':no,'source_file':source['source_file'],'source_format':source['source_format'],'source_url':source['source_url'],'source_sha256':source['source_sha256'],'source_date':local_date,'stored_date':source['stored_date'],'roster_quote':source['roster_quote'],'membership_evidence':'dated_db_council_membership' if ids else 'official_council_present_roster','initial_arrival_adjustments':initial_adjustments,'presence_events':[e for e in events if e['offset']<position],'source_motion_text':block['motion_text'],'source_block':block['source_block'],'recording_rule':'Langford1971 section38(original)/44(consolidated), CommunityCharter123; proposed inferred choices, not explicit rollcall'}


def main():
 selected=[m for m in data['motions'] if m['result']]
 ids={m['meeting_id'] for m in selected}
 with ThreadPoolExecutor(max_workers=4) as pool:
  sources=dict(zip(sorted(ids),pool.map(source_for,[meetings[i] for i in sorted(ids)])))
 results=[inspect_motion(m,sources[m['meeting_id']]) for m in selected]
 summary={'audit_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'proposal_status':'requires_independent_review_before_apply','parser_sha256':hashlib.sha256((ROOT/'apps/pipeline/pipeline/ingestion/ballot_reconstruction.py').read_bytes()).hexdigest(),'motion_gate_sha256':hashlib.sha256((ROOT/'apps/pipeline/pipeline/ingestion/vote_evidence.py').read_bytes()).hexdigest(),'resulted_motions':len(selected),'source_meetings':len(sources),'sources':dict(Counter(s.get('error','pdf_available') for s in sources.values())),'classification':dict(Counter(r['status'] for r in results)),'proposed_vote_rows':sum(len(r.get('votes',[])) for r in results),'by_year':{y:dict(Counter(r['status'] for r in results if meetings[r['meeting_id']]['meeting_date'].startswith(y))) for y in sorted({m['meeting_date'][:4] for m in meetings.values()})}}
 (OUT/'full-ballot-audit.json').write_text(json.dumps({'summary':summary,'motions':results},indent=2));print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':main()
