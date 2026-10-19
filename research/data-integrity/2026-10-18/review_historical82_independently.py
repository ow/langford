"""Independent read-only machine review of every remaining documentary ballot.

No production vote/presence helpers, fuzzy matching, AI calls or database writes.
Fresh native PDF extraction, exact formal body/outcome, exhaustive roster-token
accounting, independently replayed attendance, full dissent-name accounting and
current identity/membership/choice checks. Any uncertainty is a per-motion hold.
"""
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,date,timezone
import hashlib,json,re,subprocess
from functools import lru_cache
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
CACHE=Path('/private/tmp/independent-full-ballot-review');CACHE.mkdir(exist_ok=True)
plan_bytes=(OUT/'historical-ballot-current-plan.json').read_bytes();plan=json.loads(plan_bytes)
snapshot=json.loads((OUT/'ballot-source-current-snapshot.json').read_text())
people_data=json.loads((OUT/'vote-people-current-snapshot.json').read_text())
people=people_data.get('people',[]) if isinstance(people_data,dict) else people_data
vote_data=json.loads((OUT/'full-current-vote-inventory.json').read_text())
live={**snapshot,'people':people,'votes':vote_data['votes']}
persons={p['id']:p for p in people}
meetings={m['id']:m for m in live['meetings']};motions={m['id']:m for m in live['motions']}
existing=defaultdict(list)
for v in live['votes']:existing[v['motion_id']].append(v)
rule=json.loads((OUT/'ballot-recording-rule.json').read_text())


def norm(text):return re.sub(r'[^a-z0-9]+',' ',text.casefold()).strip()


def family(result):
    value=norm(result or '')
    if value=='not carried' or value.startswith('defeated'):return 'failed'
    if re.match(r'^(?:carried|passed|adopted)(?: |$)',value):return 'passed'
    return None


def active_people(day):
    ids={m['person_id'] for m in live['memberships'] if m.get('classification')=='Council' and m['start_date'] and m['start_date']<=day and (not m['end_date'] or m['end_date']>=day)}
    return [persons[i] for i in sorted(ids) if i in persons]


@lru_cache(maxsize=None)
def identity_patterns(pid,allow_surnames):
    words=persons[pid]['name'].split()
    if len(words)<2:return ()
    first,last=words[0],words[-1]
    forms=[re.escape(persons[pid]['name']),re.escape(first[0])+r'(?:[.,]\s*|\s+)'+re.escape(last)]
    if allow_surnames:forms.append(re.escape(last))
    return tuple(re.compile(r'(?<![A-Za-z])(?:'+p+r')(?![A-Za-z])',re.I)for p in forms)


def exact_name_spans(text,pool,allow_surnames=False):
    matches=[]
    for p in pool:
        for pattern in identity_patterns(p['id'],allow_surnames):
            for m in pattern.finditer(text):
                matches.append((m.start(),m.end(),p['id']))
    # Prefer a whole name over its nested surname; the same span may not identify
    # two people. Unlike the pipeline parser, unmatched tokens remain evidence.
    matches.sort(key=lambda m:(m[0],-(m[1]-m[0])))
    chosen=[];ambiguous=[]
    for item in matches:
        collisions=[c for c in chosen if item[0]<c[1] and c[0]<item[1]]
        if collisions:
            if any(c[2]!=item[2] for c in collisions):ambiguous.append(item)
            continue
        chosen.append(item)
    return chosen,ambiguous


