"""Bounded documentary voting eligibility for Langford's Community Advisory Committee.

PRESENT in an original dated CAC member roster is an observation on that date,
not a guessed appointment interval. Full identities and special role eligibility
are independently corroborated below. No Council-membership shortcut for citizen
members, no persistence, and no authority to treat a recommendation as adoption.
"""
import re
import hashlib
from datetime import date

import requests
from bs4 import BeautifulSoup

from .canonical_motions import bound_source_motion, source_identity, source_motion_candidates, operative_view, operative_proof
from .ballot_reconstruction import (
    physical_presence_events, resolve_people, validate_roster_entries, voters_before_vote,
)
from .vote_evidence import normalize_text, named_vote_declarations, outcome_family

# Identity corroboration only: do not extrapolate these current appointments to
# a historical date. The contemporaneous original member roster proves that date.
CAC_CITIZENS = {
    'chris foxall', 'frazer johnson', 'nicolas lehman', 'robin plomp',
    'jacqui whiteway', 'moira mcdonald',
}
CAC_IDENTITY_SECTION_SHA256 = '3ff00718fd35dc916b9655f61dac7157dd2ae78fb123b426188af5f6ed0f9917'
CAC_COUNCILLORS = {'keith yacucha', 'mark morley', 'colby harder'}
CAC_SOURCES = {
    'identity_listing': {
        'url': 'https://langford.ca/city-hall/council-committees/mayor-council/',
        'sha256': '191f44fb9b902f91d00ac24681216a8466afee6ec851e746c30768f8fe7e0a66',
        'validated_as_of': '2026-10-18',
    },
    'terms_2023': {
        'url': 'https://langford.ca/wp-content/uploads/2023/02/February-21-2023-Agenda-Package.pdf',
        'sha256': '69d5128ee9facfb993f4b4208b2a7e5049c6632ab93a29abc0e354690efa3ff0',
        'sections': [4, 5, 7, 13, 14, 15, 26, 28, 33, 34],
    },
    'terms_2024': {
        'url': 'https://langford.ca/wp-content/uploads/2023/04/POL-0163-Admin-Amend-4-SIGNED-EDITED-NJ.pdf',
        'sha256': 'dd4dd8b6b95b963ef7c964be676e11d1a4603e1bbb27f2b847467ecefe748182',
        'sections': [4, 5, 7, 13, 14, 15, 26, 28, 32, 33],
    },
    'councillor_appointment': {
        'url': 'https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=5137',
        'sha256': '0534e98a95a3eed0b375a969c2c8d6fbb34c65f711f0ae6f966b91d445e0081a',
        'effective_from': '2023-02-21', 'item': '9.6',
    },
    'whiteway_appointment': {
        'url': 'https://pub-langford.escribemeetings.com/FileStream.ashx?DocumentId=11478',
        'sha256': '23264d755e2067195b7288faecdaf7163ebcbfd4a10f1178805e44d240b940df',
        'effective_from': '2024-07-15', 'effective_through': '2026-12-31', 'item': '5.1',
    },
}


def refresh_committee_policy(policy, checked_date, session=None):
    """Automatically extend only the unchanged signed terms/member registry.

    The target accordion has a semantic content hash: unrelated bios, theme
    markup and nonces cannot alter eligibility. Changed or unavailable primary
    evidence produces an explicit machine-revalidation hold, never a date bump.
    """
    scope = {'enabled_from': '2023-02-21', 'enabled_through': min(checked_date, '2026-12-31'),
             'validated_as_of': checked_date, 'terms_url': CAC_SOURCES['terms_2024']['url'],
             'identity_listing_url': CAC_SOURCES['identity_listing']['url']}
    http = session or requests.Session()
    try:
        date.fromisoformat(checked_date)
        document = http.get(scope['terms_url'], timeout=30)
        document.raise_for_status()
        digest = hashlib.sha256(document.content).hexdigest()
        scope['terms_sha256'] = digest
        if digest != CAC_SOURCES['terms_2024']['sha256']:
            return {**policy, 'committee_policy': {**scope, 'status': 'committee_terms_changed_requires_machine_revalidation'}}
        listing = http.get(scope['identity_listing_url'], timeout=30)
        listing.raise_for_status()
        scope['identity_document_sha256'] = hashlib.sha256(listing.content).hexdigest()
        soup = BeautifulSoup(listing.content, 'html.parser')
        headings = [h for h in soup.find_all('h2') if h.get_text(' ', strip=True) == 'Community Advisory Committee']
        if len(headings) != 1 or not headings[0].find_parent('a'):
            return {**policy, 'committee_policy': {**scope, 'status': 'committee_registry_structure_changed_requires_machine_revalidation'}}
        section = headings[0].find_parent('a').find_next_sibling()
        if section is None or 'accordion-text' not in section.get('class', []):
            return {**policy, 'committee_policy': {**scope, 'status': 'committee_registry_structure_changed_requires_machine_revalidation'}}
        semantic = normalize_text(section.get_text(' ', strip=True))
        scope['identity_section_sha256'] = hashlib.sha256(semantic.encode()).hexdigest()
        if scope['identity_section_sha256'] != CAC_IDENTITY_SECTION_SHA256:
            return {**policy, 'committee_policy': {**scope, 'status': 'committee_registry_changed_requires_machine_revalidation'}}
        return {**policy, 'committee_policy': {**scope, 'status': 'verified_unchanged'}}
    except (requests.RequestException, OSError, ValueError) as error:
        return {**policy, 'committee_policy': {**scope, 'status': 'committee_policy_verification_unavailable_hold', 'error_type': type(error).__name__}}


