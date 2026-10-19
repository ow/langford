"""Documentary roster and physical-presence validation for ballot reconstruction.

These helpers never infer a choice. Unknown roster tokens or attendance language
are returned as holds for the caller; absence of a parsed event is not proof.
"""
import re
from collections import defaultdict
from .vote_evidence import normalize_text


def resolve_people(text,people):
    surnames=defaultdict(list)
    for person in people:
        parts=normalize_text(person['name']).split()
        if len(parts)>=2 and len(parts[-1])>=3:surnames[parts[-1]].append(person)
    found=[];unknown=[]
    for surname,candidates in surnames.items():
        if not re.search(r'\b'+re.escape(surname)+r'\b',normalize_text(text)):continue
        initial=re.search(r'\b([A-Z])\.\s*'+re.escape(surname)+r'\b',text,re.I)
        if initial:candidates=[p for p in candidates if p['name'][0].casefold()==initial[1].casefold()]
        if len(candidates)==1:found.append(candidates[0])
        else:unknown.append(surname)
    return found,unknown


def validate_roster_entries(text,people):
    """Account for every roster token, including unprefixed unknown full names."""
    found,unknown=resolve_people(text,people)
    remaining=normalize_text(text).split()
    known_words={word for person in found for word in normalize_text(person['name']).split()}
    allowed={'mayor','councillor','councillors','member','members','committee','chair','acting','and','present','via','electronic','electronically','telephone','teleconference','video','conference','zoom','in','person','by','phone','participating','remote','remotely'}
    residual=[word for word in remaining if word not in known_words|allowed and len(word)>1]
    return found,sorted(set(unknown+residual))


_EVENT=re.compile(r'\b(lost\s+(?:the\s+)?connection|stepped\s+out|excused|left|returned|departed|arrived|joined|rejoined|withdrew|recused|exited|disconnected|reconnected|conflict\s+of\s+interest)\b',re.I)


def _physical_target(verb,after):
    physical=bool(re.match(r'\s*(?:(?:to\s+)?(?:the\s+)?(?:room|meeting|chambers|council\s+chambers)\b|at\s+\d{1,2}[:.]\d{2}(?!\d))',after,re.I))
    if verb in {'lost connection','lost the connection','disconnected','reconnected'}:physical=True
    if verb=='stepped out':physical=bool(re.match(r'\s*(?:of\s+(?:the\s+)?(?:room|meeting|chambers)\b|at\s+\d{1,2}[:.]\d{2}(?!\d))',after,re.I))
    return physical and verb not in {'conflict of interest','recused','excused'}


def _abstract_presence(verb,after):
    return bool((verb=='withdrew' and re.match(r'\s+(?:his|her|their|the|a)\s+(?:amending\s+)?motion\b',after,re.I)) or (verb=='left' and re.match(r'\s+(?:the\s+)?decision\b',after,re.I)) or (verb=='returned' and re.match(r'\s+to\s+(?:the\s+)?discussion\b',after,re.I)))


