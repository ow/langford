"""Documentary government roles observed at one meeting, never employment terms.

Consumes the canonical original-minutes source object. It performs no network,
AI or database writes. Initial/surname identities must be registry-unique; a job
mentioned in public input is not an appearance on behalf of a government body.
"""
from collections import defaultdict
from datetime import date, datetime
from pathlib import PurePosixPath
import re
from urllib.parse import urlparse
from typing import Literal, TypedDict


class ParticipantRoleObservation(TypedDict):
    person_id: int
    meeting_id: int
    classification: Literal["government_staff"]
    role: str
    organization: str
    observed_date: str
    native_source_date: str
    method: Literal["official_minutes_explicit_role_v1"]
    source_file: str
    source_sha256: str
    source_url: str
    source_quote: str
    evidence_kind: str

METHOD = 'official_minutes_explicit_role_v1'
_MONTHS = 'January|February|March|April|May|June|July|August|September|October|November|December'
_STAFF = re.compile(r'^(?:(?:Senior|Deputy|Assistant|Acting)\s+)?(?:Manager|Planner|Engineer|Superintendent|Inspector|Chief Administrative Officer|Corporate Officer|Director\s+of)\b', re.I)
_MUNICIPAL = re.compile(r'^(?:Chief Administrative Officer|(?:Deputy |Acting )?Corporate Officer|(?:Deputy )?Director of Corporate Services|Legislative Services Administrative Coordinator|Legislative Services Coordinator|City Engineer|Municipal Clerk)$', re.I)
_ORGANIZATIONS = (
    (re.compile(r'\bCapital\s+Regional\s+District\b', re.I), 'Capital Regional District'),
    (re.compile(r'\bCRD\b'), 'Capital Regional District'),
    (re.compile(r'\bRoyal\s+Canadian\s+Mounted\s+Police\b', re.I), 'Royal Canadian Mounted Police'),
    (re.compile(r'\bWest\s+Shore\s+RCMP\b', re.I), 'West Shore RCMP'),
)