def roster_from_native(text,pool):
    start=re.search(r'\bPRESENT\s*:',text,re.I)
    if not start:raise ValueError('native_present_marker_missing')
    tail=text[start.end():]
    end=re.search(r'\b(?:ATTENDING|ABSENT|REGRETS)\s*:?|\n\s*(?:1\.|CALL TO ORDER|TERRITORIAL)',tail,re.I)
    if not end:raise ValueError('native_present_boundary_missing')
    quote=tail[:end.start()].strip()
    spans,ambiguous=exact_name_spans(quote,pool)
    if ambiguous:raise ValueError('native_present_name_ambiguous')
    mask=list(quote)
    for a,b,pid in spans:mask[a:b]=' '*(b-a)
    residue=''.join(mask)
    residue=re.sub(r'\b(?:acting|mayor|councillors?|committee|members?|chair|and|present|via|electronic|electronically|telephone|teleconference|video|conference|zoom|in|person|by|phone|participating|remote|remotely)\b',' ',residue,flags=re.I)
    remaining=re.findall(r'[A-Za-z0-9]+',residue)
    if remaining:raise ValueError('native_roster_unaccounted_tokens:'+','.join(sorted(set(remaining))))
    ids=[s[2] for s in spans]
    if len(ids)!=len(set(ids)):raise ValueError('native_roster_repeated_identity')
    if not 4<=len(ids)<=7:raise ValueError('native_roster_quorum_or_size')
    return set(ids),quote


OUTCOME=re.compile(r'(?im)^[ \t]*(?:Motion[ \t]+)?(NOT CARRIED|CARRIED(?:[ \t]+UNANIMOUSLY)?|DEFEATED|WITHDRAWN|TABLED)\b[^\n]*')


def formal_decisions(text):
    starts=list(re.finditer(r'(?im)^[ \t]*(?:MOVED[ \t]+BY[ \t]*[:;]?|On the (?:Main )?Motion(?: as Amended)?[ \t]*:)',text))
    blocks=[]
    for i,start in enumerate(starts):
        stop=starts[i+1].start()if i+1<len(starts)else len(text)
        block=text[start.start():stop];result=OUTCOME.search(block)
        if not result:continue
        body=block[:result.start()]
        second=re.search(r'(?im)^.*SECONDED[^\n]*\n',body)
        if second:body=body[second.end():]
        else:body=body[start.end()-start.start():]
        declaration=re.search(r'(?im)^\s*(?:OPPOSED\s*:|(?:Mayor|Councillors?)\s+[^\n]*\b(?:opposed|voted against)\b)',body)
        pre=body[declaration.start():]if declaration else ''
        if declaration:body=body[:declaration.start()]
        blocks.append({'body':body.strip(),'result':result[1].upper(),'outcome_quote':result[0].strip(),'vote_offset':start.start()+result.start(),'start':start.start(),'stop':stop,'tail':pre+'\n'+block[result.end():],'block':block.strip()})
    return blocks


EVENT_TOKEN=re.compile(r'\b(?:lost\s+(?:the\s+)?connection|disconnected|reconnected|stepped\s+out|conflict\s+of\s+interest|recused|excused|withdrew|left|leaving|departed|arrived|joined|rejoined|returned|entered|exited|was\s+absent|was\s+not\s+present|not\s+in\s+attendance)\b',re.I)


