"""Source-bound agenda accommodations, separate from physical attendance.

Only the agenda's own outcome, or a later frame after a fully closed named
item episode, can disregard its documentary conflict token. Declarations,
unknown subjects, incomplete/nested items, and target ballots remain held.
"""
import hashlib
import re

from .ballot_reconstruction import validate_roster_entries
from .source_occurrences import formal_inventory, own_formal_envelopes, text_occurrence_unique

_ACCOMMODATION = re.compile(
    r'''(?m)^[ \t]*[•*\-]\s*Separate\s+item\s+\d+(?:\.\d+)*\s+["“]Public\s+Participation["”]\s+in\s+two\s+to\s+accommodate\s+'''
    r"(?P<subject>(?:Mayor|Councillor)\s+[A-Za-z .-]+?)[’']s\s+"
    r'(?:perceived\s+)?(?:pecuniary\s+)?conflict\s+of\s+interest\s+pertaining\s+to\s+agenda\s+item\s+'
    r'(?P<label>\d+(?:\.\d+)+)\s*[-–]\s*(?P<description>[^•\n]+(?:\n(?!\s*[•*\-])[^\n]+)*)', re.I)
_HEADING = re.compile(r'(?m)^[ \t]*(\d+(?:\.\d+)*)(?:\.)?[ \t]+([^\n]+)')
_ACTION = re.compile(r'\b(?:remained|lost|stepped|excused|left|returned|departed|arrived|joined|rejoined|withdrew|recused|exited|disconnected|reconnected|declared|restated|stated|reported|said|asked|advised|explained|told)\b', re.I)
_INTRODUCTION = re.compile(r'(?im)^[ \t]*(?:Amendment\s*:\s*)?(?:MOVED\b|On\s+(?:the\s+)?(?:Main\s+)?Motion\b|Voting\s+resumed\b)')
_SUBJECT = r'(?:Mayor|Councillor)\s+[A-Za-z .-]+?'
_CLOCK = r'\d{1,2}:\d{2}\s*(?:p\.?m\.?|a\.?m\.?)'
_EXIT = re.compile(r'(?P<subject>'+_SUBJECT+r')\s+declared\s+a\s+(?:perceived\s+)?(?:pecuniary\s+)?conflict\s+of\s+interest\s+and\s+left\s+the\s+meeting\s+at\s+'+_CLOCK+r'\.?', re.I)
_RETURN = re.compile(r'(?P<subject>'+_SUBJECT+r')\s+returned\s+to\s+the\s+meeting\s+at\s+'+_CLOCK+r'(?:\s+and\s+assumed\s+the\s+role\s+of\s+the\s+Chair)?\.?', re.I)
_CHAIR = re.compile(r'(?P<subject>'+_SUBJECT+r')\s+assumed\s+the\s+role\s+of\s+the\s+Chair\.?', re.I)


def _single_person(subject, people):
    found, unknown = validate_roster_entries(subject, people)
    return found[0]['id'] if len(found) == 1 and not unknown else None


