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
receipt_bytes=(OUT/'full-ballot-remaining-receipt.json').read_bytes()
receipt=json.loads(receipt_bytes)
plan_bytes=(OUT/'full-ballot-audit.json').read_bytes();plan=json.loads(plan_bytes)
live=json.loads(Path('/private/tmp/independent-ballot-live.json').read_text())
people=live['people'];persons={p['id']:p for p in people}
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
    ids={m['person_id'] for m in live['memberships'] if m['start_date'] and m['start_date']<=day and (not m['end_date'] or m['end_date']>=day)}
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
    movers=list(re.finditer(r'(?im)^[ \t]*MOVED[ \t]+BY[ \t]*[:;]?',text))
    blocks=[]
    for i,start in enumerate(movers):
        stop=movers[i+1].start() if i+1<len(movers) else len(text)
        block=text[start.start():stop]
        result=OUTCOME.search(block)
        if not result:continue
        body=block[:result.start()]
        begin=re.search(r'\bTHAT\b',body,re.I)
        if not begin:continue
        blocks.append({'body':body[begin.start():].strip(),'result':result.group(1).upper(),
            'outcome_quote':result.group(0).strip(),'vote_offset':start.start()+result.start(),
            'start':start.start(),'stop':stop,'tail':block[result.end():],'block':block.strip()})
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
    tail=block['tail']
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
    sources={c['after_meta']['ballot_reconstruction']['source_file']:c['after_meta']['ballot_reconstruction']for c in receipt['changes']}
    results={}
    def load(item):
        key,source=item
        try:return key,read_source(source)
        except Exception as error:return key,{'error':str(error)}
    with ThreadPoolExecutor(max_workers=4)as workers:
        results=dict(workers.map(load,sources.items()))
    reviewed=[]
    for change in receipt['changes']:
        pid=change['motion_id'];proof=change['after_meta']['ballot_reconstruction'];src=results[proof['source_file']]
        record={'motion_id':pid,'source_file':proof['source_file'],'status':'hold','checks':[]}
        try:
            if src.get('error'):raise ValueError(src['error'])
            assert src['date']==proof['source_date'],'native_header_date_differs_from_proposal'
            row=motions[pid];meeting=meetings[row['meeting_id']]
            assert meeting['classification']=='Council','not_council_body_meeting'
            assert ('Committee of the Whole'in meeting['title'])==(src['source_body']=='Committee of the Whole'),'native_body_catalog_title_mismatch'
            delta=abs((date.fromisoformat(src['date'])-date.fromisoformat(meeting['meeting_date'][:10])).days)
            assert delta<=1,'native_header_catalog_date_mismatch'
            assert norm(src['roster_quote'])==norm(proof['roster_quote']),'native_roster_quote_differs'
            target=norm(row['text_content']);assert target==norm(proof['source_motion_text']),'current_body_differs_from_source_proposal'
            matches=[b for b in src['blocks'] if norm(b['body'])==target]
            assert len(matches)==1,'native_formal_body_not_unique:'+str(len(matches))
            block=matches[0]
            assert family(block['result'])==family(row['result'])==family(proof['source_result']),'native_outcome_conflicts'
            assert rule['enabled_from']<=src['date']<=rule['enabled_through']or'UNANIMOUS'in block['result'],'recording_convention_outside_verified_period'
            expected,events=present_at_vote(src['roster'],src['events'],src['unknown_events'],block['vote_offset'])
            active={p['id']for p in src['pool']}
            assert 4<=len(expected)<=7 and expected<=active,'membership_or_quorum_not_proven'
            proposed={v['person_id']:v['vote']for v in proof['votes']}
            assert len(proposed)==len(proof['votes'])and set(proposed)==expected,'independent_presence_set_differs'
            for v in proof['votes']:assert persons[v['person_id']]['name']==v['person_name'],'canonical_identity_changed'
            named,named_proof=decision_choices(block,src['pool'])
            assert set(named)<=expected,'source_named_voter_not_present'
            independent={i:named.get(i,'Yes')for i in expected}
            if'UNANIMOUS'in block['result']:assert all(v=='Yes'for v in independent.values()),'unanimity_conflicts'
            assert independent==proposed,'independent_choices_differ'
            yes=sum(v=='Yes'for v in independent.values());no=sum(v=='No'for v in independent.values())
            assert (family(block['result'])=='passed')==(yes>no),'independent_tally_conflicts'
            assert all(v['person_id']in independent and independent[v['person_id']]==v['vote']for v in existing[pid]),'existing_choice_conflict'
            expected_new=sorted((pid,i,v)for i,v in independent.items()if i not in {v['person_id']for v in existing[pid]})
            assert expected_new==sorted(tuple(v)for v in change['new_choices']),'current_new_choice_set_changed'
            record.update({'status':'reviewed','checks':['native_binary_sha256','official_url','unique_exact_formal_body','compatible_explicit_outcome','native_header_date_within_one_day','exhaustive_native_roster_identities','independent_physical_presence_replay','current_dated_council_membership','complete_dissent_names','independent_choices_and_tally','current_existing_choices_preserved'],
                'source_body':src['source_body'],'scope_basis':'1971 sections2,4,38/44,52/60,56/64; COTW is recommendations only'if src['source_body']=='Committee of the Whole'else'Council',
                'source_sha256':src['sha256'],'source_url':src['url'],'native_text_sha256':src['native_text_sha256'],'source_date':src['date'],'catalog_date':meeting['meeting_date'],
                'roster_person_ids':sorted(src['roster']),'present_person_ids':sorted(expected),'independent_events':events,'named_choice_proof':named_proof,'source_motion_text':block['body'],'outcome_quote':block['outcome_quote'],
                'choices':[{'person_id':i,'vote':independent[i]}for i in sorted(independent)],'yes':yes,'no':no,'new_choices':len(expected_new)})
        except(Exception)as error:record['reason']=str(error)
        reviewed.append(record)
    summary={'candidate_motions':len(reviewed),'reviewed':sum(r['status']=='reviewed'for r in reviewed),'held':sum(r['status']=='hold'for r in reviewed),
        'reviewed_new_choices':sum(r.get('new_choices',0)for r in reviewed),'distinct_original_pdfs':len(sources),'hold_reasons':dict(Counter(r.get('reason')for r in reviewed if r['status']=='hold'))}
    result={'mode':'independent_native_pdf_machine_review_no_writes','at':datetime.now(timezone.utc).isoformat(),'summary':summary,
        'candidate_plan_sha256':hashlib.sha256(plan_bytes).hexdigest(),'committee_scope_evidence_sha256':hashlib.sha256((OUT/'committee-whole-recording-rule-scope.json').read_bytes()).hexdigest(),'remaining_receipt_sha256':hashlib.sha256(receipt_bytes).hexdigest(),
        'reviewer_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'reviewed_candidate_ids':[r['motion_id']for r in reviewed if r['status']=='reviewed'],
        'held_candidate_ids':[r['motion_id']for r in reviewed if r['status']=='hold'],
        'sources':[{k:v for k,v in src.items()if k not in['text','pool','blocks']}for src in results.values()], 'records':reviewed}
    # Sets are represented only as sorted identity lists in saved source proof.
    for src in result['sources']:
        if isinstance(src.get('roster'),set):src['roster']=sorted(src['roster'])
    (OUT/'remaining-ballot-independent-review.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