def independent_attendance(text,pool):
    events=[];holds=[]
    for token in EVENT_TOKEN.finditer(text):
        before=text[:token.start()].split('\n\n')[-1]
        after=text[token.end():].split('\n\n')[0]
        verb=' '.join(token.group().lower().split())
        if verb in {'conflict of interest','excused','recused'} and re.search(r'\bleft\s+(?:the\s+)?(?:meeting|room|chambers)\b',after,re.I):continue
        if verb=='withdrew' and re.match(r'\s+(?:his|her|their|the|a)\s+(?:amending\s+)?motion\b',after,re.I):continue
        if verb=='left' and re.match(r'\s+(?:the\s+)?decision\b',after,re.I):continue
        if verb=='returned' and re.match(r'\s+to\s+(?:the\s+)?discussion\b',after,re.I):continue
        # Isolate an actor statement, permitting initials (whose uppercase-dot
        # is not a sentence end) and a compound exit/return with one subject.
        pieces=re.split(r'(?<![A-Z])[.;!?]\s+(?=[A-Z])|\n\s*\n',before)
        actor=pieces[-1]
        actor_spans,ambiguous=exact_name_spans(actor,pool,allow_surnames=True)
        if not actor_spans and re.search(r'\bThe Mayor\s*$',actor,re.I):
            datehit=re.search(r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(20\d{2})',text[:1600],re.I)
            day=datetime.strptime(' '.join(datehit.groups()),'%B %d %Y').date().isoformat() if datehit else ''
            mayorids={m['person_id']for m in live['memberships']if m.get('classification')=='Council' and m.get('role')=='Mayor' and m.get('start_date') and m['start_date']<=day and(not m.get('end_date')or m['end_date']>=day)}
            rolematches=[p for p in pool if p['id']in mayorids and any(re.search(r'\bMayor\s+'+pat.pattern,text[:1600],re.I)for pat in identity_patterns(p['id'],False))]
            if len(rolematches)==1:actor_spans=[(0,len(actor),rolematches[0]['id'])]
        if not actor_spans:
            # A named councillor unknown to the canonical roster is uncertainty,
            # not an invisible attendance event. Unrelated narrative is ignored.
            if re.search(r'\b(?:Mayor|Councillors?)\b',actor,re.I):
                holds.append({'offset':token.start(),'reason':'unresolved_physical_actor','quote':actor+token.group()+after.split('\n')[0]})
            continue
        ids={s[2] for s in actor_spans}
        quote=actor+token.group()+after.split('\n')[0]
        if ambiguous or len(ids)!=1:
            holds.append({'offset':token.start(),'reason':'collective_or_ambiguous_actor','quote':quote});continue
        person=next(iter(ids))
        # The subject must immediately precede this verb, or explicitly carry
        # across its own already established 'left ... and returned ...' clause.
        nearest=max(actor_spans,key=lambda s:s[1]);gap=actor[nearest[1]:]
        direct=not gap.strip(' \t\r\n,') or bool(re.fullmatch(r'\s+had\s+',gap))
        if verb in {'left','departed'} and re.search(r'\b(?:declared|excused)\b.*\b(?:and|she|he)\s*$',gap,re.I|re.S):direct=True
        compound=bool(events and events[-1]['person_id']==person and re.search(r'\band\s*$',gap,re.I))
        physical=bool(re.match(r'\s*(?:(?:to\s+|of\s+)?(?:the\s+)?(?:meeting|room|chambers|council\s+chambers)\b|at\s*\d{1,2}[:.]\d{2}\b)',after,re.I))
        if verb in {'lost connection','lost the connection','disconnected','reconnected'}:physical=True
        if verb in {'recused','excused','conflict of interest','was absent','was not present','not in attendance'}:physical=False
        if not(direct or compound) or not physical:
            holds.append({'offset':token.start(),'reason':'nonphysical_or_unparsed_attendance','quote':quote});continue
        state='present' if verb in {'returned','joined','rejoined','arrived','entered','reconnected'} else 'absent'
        events.append({'offset':token.start(),'person_id':person,'state':state,'verb':verb,'quote':quote})
    return events,holds


def present_at_vote(initial,events,holds,cutoff):
    uncertainty=[h for h in holds if h['offset']<cutoff]
    if uncertainty:raise ValueError('earlier_unparsed_attendance:'+uncertainty[0]['reason'])
    # A timeless PRESENT roster may list eventual arrivals; infer initial state
    # backwards from each person's first explicit event before replaying forward.
    present=set(initial)
    for pid in {e['person_id']for e in events}:
        first=next(e for e in events if e['person_id']==pid)
        if first['state']=='present':
            if first['verb'] in {'joined','arrived','entered'}:present.discard(pid)
            elif cutoff<first['offset']:raise ValueError('initial_state_before_first_return_unknown')
    applied=[]
    for e in events:
        if e['offset']>=cutoff:break
        if e['state']=='present':present.add(e['person_id'])
        else:present.discard(e['person_id'])
        applied.append(e)
    return present,applied


def decision_choices(block,pool):
    # Stop at the next numbered agenda item, next formal decision, or main-motion
    # boundary; no arbitrary nine-line cap and no later agenda narrative ballots.
    tail=re.sub(r'(?<=\w)\n[ \t]*(?=opposed\b)', ' ', block['tail'],flags=re.I)
    boundaries=[m.start()for pattern in [r'(?m)^\s*\d+(?:\.\d+)*[.)]?\s+[A-Z]',r'(?im)^\s*(?:Motion\s+)?(?:CARRIED|DEFEATED|WITHDRAWN|NOT CARRIED)\b',r'\bOn the (?:Main )?Motion\b']for m in re.finditer(pattern,tail)]
    if boundaries:tail=tail[:min(boundaries)]
    choices={};proof=[];lines=tail.splitlines();i=0
    while i<len(lines):
        line=lines[i].strip();i+=1
        prefix=re.match(r'(OPPOSED|AGAINST|NO|IN FAVOU?R|YES|ABSTAIN(?:ED)?|RECUSED)\s*:\s*(.*)',line,re.I)
        suffix=re.match(r'((?:\d+\s+)?(?:Mayor|Councillors?)\s+.*?)\s+(opposed|voted against|voted no|voted(?: in)? favou?r|voted yes|abstained|recused)\b',line,re.I)
        if not prefix and not suffix:continue
        if prefix:
            verb,names=prefix.groups()
            # Consume wrapped identity rows until a blank line, item boundary or
            # another declaration; any unrecognized token then holds the ballot.
            while i<len(lines) and lines[i].strip() and not re.match(r'\s*(?:\d+[.]|OPPOSED\s*:|MOVED BY|SECONDED|Motion\b)',lines[i],re.I):
                next_line=lines[i].strip()
                if re.search(r'\b(?:Council|Mayor|Councillor)\b.+\b(?:left|returned|opened|called|stated)\b',next_line,re.I):break
                names+=' '+next_line;i+=1
        else:names,verb=suffix.groups()
        if re.search(r'abstain|recus',verb,re.I):raise ValueError('source_special_vote_not_yes_no')
        choice='Yes' if re.search(r'favour|favor|\byes\b',verb,re.I)else'No'
        spans,ambiguous=exact_name_spans(names,pool,allow_surnames=True)
        if ambiguous or not spans:raise ValueError('source_dissent_identity_unresolved')
        mask=list(names)
        for a,b,pid in spans:mask[a:b]=' '*(b-a)
        residue=re.sub(r'\b(?:Mayor|Councillors?|and|Committee|Members?)\b',' ',''.join(mask),flags=re.I)
        residual=re.findall(r'[A-Za-z]+',residue)
        if residual:raise ValueError('source_dissent_unaccounted_tokens:'+','.join(residual))
        for pid in {m[2]for m in spans}:
            if pid in choices and choices[pid]!=choice:raise ValueError('source_conflicting_named_choices')
            choices[pid]=choice
        proof.append({'names':names,'verb':verb,'person_ids':sorted({m[2]for m in spans}),'choice':choice})
    return choices,proof


def read_source(source):
    path=ROOT/source['source_file'];binary=path.read_bytes();digest=hashlib.sha256(binary).hexdigest()
    assert digest==source['source_sha256'],'binary_sha256_changed'
    assert source['source_format']=='original_pdf_layout' and binary.lstrip().startswith(b'%PDF-'),'native_pdf_missing'
    output=CACHE/(digest+'.txt')
    # Run independently even if the production audit has a cached extraction.
    subprocess.run(['pdftotext','-layout','-enc','UTF-8',str(path),str(output)],check=True,timeout=60,capture_output=True)
    native=output.read_text(errors='strict')
    text='\n'.join(line for line in native.splitlines() if not re.match(r'^\s*Minutes of[^\n]*$',line,re.I) and not re.match(r'^\s*\d+\s*$',line))
    date_match=re.search(r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(20\d{2})\b',text[:1600],re.I)
    assert date_match,'native_header_date_missing'
    day=datetime.strptime(' '.join(date_match.groups()),'%B %d %Y').date().isoformat()
    pool=active_people(day)
    header=re.search(r'(?im)^\s*((?:Special\s+)?Counci[l!] Minutes|Committee of the Whole Minutes)\s*$',text[:1200])
    assert header,'native_source_not_council_or_whole_minutes'
    source_body='Committee of the Whole'if'Committee'in header.group(1)else'Council'
    roster,quote=roster_from_native(text,people)
    events,unknown=independent_attendance(text,[persons[i]for i in roster])
    sidecar=Path(str(path)+'.url')
    url=sidecar.read_text().strip() if sidecar.exists() else source['source_url']
    assert url and url==source['source_url'],'official_source_url_missing_or_changed'
    assert re.match(r'https://(?:www\.)?langford\.ca/|https://pub-langford\.escribemeetings\.com/',url),'nonofficial_source_url'
    return {'source_file':source['source_file'],'sha256':digest,'url':url,'native_text_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
        'date':day,'source_body':source_body,'header_quote':header.group(1),'text':text,'roster':roster,'roster_quote':quote,'pool':pool,'events':events,'unknown_events':unknown,'blocks':formal_decisions(text)}


def main():
 assert hashlib.sha256(plan_bytes).hexdigest()=='7608b197ee295ea2dd062d1c238cc2b4a64cafd57c0c50ed5724a206797ed717','plan_changed'
 for name,digest in plan['summary']['code_sha256s'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,'shared_engine_changed:'+name
 assert hashlib.sha256((OUT/'ballot-source-current-snapshot.json').read_bytes()).hexdigest()==plan['summary']['current_motion_snapshot_sha256'],'motion_snapshot_changed'
 assert hashlib.sha256((OUT/'full-current-vote-inventory.json').read_bytes()).hexdigest()==plan['summary']['current_vote_inventory_sha256'],'vote_snapshot_changed'
 candidates=plan['motions']+plan['canonical_body_corrections'];sources={r['source_file']:r for r in candidates};loaded={}
 for key,r in sources.items():
  try:loaded[key]=read_source(r)
  except Exception as e:loaded[key]={'error':str(e)}
 records=[]
 for r in candidates:
  mid=r['motion_id'];src=loaded[r['source_file']];rec={'motion_id':mid,'status':'held','kind':'body_correction' if r in plan['canonical_body_corrections']else 'new_ballot','source_file':r['source_file']}
  try:
   assert not src.get('error'),src.get('error')
   row=motions[mid];meeting=meetings[row['meeting_id']]
   assert src['date']==r['source_date'],'source_date_differs'
   assert abs((date.fromisoformat(src['date'])-date.fromisoformat(meeting['meeting_date'][:10])).days)<=1,'catalog_date_mismatch'
   assert norm(src['roster_quote'])==norm(r['roster_quote']),'source_roster_mismatch'
   assert src['source_body']==r['source_classification'],'body_classification_differs'
   if r in plan['motions']:assert norm(row['text_content'])==norm(r['source_motion_text']),'current_body_not_exact_proposal'
   else:
    assert norm(row['text_content'])in norm(r['source_motion_text']),'body_correction_changes_existing_operative_clause'
    assert sorted(r['current_vote_ids'])==sorted(v['id']for v in existing[mid]),'body_correction_vote_ids_changed'
   text=src['text'];flat=re.sub(r'\W+','',text.casefold());needle=re.sub(r'\W+','',r['source_block'].casefold())
   assert flat.count(needle)==1,'full_actor_body_result_block_not_unique'
   assert norm(r['source_motion_text'])in norm(r['source_block']),'body_missing_from_block'
   # Locate by the full bound actor/body/result block, then bind its first result.
   compact_prefix=flat.index(needle);block_candidates=[]
   for b in src['blocks']:
    if norm(r['source_motion_text'])==norm(b['body']):block_candidates.append(b)
   assert len(block_candidates)==1,'independent_complete_formal_body_not_unique:'+str(len(block_candidates))
   b=block_candidates[0]
   assert family(b['result'])==family(r['source_result'])==family(row['result']),'explicit_result_conflict'
   assert rule['enabled_from']<=src['date']<=rule['enabled_through']or'UNANIMOUS'in b['result'],'policy_date_outside_scope'
   present,events=present_at_vote(src['roster'],src['events'],src['unknown_events'],b['vote_offset'])
   active={p['id']for p in src['pool']};assert 4<=len(present)<=7 and present<=active,'dated_membership_or_quorum_missing'
   proposed={v['person_id']:v['vote']for v in r['votes']};assert set(proposed)==present and len(proposed)==len(r['votes']),'independent_presence_differs'
   for v in r['votes']:assert persons[v['person_id']]['name']==v['person_name'],'canonical_name_differs'
   named,namedproof=decision_choices(b,src['pool']);assert set(named)<=present,'named_voter_absent'
   independent={i:named.get(i,'Yes')for i in present};assert independent==proposed,'independent_choices_differ'
   yes=sum(v=='Yes'for v in independent.values());no=sum(v=='No'for v in independent.values());assert (family(b['result'])=='passed')==(yes>no),'outcome_tally_conflict'
   assert not('UNANIMOUS'in b['result']and no),'unanimity_contradiction'
   oldvotes=existing[mid];assert all(independent.get(v['person_id'])==v['vote']for v in oldvotes),'existing_choice_conflict'
   actualnew={(v['person_id'],v['vote'])for v in r.get('new_choice_rows',[])};expectednew={(pid,v)for pid,v in independent.items()if pid not in{v['person_id']for v in oldvotes}};assert actualnew==expectednew,'new_choices_differ'
   rec.update({'status':'reviewed','source_sha256':src['sha256'],'source_url':src['url'],'source_date':src['date'],'catalog_date':meeting['meeting_date'],'native_text_sha256':src['native_text_sha256'],'roster_quote':src['roster_quote'],'present_person_ids':sorted(present),'dated_membership_intervals':[m for m in live['memberships']if m['person_id']in present and m.get('classification')=='Council' and m.get('start_date')and m['start_date']<=src['date']and(not m.get('end_date')or m['end_date']>=src['date'])],'independent_presence_events':events,'source_motion_text':b['body'],'outcome_quote':b['outcome_quote'],'named_choice_proof':namedproof,'choices':[{'person_id':pid,'vote':independent[pid]}for pid in sorted(independent)],'new_choice_count':len(actualnew),'existing_vote_ids':[v['id']for v in oldvotes],'checks':['original_binary_hash_official_url','native_date_catalog_within_one_day','unique_full_actor_body_firstresult','exhaustive_roster_names','dated_council_membership','independent_physical_presence','full_named_dissent_accounting','per_choice_existing_values_preserved','reconstructed_tally']})
  except Exception as e:rec['reason']=str(e)
  records.append(rec)
 summary={'candidates':82,'canonical_body_corrections':6,'reviewed':sum(r['status']=='reviewed'for r in records),'held':sum(r['status']=='held'for r in records),'reviewed_new_choices':sum(r.get('new_choice_count',0)for r in records),'distinct_original_sources':len(sources),'hold_reasons':dict(Counter(r.get('reason')for r in records if r['status']=='held'))}
 out={'mode':'independent_native_read_only_historical_review','candidate_plan_sha256':hashlib.sha256(plan_bytes).hexdigest(),'review_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'apply_script_sha256':hashlib.sha256((OUT/'apply_historical_ballots.py').read_bytes()).hexdigest(),'summary':summary,'frozen_engine_sha256s':plan['summary']['code_sha256s'],'snapshot_sha256s':{n:hashlib.sha256((OUT/n).read_bytes()).hexdigest()for n in ['ballot-source-current-snapshot.json','full-current-vote-inventory.json','vote-people-current-snapshot.json']},'reviewed_candidate_ids':[r['motion_id']for r in records if r['status']=='reviewed'and r['kind']=='new_ballot'],'reviewed_body_correction_ids':[r['motion_id']for r in records if r['status']=='reviewed'and r['kind']=='body_correction'],'historical_membership_receipt_sha256':hashlib.sha256((OUT/'historical-office-applied-receipt.json').read_bytes()).hexdigest(),'canonical_body_corrections':[r for r in records if r['kind']=='body_correction'],'text_notes':{'1506':'Rendered original page2 confirms printed Royal Royals University in recital; operative clause correctly says Royal Roads University and remains unchanged. Raw official spelling retained in canonical evidence.','2305':'AND prefix belongs to its own MOVED BY Szpak/SECONDED Yacucha/first-result block, not preceding separately voted resolution.'},'mayor_role_binding_review':'2570/2571: native PRESENT Mayor S. Young plus unique dated Mayor Stew Young143 interval2018-11-19–2022-11-06 binds The Mayor return. Independently replayed actual earlier Young exit and named-role return before both ballots; no habit assumption.','records':records}
 (OUT/'historical82-independent-review.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(summary))
if __name__=='__main__':main()