def _day(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _source_hold(source, meeting):
    try:
        path = PurePosixPath(source['source_file'])
        if path.is_absolute() or '..' in path.parts or path.parts[0] != 'archive' or '\\' in str(path):
            return 'project_relative_original_source_required'
        if not re.fullmatch(r'[0-9a-f]{64}', source['source_sha256']):
            return 'original_source_sha256_required'
        url = urlparse(source['source_url'])
        if url.scheme != 'https' or url.hostname not in {'langford.ca', 'www.langford.ca', 'pub-langford.escribemeetings.com'}:
            return 'official_original_source_url_required'
        if source.get('error') or source['source_format'] not in {'original_pdf_layout', 'official_html_structural'}:
            return 'canonical_original_minutes_required'
        own_header = re.split(r'\bPRESENT\b', source['text'], maxsplit=1, flags=re.I)[0]
        header = source['source_header']
        if header.strip() != own_header.strip():
            return 'own_header_text_binding_changed'
        dates = list(re.finditer(r'\b(' + _MONTHS + r')\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(20\d{2})\b', header, re.I))
        if len(dates) != 1:
            return 'native_own_header_date_unknown_or_ambiguous'
        native = datetime.strptime(' '.join(dates[0].groups()), '%B %d %Y').date()
        catalog = _day(meeting['meeting_date'])
        if native != _day(source['local_date']) or abs((native-catalog).days) > 1:
            return 'native_catalog_meeting_date_mismatch'
        if not re.search(r'\b(?:Council|Committee|Commission)\b', header, re.I):
            return 'native_meeting_heading_unknown'
    except (KeyError, ValueError, TypeError, IndexError):
        return 'original_source_binding_incomplete'
    return None


def _person_patterns(people):
    initials = defaultdict(list)
    full_names = defaultdict(list)
    patterns = []
    for person in people:
        words = re.findall(r"[A-Za-z'-]+", person['name'])
        if len(words) < 2:
            continue
        initials[(words[0][0].casefold(), words[-1].casefold())].append(person)
        if len(words[0]) > 1:
            full_names[tuple(word.casefold() for word in words)].append(person)
    for words, candidates in full_names.items():
        expression = r'(?<![A-Za-z])' + r'\s+'.join(map(re.escape, words)) + r'(?![A-Za-z])'
        patterns.append((re.compile(expression, re.I), candidates[0] if len(candidates) == 1 else None,
                         None if len(candidates) == 1 else 'ambiguous_full_name'))
    for (initial, surname), candidates in initials.items():
        expression = r'(?<![A-Za-z])' + re.escape(initial) + r'\.\s*' + re.escape(surname) + r'(?![A-Za-z])'
        patterns.append((re.compile(expression, re.I), candidates[0] if len(candidates) == 1 else None,
                         None if len(candidates) == 1 else 'ambiguous_initial_surname'))
    return patterns


def _names(text, patterns):
    matches = []
    for pattern, person, reason in patterns:
        for match in pattern.finditer(text):
            matches.append((match.start(), match.end(), person, reason))
    return sorted(matches, key=lambda value: (value[0], -value[1]))


def _paragraph(text, position):
    boundaries = list(re.finditer(r'\n[ \t]*\n', text[:position]))
    start = boundaries[-1].end() if boundaries else 0
    after = re.search(r'\n[ \t]*\n', text[position:])
    end = position + after.start() if after else len(text)
    return start, end


def _roster_entries(text, patterns):
    """Keep native PDF column geometry; continuation cells inherit one column."""
    marker = re.search(r'\bATTENDING\s*:', text, re.I)
    if not marker:
        return []
    stop = re.search(r'(?im)^\s*(?:Meeting available|\d+\.\s|CALL TO ORDER)', text[marker.end():])
    if not stop:
        return []
    end = marker.end() + stop.start()
    lines = text[marker.start():end].splitlines()
    columns = {}; entries = []
    for index, original in enumerate(lines):
        line = re.sub(r'^ATTENDING\s*:', lambda m: ' '*len(m[0]), original, flags=re.I)
        for cell in re.finditer(r'\S(?:.*?\S)?(?=\s{2,}|$)', line):
            value = cell[0]; names = [hit for hit in _names(value, patterns) if hit[0] == 0]
            near = next((key for key in columns if abs(key-cell.start()) <= 3), None)
            if names:
                _, right, person, reason = names[0]
                if not value[right:].startswith(','):
                    continue
                entry = {'person': person, 'reason': reason, 'role': value[right+1:].strip(), 'first': index, 'last': index}
                entries.append(entry); columns[cell.start()] = entry
            elif near is not None:
                columns[near]['role'] += ' ' + value
                columns[near]['last'] = index
    for entry in entries:
        entry['source_quote'] = '\n'.join(lines[entry['first']:entry['last']+1])
    return entries


def participant_role_observations(source, *, meeting, people):
    """Return person-ID keyed, source-bound observations for this meeting only.

    Intended ingestion hook: merge these observations into
    ``meetings.meta.participant_roles`` after the original-minutes loader passes.
    The caller owns metadata CAS and preservation; this function never updates
    person memberships, council terms, transcript links or existing metadata.
    """
    reason = _source_hold(source, meeting)
    if reason:
        return {'status': 'source_held', 'observations': {}, 'holds': [{'reason': reason}]}
    text = source['text']; patterns = _person_patterns(people)
    observations: dict[str, ParticipantRoleObservation] = {}
    holds = []; conflicted = set()

    def add(person, role, organization, quote, evidence_kind, ambiguity=None):
        if person is None:
            holds.append({'reason': ambiguity or 'ambiguous_initial_surname', 'source_quote': quote})
            return
        key = str(person['id'])
        if key in conflicted:
            return
        value = {'person_id': person['id'], 'meeting_id': meeting['id'], 'classification': 'government_staff',
                 'role': role, 'organization': organization, 'observed_date': _day(meeting['meeting_date']).isoformat(),
                 'native_source_date': _day(source['local_date']).isoformat(), 'method': METHOD,
                 'source_file': source['source_file'], 'source_sha256': source['source_sha256'],
                 'source_url': source['source_url'], 'source_quote': quote, 'evidence_kind': evidence_kind}
        old = observations.get(key)
        if old and (old['role'].casefold(), old['organization'].casefold()) != (role.casefold(), organization.casefold()):
            observations.pop(key); conflicted.add(key)
            holds.append({'person_id': person['id'], 'reason': 'conflicting_explicit_meeting_roles'})
        else:
            observations.setdefault(key, value)

    # The original City/Town heading plus a municipal-only formal staff function
    # is required. Generic private-sector titles are never enough.
    city = re.search(r'\b((?:City|Town|Village|District) of [A-Za-z][A-Za-z -]{1,45})\s*\n', source['source_header'])
    if city and ' '.join(city[1].casefold().split()) != 'city of langford':
        holds.append({'reason': 'municipal_organization_heading_unknown', 'source_quote': city[0].rstrip()})
        city = None
    if city:
        for entry in _roster_entries(text, patterns):
            role = ' '.join(entry['role'].split()).strip(' ,')
            if _MUNICIPAL.fullmatch(role):
                add(entry['person'], role, city[1].strip(), entry['source_quote'], 'formal_attending_municipal_function', entry['reason'])

    for left, right, person, ambiguous in _names(text, patterns):
        if not re.match(r'\s*,', text[right:]):
            continue
        paragraph_start, paragraph_end = _paragraph(text, left)
        before = text[paragraph_start:left]
        if re.search(r'\b(?:Mayor|Councillors?|Board Director)\s*$', before, re.I):
            continue
        after = text[right:paragraph_end].lstrip(' ,\n\t')
        if not _STAFF.match(after):
            continue
        organizations = [(m.start(), m.end(), organization) for expression, organization in _ORGANIZATIONS
                         for m in expression.finditer(after)]
        if not organizations:
            continue
        organization_start, organization_end, organization = min(organizations)
        role = ' '.join(after[:organization_start].split()).strip(' ,')
        if len(role) > 160 or _names(role, patterns):
            continue
        action = after[organization_end:]
        if not re.match(r'^\s*(?:\([A-Z]{2,8}\))?\s*,?\s*(?:provided|presented|responded|answered|spoke|addressed|outlined|explained|attended)\b', action, re.I):
            continue
        quote = text[left:paragraph_end].rstrip()
        add(person, role, organization, quote, 'explicit_public_body_role_and_actual_participation', ambiguous)
    return {'status': 'parsed', 'observations': observations, 'holds': holds}