def _unknown_absent_presence(text, unknown_tokens):
    """An absent name must never disappear merely because it lacks a person ID."""
    held = []
    verbs = re.compile(r'\b(arrived|joined|entered|returned|rejoined|left|departed|exited|disconnected|reconnected)\b', re.I)
    for event in verbs.finditer(text):
        before = text[max(0, event.start()-160):event.start()]
        if not any(re.search(r'\b'+re.escape(token)+r'\b', before, re.I) for token in unknown_tokens):
            continue
        after = text[event.end():event.end()+130]
        # Unknown actor/target wording is uncertainty, not an invisible arrival.
        # Only explicitly abstract phrases can be ignored safely here.
        if ((event[1].casefold() == 'returned' and re.match(r'\s+to\s+(?:the\s+)?(?:discussion|questions)\b', after, re.I))
                or (event[1].casefold() == 'left' and re.match(r'\s+(?:the\s+)?decision\b', after, re.I))):
            continue
        held.append({'offset': event.start(), 'reason': 'unknown_absent_member_physical_event',
                     'source_quote': before+event[0]+after.split('\n')[0],
                     'initial_state_unknown': event[1].casefold() not in {'arrived','joined','entered'}})
    return held


def _active_council(memberships, day):
    return [m for m in memberships if m.get('classification') == 'Council'
            and m.get('start_date') and m['start_date'] <= day
            and (not m.get('end_date') or m['end_date'] >= day)]