def physical_presence_events(text,voting_people,role_bindings=None):
    """Read ordered physical events; hold abstract, wrapped or ambiguous language.

    Bare full names/initials are eligible, not just role-prefixed names. Accepted
    verbs require a physical meeting/room/connection target or an immediate time;
    'returned to discussion' and 'left the decision to staff' are uncertainty.
    """
    events=[];held=[]
    role_bindings=role_bindings or {}
    known={person['id']:person for person in voting_people}
    for hit in _EVENT.finditer(text):
        before=text[max(0,hit.start()-150):hit.start()]
        generic=re.search(r'\b(?:the\s+)?(acting mayor|mayor|chair|presiding member)\s*$',before,re.I)
        if generic:
            verb=' '.join(hit.group(0).casefold().split());after=text[hit.end():hit.end()+130]
            if _abstract_presence(verb,after):
                continue
            role=generic[1].casefold();binding=role_bindings.get(role)
            quote=before[generic.start():]+hit.group(0)+after.split('\n')[0]
            person=known.get(binding.get('person_id')) if isinstance(binding,dict) else None
            physical=_physical_target(verb,after)
            if not person or not binding.get('source_quote') or binding.get('membership_role','').casefold()!=role or not physical:
                held.append({'offset':hit.start(),'source_quote':quote,'reason':'generic_role_presence_not_uniquely_bound'});continue
            events.append({'offset':hit.start(),'person_id':person['id'],'state':'present' if verb in {'returned','arrived','joined','rejoined','reconnected'} else 'absent','source_quote':quote,'verb':verb,'role_binding':dict(binding)})
            continue
        mentions=[]
        for person in voting_people:
            surname=normalize_text(person['name']).split()[-1]
            for match in re.finditer(r'(?<![A-Za-z])(?:Mayor|Councillors?)?\s*'+re.escape(surname)+r'\b',before,re.I):
                mentions.append((match.end(),match.start(),person))
        if not mentions:continue
        end,start,person=max(mentions,key=lambda entry:entry[0])
        earlier=[mention for mention in mentions if mention[0]<=start and mention[2]['id']!=person['id']]
        connective={'and','mayor','councillor','councillors','committee','member'}|{w for p in voting_people for w in normalize_text(p['name']).split()[:-1]}
        collective=any(set(normalize_text(before[mention[0]:start]).split())<=connective for mention in earlier)
        if collective:
            held.append({'offset':hit.start(),'source_quote':before+hit.group(0)+text[hit.end():hit.end()+80],'reason':'collective_presence_subject_needs_parse'})
            continue
        subject=before[:end];between=before[end:]
        # Initials must agree with the established identity; a surname alone in
        # a sentence can be held but cannot silently assign a different person.
        resolved,ambiguous=resolve_people(subject,[p for p in voting_people if normalize_text(p['name']).split()[-1]==normalize_text(person['name']).split()[-1]])
        after=text[hit.end():hit.end()+130]
        snippet=before[max(0,start-35):]+hit.group(0)+after.split('\n')[0]
        verb=' '.join(hit.group(0).casefold().split())
        return_event=verb in {'returned','arrived','joined','rejoined','reconnected'}
        # Only an adjacent subject is accepted. A preceding speaker discussing
        # someone else's departure supplies a hold, not an attendance change.
        adjacent=bool(re.fullmatch(r'[\s,]*(?:had\s+)?',between))
        # A documented board membership/conflict clause can separate the named
        # member from their own physical exit. Require the complete narrow
        # grammar; reported departures or another person's actions stay held.
        conflict_exit=verb=='left' and bool(re.fullmatch(
            r',\s*as\s+a\s+Member\s+of\s+the\s+[A-Za-z\s-]+\s+Board,\s*'
            r'declared\s+a\s+conflict\s+with\s+respect\s+to\s+Bylaw\s+No\.\s*\d+\s+and\s*',
            between,re.I))
        # 'X left ... and returned ...' repeats the same explicit subject.
        inherited=bool(events and events[-1]['person_id']==person['id'] and events[-1]['offset']>=hit.start()-len(before)+end and re.search(r'\band\s*$',between,re.I))
        adjacent=adjacent or inherited or conflict_exit
        physical=_physical_target(verb,after)
        if _abstract_presence(verb,after):
            continue  # Explicitly abstract actions do not change physical presence.
        if len(resolved)!=1 or ambiguous or not adjacent or not physical:
            held.append({'offset':hit.start(),'source_quote':snippet,'reason':'ambiguous_or_nonphysical_presence_language'});continue
        # Include surname start: this event is eligible only before the vote's
        # source position; the exact physical verb offset preserves ordering.
        events.append({'offset':hit.start(),'person_id':resolved[0]['id'],'state':'present' if return_event else 'absent','source_quote':snippet,'verb':verb})
    return events,held


def voters_before_vote(initial_roster,events,cutoff):
    """A PRESENT list can include late arrivals; seed only proved initial voters."""
    present=set(initial_roster);adjustments=[]
    first={}
    for event in events:first.setdefault(event['person_id'],event)
    for person,event in first.items():
        if event['state']=='present':
            if event['verb'] in ('joined','arrived'):
                present.discard(person);adjustments.append(event)
            elif cutoff<event['offset']:
                return None,[{'reason':'initial_presence_before_first_return_unknown',**event}]
    for event in events:
        if event['offset']>=cutoff:continue
        if event['state']=='present':present.add(event['person_id'])
        else:present.discard(event['person_id'])
    return present,adjustments
