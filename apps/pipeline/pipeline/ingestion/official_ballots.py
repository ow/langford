"""Official source ballot validation shared by ordinary ingestion and audits.

No model output, cached Markdown, attendance-table shortcut, or absent dissent
alone proves a ballot. Original sources, each voter and policy applicability are
validated before any inferred choice is returned. Functions do not write DB.
"""
from collections import defaultdict
from datetime import datetime
import hashlib
import re
import subprocess
from pathlib import Path

from .vote_evidence import minutes_motion_blocks, normalize_text, named_votes, outcome_family
from .ballot_reconstruction import validate_roster_entries, physical_presence_events, voters_before_vote


def _surname_index(people):
    surnames=defaultdict(list)
    for person in people:
        parts=normalize_text(person['name']).split()
        if len(parts)>=2 and len(parts[-1])>=3:
            surnames[parts[-1]].append(person)
    return surnames

def resolve_names(text, people):
 surnames=_surname_index(people)
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
   body='\n'.join(item.get_text(' ',strip=True) for item in node.select('.MotionText'))
   parts.extend(['MOVED BY: '+text('.MovedBy .Value'),'SECONDED: '+text('.SecondedBy .Value'),body,text('.MotionResult')])
   if post:parts.append(post)
   return
  if 'AgendaItemMinutes' in classes:
   parts.append(node.get_text(' ',strip=True));return
  for child in node.children:walk(child)
 body=soup.select_one('.AgendaItems')
 if not body:raise ValueError('official_html_motion_structure_missing')
 walk(body)
 return '\n'.join(parts)