def inspect_committee_motion(motion, source, *, meeting, people, memberships, policy):
    """Return a complete source-proven CAC ballot or a documentary hold.

    source is the original PDF/structural HTML returned by load_official_minutes.
    Callers must retain its source binary/hash and must CAS existing votes before
    persisting. A successful result observes committee membership only on the
    source date; it must never create an inferred multi-year membership record.
    """
    result = {'motion_id': motion['id'], 'meeting_id': motion['meeting_id'],
              'result': motion['result'], 'source_date_evidence': source.get('source_date_evidence')}
    def hold(status, **details):
        return {**result, 'status': status, **details}
    if source.get('error'):
        return hold(source['error'])
    if motion['meeting_id'] != meeting['id']:
        return hold('source_meeting_mismatch')
    if meeting.get('municipality_slug') != 'langford' or policy.get('municipality_slug') != 'langford':
        return hold('municipality_recording_rule_not_validated')
    header = source.get('source_header', '')
    if source.get('source_classification') != 'Committee' or not re.search(r'\bCommunity Advisory Committee\b', header, re.I):
        return hold('committee_source_scope_not_validated')
    if not re.match(r'https://(?:www\.)?langford\.ca/|https://pub-langford\.escribemeetings\.com/', source.get('source_url') or ''):
        return hold('committee_official_source_url_missing')
    day = source.get('local_date')
    if not day:
        return hold('source_date_unknown')
    if abs((date.fromisoformat(day) - date.fromisoformat(meeting['meeting_date'][:10])).days) > 1:
        return hold('source_meeting_date_mismatch')
    committee_policy = policy.get('committee_policy')
    if committee_policy is not None:
        if committee_policy.get('status') != 'verified_unchanged':
            return hold(committee_policy.get('status', 'committee_policy_verification_unavailable_hold'))
        if (committee_policy.get('terms_sha256') != CAC_SOURCES['terms_2024']['sha256']
                or committee_policy.get('identity_section_sha256') != CAC_IDENTITY_SECTION_SHA256):
            return hold('committee_policy_evidence_not_bound')
    else:
        committee_policy = {'status': 'historically_verified_snapshot', 'enabled_from': '2023-02-21',
                            'enabled_through': CAC_SOURCES['identity_listing']['validated_as_of'],
                            'validated_as_of': CAC_SOURCES['identity_listing']['validated_as_of']}
    if not committee_policy['enabled_from'] <= day <= min(committee_policy['enabled_through'], '2026-12-31'):
        return hold('committee_identity_and_terms_date_not_validated')
    candidates = source_motion_candidates(source, motion['text_content'])
    bound = bound_source_motion(motion, source, meeting['id'])
    if len(candidates) != 1 and bound is None:
        return hold('source_motion_not_exact_or_ambiguous', exact_candidates=len(candidates))
    block = bound if bound is not None else candidates[0]
    view = operative_view(source, block)
    if view and view['status'] == 'documentary_event_only_held':
        return hold('source_documentary_event_not_resolution')
    if view:
        result['operative_motion_body'] = operative_proof(source, block)
    if bound is not None:
        result['source_motion_identity'] = {**source_identity(meeting['id'], source, bound), 'validation':'current_binary_meeting_offset_order_body_and_recomputed_key'}
    family = outcome_family(block['result'])
    if family != outcome_family(motion['result']):
        return hold('outcome_conflict')
    if family not in ('passed', 'failed'):
        return hold('not_a_yes_no_decision')
    quote = source['roster_quote']
    # Vice-Chair is a known role annotation, not an unknown person's name.
    roster, unknown = validate_roster_entries(re.sub(r'\bVice[- ]Chair\b', 'Chair', quote, flags=re.I), people)
    if unknown or not roster:
        return hold('committee_full_identity_not_proven', unknown=unknown)
    text = source['text']
    absent = re.search(r'\bABSENT\s*:?([\s\S]*?)(?=\bATTENDING\b|Meeting available|\n\s*1\.|$)', text[:6000], re.I)
    absent_people = []
    absent_quote = absent[1].strip() if absent else ''
    absent_unknown = []
    if absent:
        _, absent_unknown = validate_roster_entries(absent_quote, people)
        absent_people, _ = resolve_people(absent[1], people)
        conflict = {p['id'] for p in roster} & {p['id'] for p in absent_people}
        if conflict:
            return hold('committee_roster_present_absent_conflict', person_ids=sorted(conflict))
    active_council = _active_council(memberships, day)
    active_ids = {m['person_id'] for m in active_council}
    mayors = {m['person_id'] for m in active_council if (m.get('role') or '').casefold() == 'mayor'}
    eligible, excluded, observations = [], [], []
    initial_ids = {p['id'] for p in roster}
    observed_people = {p['id']: p for p in roster + absent_people}
    for person in observed_people.values():
        name = normalize_text(person['name'])
        if name in CAC_COUNCILLORS:
            if person['id'] not in active_ids:
                return hold('committee_councillor_office_not_proven', person_id=person['id'])
            evidence = 'formal_council_appointment_and_official_dated_member_roster'
        elif name in CAC_CITIZENS:
            if name == 'jacqui whiteway' and not '2024-07-15' <= day <= '2026-12-31':
                return hold('committee_appointment_date_conflict', person_id=person['id'])
            evidence = 'official_dated_member_roster_with_independent_full_identity'
        elif person['id'] in mayors:
            # The primary dated roster must explicitly identify that office.
            mayor_lines = [line for line in quote.splitlines() if re.search(r'(?<!Acting )\bMayor\b', line, re.I)]
            matches = [line for line in mayor_lines if person in resolve_people(line, people)[0]]
            if len(mayors) != 1 or len(matches) != 1:
                return hold('committee_exofficio_mayor_not_proven')
            evidence = 'POL0163_section13_and_dated_mayor_office'
        elif person['id'] in active_ids:
            excluded.append({'person_id': person['id'], 'reason': 'nonmember_visiting_councillor_POL0163_section14'})
            continue
        else:
            if person['id'] in initial_ids:
                return hold('committee_full_identity_not_proven', person_id=person['id'])
            continue  # Unknown absent identity cannot vote if later arrival occurs.
        eligible.append(person)
        observations.append({'person_id': person['id'], 'name': person['name'], 'observed_date': day,
                             'evidence': evidence, 'source_quote': quote if person['id'] in initial_ids else absent_quote,
                             'source_sha256': source['source_sha256'], 'observed_attendance': 'present' if person['id'] in initial_ids else 'absent', 'creates_term_interval': False})
    # Chair/Vice-Chair must be Council members and explicitly labeled in the
    # original roster; no inference from the usual rotation or chairing habits.
    chair_ids = set()
    for line in quote.splitlines():
        if re.search(r'\bChair\b', line, re.I):
            chair_ids.update(p['id'] for p in resolve_people(line, eligible)[0]
                             if normalize_text(p['name']) in CAC_COUNCILLORS)
    positions = [source['text'].find(block['source_block'])]
    if positions[0] < 0:
        return hold('source_offset_unknown')
    cutoff = positions[0] + block['source_block'].find(block['outcome_quote'])
    # Parse all identity-corroborated citizen arrivals, including members initially
    # ABSENT. A person arriving without a member observation is held below.
    timeline_people = {p['id']: p for p in people if normalize_text(p['name']) in CAC_CITIZENS | CAC_COUNCILLORS}
    timeline_people.update({p['id']: p for p in eligible + absent_people
                            if p['id'] not in {e['person_id'] for e in excluded}})
    events, held = physical_presence_events(text, list(timeline_people.values()))
    held.extend(_unknown_absent_presence(text, absent_unknown))
    earlier_held = [e for e in held if e['offset'] < cutoff or e.get('initial_state_unknown')]
    if earlier_held:
        return hold('unparsed_presence_event', events=earlier_held)
    present, adjustments = voters_before_vote(initial_ids & {p['id'] for p in eligible}, events, cutoff)
    if present is None:
        return hold('initial_presence_unknown', events=adjustments)
    if not present <= {p['id'] for p in eligible}:
        return hold('committee_member_observation_unavailable', person_ids=sorted(present - {p['id'] for p in eligible}))
    # Up to nine appointed members: five non-exofficio members is a conservative
    # quorum, even during a vacancy. The Mayor cannot supply the fifth appointee.
    if len(present - mayors) < 5 or len(present) > 10 or not present & chair_ids:
        return hold('committee_quorum_or_chair_not_proven')
    named = {}
    for declaration in named_vote_declarations(block):
        if declaration.get('unparsed'):
            return hold('unparsed_source_choice_declaration', source_quote=declaration['source_quote'])
        resolved, unknown = validate_roster_entries(declaration['names'], eligible)
        if unknown or not resolved:
            return hold('unresolved_dissent_names', unknown=unknown or [declaration['names']])
        if declaration.get('declared_count') is not None and declaration['declared_count'] != len(resolved):
            return hold('explicit_rollcall_count_mismatch')
        for person in resolved:
            pid = person['id']
            if pid not in present:
                return hold('named_choice_voter_not_present', person_id=pid)
            if declaration['vote'] not in ('Yes', 'No'):
                return hold('special_vote_or_recusal_needs_scope')
            if pid in named and named[pid]['vote'] != declaration['vote']:
                return hold('conflicting_named_source_choices')
            named[pid] = {'vote': declaration['vote'], 'source_quote': declaration['source_quote']}
    unanimous = 'UNANIMOUS' in block['result']
    if unanimous and any(v['vote'] != 'Yes' for v in named.values()):
        return hold('unanimous_result_conflicts_with_named_choice')
    explicit_complete = set(named) == present
    if not explicit_complete and not unanimous:
        if policy.get('policy_status') != 'verified_unchanged':
            return hold(policy.get('policy_status', 'recording_rule_not_refreshed'))
        if not policy.get('enabled_from', '9999') <= day <= policy.get('enabled_through', ''):
            return hold('recording_rule_date_not_validated')
    if re.search(r'extend.*meeting|reconsider|sustain.*chair|presiding|appeal.*chair|chair.*appeal|ruling.*chair', block['motion_text'], re.I):
        return hold('special_voting_threshold_needs_validation')
    by_id = {p['id']: p for p in eligible}
    votes = [{'person_id': pid, 'person_name': by_id[pid]['name'],
              'vote': named.get(pid, {}).get('vote', 'Yes'),
              'source_quote': named.get(pid, {}).get('source_quote', block['outcome_quote']),
              'evidence': 'explicit_named' if pid in named else 'inferred_explicit_unanimity' if unanimous else 'inferred_official_dissent_recording_rule'}
             for pid in sorted(present)]
    yes = sum(v['vote'] == 'Yes' for v in votes)
    no = len(votes) - yes
    if (family == 'passed') != (yes > no):
        return hold('reconstructed_tally_conflicts_with_outcome', yes=yes, no=no)
    return {**result, 'status': 'reconstructable_candidate', 'votes': votes, 'yes': yes, 'no': no,
            'source_classification': 'Community Advisory Committee', 'voting_body': 'community_advisory_committee',
            'outcome_role': 'committee_guidance_or_recommendation', 'scope_basis': {**CAC_SOURCES, 'validation': committee_policy},
            'committee_policy_validation': committee_policy,
            'membership_evidence': 'official_dated_committee_member_observation',
            'member_observations': observations, 'excluded_nonvoting_attendees': excluded,
            'committee_chair_person_ids': sorted(chair_ids), 'committee_quorum_minimum_appointees': 5,
            'inference_basis': 'every_present_voter_explicitly_named' if explicit_complete else None,
            'source_result': block['result'], 'source_motion_text': block['motion_text'],
            'source_block': block['source_block'], 'roster_quote': quote,
            'presence_events': [e for e in events if e['offset'] < cutoff], 'initial_arrival_adjustments': adjustments,
            **{key: source[key] for key in ('source_file', 'source_format', 'source_url', 'source_sha256', 'stored_date')},
            'source_date': day}