def _closed_target(source, label, person_id, events, unknown, people):
    text = source['text']
    envelopes = formal_inventory(source)['envelopes']
    # Conditions numbered inside a motion are not agenda headings.
    headings = [h for h in _HEADING.finditer(text)
                if not any(e['body_start'] <= h.start() < e['outcome_end'] for e in envelopes)]
    targets = [h for h in headings if h[1] == label]
    if len(targets) != 1:
        return None
    heading = targets[0]
    peers = [h for h in headings if h.start() > heading.start() and len(h[1].split('.')) <= len(label.split('.'))]
    if not peers:
        return None
    stop = peers[0].start()
    frames = [(b, own_formal_envelopes(source, b)) for b in source['blocks']
              if heading.end() < b['source_offset'] < stop]
    if len(frames) != 1 or len(frames[0][1]) != 1:
        return None
    block, owned = frames[0]
    envelope = owned[0]
    start = block['source_offset']
    introductions = list(_INTRODUCTION.finditer(text, heading.end(), stop))
    if (len(introductions) != 1 or introductions[0].start() != start
            or envelope['kind'] != 'seconded_motion'
            or envelope['outcome_end'] >= stop
            or len([e for e in envelopes if heading.end() <= e['anchor_offset'] < stop]) != 1
            or any(heading.end() <= e['offset'] < stop for e in unknown)):
        return None
    # A departure must be owned by this item's complete pre-formal narrative.
    # A previous participation episode cannot substitute for it.
    intro = text[heading.end():start]
    exit_match = _EXIT.search(intro)
    if not exit_match or _single_person(exit_match['subject'], people) != person_id:
        return None
    residue = (intro[:exit_match.start()]+intro[exit_match.end():]).strip()
    if residue:
        chair = _CHAIR.fullmatch(' '.join(residue.split()))
        if not chair or _single_person(chair['subject'], people) is None:
            return None
    tail = text[envelope['outcome_end']:stop].strip()
    returned = _RETURN.fullmatch(' '.join(tail.split()))
    if not returned or _single_person(returned['subject'], people) != person_id:
        return None
    physical = [e for e in events if heading.end() <= e['offset'] < stop]
    if (len(physical) != 2 or [(e['person_id'], e['state'], e['verb']) for e in physical]
            != [(person_id, 'absent', 'left'), (person_id, 'present', 'returned')]
            or not heading.end() < physical[0]['offset'] < start
            or not envelope['outcome_end'] < physical[1]['offset'] < stop):
        return None
    return {'heading_span':[heading.start(),heading.end()], 'formal_start':start,
            'outcome_span':[envelope['outcome_offset'],envelope['outcome_end']],
            'exit_offset':physical[0]['offset'], 'return_offset':physical[1]['offset'], 'next_peer_start':stop}


def documentary_presence_before_vote(source, block, position, events, unknown, people):
    """Return remaining holds and exact no-state-change documentary witnesses."""
    held = []
    observations = []
    envelopes = formal_inventory(source)['envelopes']
    current = own_formal_envelopes(source, block)
    for event in unknown:
        if event['offset'] >= position:
            continue
        observation = None
        for envelope in envelopes:
            body = source['text'][envelope['body_start']:envelope['outcome_offset']]
            if not re.match(r'\s*THAT\s+Council\s+approve\s+(?:the\s+)?(?:amended\s+)?agenda\s+as\s+(?:follows|amended)\b', body, re.I):
                continue
            for match in _ACCOMMODATION.finditer(body):
                start = envelope['body_start']+match.start()
                end = envelope['body_start']+match.end()
                person_id = _single_person(match['subject'], people)
                if (not start <= event['offset'] < end or person_id is None
                        or _ACTION.search(match[0]) or _ACTION.search(body[:match.start()])
                        or len(re.findall(r'conflict\s+of\s+interest', match[0], re.I)) != 1
                        or not re.match(r'conflict\s+of\s+interest\b', source['text'][event['offset']:], re.I)):
                    continue
                # The agenda itself also requires one unambiguous parsed owner.
                agenda_owners = [b for b in source['blocks'] if own_formal_envelopes(source,b) == [envelope]]
                if len(agenda_owners) != 1 or not text_occurrence_unique(source,agenda_owners[0]):
                    continue
                closure = None
                if current == [envelope]:
                    clearance = 'own_agenda_only'
                else:
                    closure = _closed_target(source, match['label'], person_id, events, unknown, people)
                    if not closure or block['source_offset'] < closure['next_peer_start']:
                        continue
                    clearance = 'closed_target_episode'
                observation = {'kind':'documentary_agenda_accommodation', 'state_effect':'none',
                               'source_sha256':source['source_sha256'],
                               'source_text_sha256':formal_inventory(source)['text_sha256'], 'token_offset':event['offset'],
                               'bullet_span':[start,end], 'bullet_sha256':hashlib.sha256(source['text'][start:end].encode()).hexdigest(),
                               'agenda_body_span':[envelope['body_start'],envelope['outcome_offset']],
                               'person_id':person_id, 'referenced_item':match['label'], 'clearance_kind':clearance}
                if closure:
                    observation['closed_target_episode'] = closure
        if observation is None:
            held.append(event)
        else:
            observations.append(observation)
    return held, observations