def _load_official_minutes(meeting, *, root, people, cache_dir):
 ROOT=Path(root)
 CACHE=Path(cache_dir)
 CACHE.mkdir(parents=True,exist_ok=True)
 surnames=_surname_index(people)
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
 # Catalog classification is not proof: mislabeled Committee minutes must not
 # silently inherit Council voting scope. Retain native header before cleanup.
 header=re.split(r'\bPRESENT\b',text[:1400],maxsplit=1,flags=re.I)[0]
 source_classification='Committee of the Whole' if re.search(r'committee\s+of\s+the\s+whole|\bCOTW\b',header,re.I) else 'Committee' if re.search(r'\bcommittee\b|\bcommission\b',header,re.I) else 'Council' if re.search(r'\bcouncil\b',header,re.I) else None
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
  resolved,_=resolve_names(initial+'. '+surname, people)
  if len(resolved)!=1:unknown.append(initial+'. '+surname)
 date_match=re.search(r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(20\d{2})\b',clean[:1400],re.I)
 local_date=datetime.strptime(' '.join(date_match.groups()),'%B %d %Y').date().isoformat() if date_match else None
 blocks=list(minutes_motion_blocks(clean));index=defaultdict(list)
 for block in blocks:index[normalize_text(block['motion_text'])].append(block)
 sidecar=Path(str(path)+'.url');url=sidecar.read_text().strip() if sidecar.exists() else meeting.get('minutes_url')
 return {'text':clean,'source_classification':source_classification,'source_header':header,'source_format':source_format,'source_file':str(path.relative_to(ROOT)),'source_url':url,'source_sha256':digest,'local_date':local_date,'stored_date':meeting['meeting_date'],'present':roster,'roster_quote':roster_quote.strip(),'roster_unknown':unknown,'ambiguous_names':ambiguous,'blocks':blocks,'index':index}

def event_timeline(source, memberships):
 known={p['id']:p for p in source['present']}
 for membership in memberships:
  if membership['classification']=='Council' and membership['start_date'] and source['local_date'] and membership['start_date']<=source['local_date'] and (not membership['end_date'] or membership['end_date']>=source['local_date']):
   if membership['person_id'] not in known:
    known[membership['person_id']]={'id':membership['person_id'],'name':membership['name']}
 return physical_presence_events(source['text'],list(known.values()))

def inspect_motion(motion, source, *, meeting, people, memberships, policy):
 result={'motion_id':motion['id'],'meeting_id':motion['meeting_id'],'result':motion['result']}
 if motion['meeting_id']!=meeting['id']:return {**result,'status':'source_meeting_mismatch'}
 if source.get('error'):return {**result,'status':source['error']}
 source_body=source.get('source_classification')
 catalog_cotw=bool(re.search(r'committee\s+of\s+the\s+whole|\bCOTW\b',meeting.get('title','')+' '+meeting.get('archive_path',''),re.I))
 if source_body=='Committee of the Whole':
  if not catalog_cotw:return {**result,'status':'source_catalog_voting_body_mismatch'}
  if not policy.get('committee_of_the_whole_scope'):return {**result,'status':'source_committee_membership_rules_need_validation'}
  voting_body='committee_of_the_whole'
 elif source_body=='Council':
  if catalog_cotw:return {**result,'status':'source_catalog_voting_body_mismatch'}
  voting_body='council'
 else:return {**result,'status':'source_committee_membership_rules_need_validation' if source_body=='Committee' else 'source_council_scope_not_proven'}
 candidates=source['index'].get(normalize_text(motion['text_content']),[])
 if len(candidates)!=1:return {**result,'status':'source_motion_not_exact_or_ambiguous','exact_candidates':len(candidates)}
 block=candidates[0]
 if outcome_family(motion['result'])!=outcome_family(block['result']):return {**result,'status':'outcome_conflict'}
 if outcome_family(block['result']) not in ('passed','failed'):return {**result,'status':'not_a_yes_no_decision'}
 if source['roster_unknown'] or source['ambiguous_names']:return {**result,'status':'roster_unknown_names','unknown':source['roster_unknown']+source['ambiguous_names']}
 present={p['id'] for p in source['present']}
 if not 3<=len(present)<=7:return {**result,'status':'roster_size_or_non_council_committee'}
 if meeting['classification']!='Council' and voting_body!='committee_of_the_whole':return {**result,'status':'committee_membership_rules_need_validation'}
 local_date=source['local_date']
 if not local_date:return {**result,'status':'source_date_unknown'}
 # Legacy catalog dates may be one UTC day ahead; an unrelated minutes file
 # must never supply a ballot merely because a generic motion text matches.
 if abs((datetime.fromisoformat(local_date)-datetime.fromisoformat(meeting['meeting_date'])).days)>1:
  return {**result,'status':'source_meeting_date_mismatch'}
 if meeting.get('municipality_slug')!='langford' or policy.get('municipality_slug')!='langford':
  return {**result,'status':'municipality_recording_rule_not_validated'}
 if 'UNANIMOUS' not in block['result'] or voting_body=='committee_of_the_whole':
  if policy.get('policy_status')!='verified_unchanged':
   return {**result,'status':policy.get('policy_status','recording_rule_not_refreshed')}
  if not policy.get('enabled_from','9999')<=local_date<=policy.get('enabled_through',''):
   return {**result,'status':'recording_rule_date_not_validated'}

 # Bylaw1971 original section38 / consolidated section44 effective Oct18,2021.
 if local_date<'2021-10-18' and 'UNANIMOUS' not in block['result']:return {**result,'status':'historical_recording_convention_not_yet_verified'}
 if 'presence_events' not in source:
  source['presence_events'],source['unknown_presence_events']=event_timeline(source,memberships)
 events,unknown=source['presence_events'],source['unknown_presence_events']
 position=source['text'].find(block['source_block'])
 if position<0:return {**result,'status':'source_offset_unknown'}
 position += block['source_block'].find(block['outcome_quote'])
 earlier_unknown=[event for event in unknown if event['offset']<position]
 if earlier_unknown:return {**result,'status':'unparsed_presence_event','events':earlier_unknown[:5]}
 present,initial_adjustments=voters_before_vote(present,events,position)
 if present is None:return {**result,'status':'initial_presence_unknown','events':initial_adjustments}
 # Membership crosscheck when database has dated council service, source date wins.
 memberships=[m for m in memberships if m['classification']=='Council' and m['start_date'] and m['start_date']<=local_date and(not m['end_date'] or m['end_date']>=local_date)]
 ids={m['person_id'] for m in memberships}
 if not ids:return {**result,'status':'dated_council_membership_unavailable'}
 if not present<=ids:return {**result,'status':'council_membership_mismatch','present':sorted(present),'active_members':sorted(ids)}
 if len(present)<4:return {**result,'status':'possible_no_quorum'}
 explicit=named_votes(block,[p['name'] for p in people])
 if 'UNANIMOUS' in block['result'] and any(v['vote']!='Yes' for v in explicit):
  return {**result,'status':'unanimous_result_conflicts_with_named_choice'}
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
  votes.append({'person_id':pid,'person_name':next(p['name'] for p in people if p['id']==pid),'vote':v['vote'] if v else 'Yes','evidence':'explicit_named' if v else ('inferred_explicit_unanimity' if 'UNANIMOUS' in block['result'] else 'inferred_official_dissent_recording_rule'),'source_quote':v['source_quote'] if v else block['outcome_quote']})
 yes=sum(v['vote']=='Yes' for v in votes);no=sum(v['vote']=='No' for v in votes)
 if (outcome_family(block['result'])=='passed')!=(yes>no):return {**result,'status':'reconstructed_tally_conflicts_with_outcome','yes':yes,'no':no}
 # Special supermajority decisions need separate threshold verification.
 if re.search(r'extend.*meeting|reconsider|sustain.*chair|presiding|appeal.*chair|chair.*appeal|ruling.*chair',block['motion_text'],re.I):return {**result,'status':'special_voting_threshold_needs_validation'}
 return {**result,'status':'reconstructable_candidate','source_classification':source_body,'voting_body':voting_body,'outcome_role':'committee_guidance_or_recommendation' if voting_body=='committee_of_the_whole' else 'council_decision','scope_basis':policy.get('committee_of_the_whole_scope') if voting_body=='committee_of_the_whole' else 'official_council_header_and_dated_council_membership','source_result':block['result'],'votes':votes,'yes':yes,'no':no,'source_file':source['source_file'],'source_format':source['source_format'],'source_url':source['source_url'],'source_sha256':source['source_sha256'],'source_date':local_date,'stored_date':source['stored_date'],'roster_quote':source['roster_quote'],'membership_evidence':'dated_db_council_membership','initial_arrival_adjustments':initial_adjustments,'presence_events':[e for e in events if e['offset']<position],'source_motion_text':block['motion_text'],'source_block':block['source_block'],'recording_rule':'Langford1971 section38(original)/44(consolidated), CommunityCharter123; proposed inferred choices, not explicit rollcall'}


def load_official_minutes(meeting, *, root, people, cache_dir):
    """Return a documentary hold when native source extraction is unavailable."""
    try:
        return _load_official_minutes(meeting, root=root, people=people, cache_dir=cache_dir)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        return {'error': 'official_minutes_extraction_unavailable', 'error_type': type(error).__name__}


def complete_ballot_proof(candidate, policy):
    keys = ('source_file', 'source_format', 'source_url', 'source_sha256', 'source_date',
            'stored_date', 'source_result', 'source_motion_text', 'source_block',
            'roster_quote', 'membership_evidence', 'presence_events',
            'initial_arrival_adjustments', 'votes', 'source_classification',
            'voting_body', 'scope_basis', 'outcome_role')
    proof = {key: candidate[key] for key in keys}
    unanimous = 'UNANIMOUS' in candidate['source_result']
    proof.update({
        'rule_id': 'explicit_unanimity' if unanimous else policy['rule_id'],
        'bylaw_url': policy.get('bylaw_url'),
        'bylaw_sha256': policy.get('bylaw_sha256'),
        'policy_checked_as_of': policy.get('validated_as_of'),
        'policy_status': policy.get('policy_status'),
        'method': 'documentary_reconstruction_not_explicit_rollcall',
        'basis': 'explicit_unanimity_with_per_vote_roster' if unanimous else 'validated_dissent_recording_rule_with_per_vote_roster',
        'choice_provenance': {f"person_{v['person_id']}": v['evidence'] for v in candidate['votes']},
    })
    return proof
