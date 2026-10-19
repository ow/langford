"""Source-first motion identities and non-destructive refresh planning.

AI proposals enrich exact formal source motions. They cannot introduce a motion,
change its operative words, or erase a previously persisted record. Unresolved
legacy identities block new inserts rather than manufacture duplicates.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date
import hashlib
import json
import re

from .vote_evidence import normalize_text
from .ballot_reconstruction import validate_roster_entries


def source_identity(meeting_id, source, block):
    identity = {'meeting_id': meeting_id, 'source_sha256': source['source_sha256'],
                'source_offset': block['source_offset'], 'source_order': block['source_order']}
    return {**identity, 'key': hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest(),
            'source_file': source['source_file'], 'source_url': source.get('source_url'),
            'source_format': source['source_format'], 'raw_motion_text': block['motion_text'],
            'source_block': block['source_block'], 'outcome_quote': block['outcome_quote'],
            'formal_source_kind': block.get('formal_source_kind', 'moved_motion')}


def bound_source_motion(motion, source, meeting_id):
    """Resolve only a current, recomputed documentary occurrence identity.

    Repeated words alone cannot distinguish two ballots. Historical keys are
    continuity evidence, never permission to choose a different occurrence.
    """
    identity = (motion.get('meta') or {}).get('canonical_source_motion') or {}
    if motion.get('meeting_id') != meeting_id or identity.get('meeting_id') != meeting_id:
        return None
    if not source.get('source_sha256') or identity.get('source_sha256') != source['source_sha256']:
        return None
    matches = []
    for block in source.get('blocks', []):
        if identity.get('source_offset') != block['source_offset'] or identity.get('source_order') != block['source_order']:
            continue
        body = normalize_text(block['motion_text'])
        if not body or normalize_text(identity.get('raw_motion_text')) != body or normalize_text(motion.get('text_content')) != body:
            continue
        payload = {'meeting_id': meeting_id, 'source_sha256': source['source_sha256'],
                   'source_offset': block['source_offset'], 'source_order': block['source_order']}
        key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if identity.get('key') == key:
            matches.append(block)
    return matches[0] if len(matches) == 1 else None


def catalog_cac_candidate(meeting):
    """Known Langford generic catalog labels still require the native CAC title."""
    title = normalize_text(meeting.get('title'))
    path = meeting.get('archive_path', '').replace('\\', '/')
    named = bool(re.search(r'community\s+advisory\s+committee', meeting.get('title', '')+' '+path, re.I))
    generic = title in {'advisory committee', 'joint advisory committee'} or bool(re.search(r'(?:^|/)(?:Joint|Community) Advisory Committee(?:/|$)', path, re.I))
    return named or (meeting.get('classification') in ('Committee', 'Advisory Committee') and generic)


def canonical_motion_plan(items, context, existing_motions):
    """Plan unique exact legacy bindings; leave uncertain history untouched.

    Source revisions can reuse an old ID only through an exact unique body or
    an exact previously recorded source key. No source-order-only or fuzzy
    association is safe when an official document has been replaced.
    """
    items = deepcopy(items)
    for item in items:
        item['_unverified_motion_proposals'] = item.pop('motions', [])
        item['motions'] = []
    source = context.get('source') or {}
    if context.get('status') != 'available' or source.get('error'):
        return items, {'status': source.get('error') or context.get('status'), 'held': [], 'source_motions': 0}
    # Ballot eligibility may be held separately, but source/document binding is
    # still required before its formal words can become a canonical motion.
    meeting = context['meeting']
    if not source.get('local_date') or abs((date.fromisoformat(source['local_date']) - date.fromisoformat(meeting['meeting_date'])).days) > 1:
        return items, {'status': 'source_date_not_bound', 'held': [], 'source_motions': 0}
    body_old = defaultdict(list)
    key_old = defaultdict(list)
    for row in existing_motions:
        body_old[normalize_text(row.get('text_content'))].append(row)
        identity = (row.get('meta') or {}).get('canonical_source_motion') or {}
        for key in [identity.get('key'), *identity.get('previous_keys', [])]:
            if key:
                key_old[key].append(row)
    catalog_cotw = bool(re.search(r'committee\s+of\s+the\s+whole|\bCOTW\b', meeting.get('title', '')+' '+meeting.get('archive_path', ''), re.I))
    catalog_cac = catalog_cac_candidate(meeting)
    native_cac = bool(re.search(r'community\s+advisory\s+committee', source.get('source_header', ''), re.I))
    expected_body = 'Committee' if catalog_cac and native_cac else 'Committee of the Whole' if catalog_cotw else meeting.get('classification')
    allowed_bodies = ('Council', 'Committee of the Whole', 'Committee') if catalog_cac and native_cac else ('Council', 'Committee of the Whole')
    if source.get('source_classification') not in allowed_bodies or source.get('source_classification') != expected_body:
        return items, {'status': 'source_voting_body_not_bound', 'held': [], 'source_motions': 0}
    blocks = source.get('blocks', [])
    body_counts = Counter(normalize_text(block['motion_text']) for block in blocks)
    bindings = []
    for block in blocks:
        identity = source_identity(meeting['id'], source, block)
        choices = key_old.get(identity['key']) or body_old.get(normalize_text(block['motion_text']), [])
        if body_counts[normalize_text(block['motion_text'])] > 1:
            choices = [row for row in existing_motions if bound_source_motion(row, source, meeting['id']) is block]
        bindings.append((block, identity, choices))
    bound_ids = {choices[0]['id'] for block, identity, choices in bindings if len(choices) == 1 and (body_counts[normalize_text(block['motion_text'])] == 1 or bound_source_motion(choices[0], source, meeting['id']) is block) and normalize_text(choices[0].get('text_content')) == normalize_text(block['motion_text'])}
    unresolved = [row['id'] for row in existing_motions if row['id'] not in bound_ids]
    all_current_bound = all(bound_source_motion(row, source, meeting['id']) is not None for row in existing_motions)
    held = []
    for block, identity, choices in bindings:
        key = normalize_text(block['motion_text'])
        new_current_occurrence = not choices and not unresolved and all_current_bound
        if len(choices) > 1 or (body_counts[key] != 1 and not new_current_occurrence and (len(choices) != 1 or bound_source_motion(choices[0], source, meeting['id']) is not block)):
            held.append({'source_key': identity['key'], 'reason': 'ambiguous_legacy_or_source_body'})
            continue
        if not choices and unresolved:
            held.append({'source_key': identity['key'], 'reason': 'unmapped_legacy_records', 'legacy_ids': unresolved})
            continue
        old = choices[0] if choices else None
        if old and normalize_text(old['text_content']) != key:
            held.append({'source_key': identity['key'], 'reason': 'source_key_body_conflict', 'legacy_ids': [old['id']]})
            continue
        enrichments = [(item, proposal) for item in items for proposal in item['_unverified_motion_proposals'] if normalize_text(proposal.get('motion_text')) == key]
        if len(enrichments) == 1:
            item, proposal = enrichments[0]
        else:
            # An explicit source container avoids guessing an agenda number from
            # addresses, numbered conditions, or a model's renumbered headings.
            item = next((item for item in items if item.get('item_order') == 'official-recorded-motions'), None)
            if item is None:
                item = {'item_order': 'official-recorded-motions', 'title': 'Official recorded motions', 'category': 'procedural', 'motions': [], '_unverified_motion_proposals': []}
                items.append(item)
            proposal = {}
        source_header = block['source_block'].split(block['motion_text'], 1)[0]
        def actor(role):
            prefix = r'(?:Amendment[ \t]*:[ \t]*|\.[ \t]*)?' if role == 'MOVED' else ''
            match = re.search(r'(?im)^\s*'+prefix+role+r'(?:\s+BY)?\s*:\s*([^\n]+)', source_header)
            return match[1].strip() if match else None
        actor_ids = {}
        actor_names = {}
        for field, role in (('mover', 'MOVED'), ('seconder', 'SECONDED')):
            raw_actor = actor(role)
            resolved, ambiguous = validate_roster_entries(raw_actor or '', source.get('present', []))
            person = resolved[0] if len(resolved) == 1 and not ambiguous else None
            actor_ids[field] = person['id'] if person else None
            actor_names[field] = person['name'] if person else raw_actor
        motion = {**proposal, 'motion_text': block['motion_text'], 'result': block['result'],
                  **actor_names, '_canonical_actor_ids': actor_ids,
                  '_canonical_source_motion': identity, '_existing_motion': old,
                  '_source_motion': {**block, 'anchor_method': 'canonical_native_formal_motion', 'match_score': 1.0}}
        if old:
            old_identity = (old.get('meta') or {}).get('canonical_source_motion') or {}
            previous = list(old_identity.get('previous_keys', []))
            if old_identity.get('key') and old_identity['key'] != identity['key']:
                previous.append(old_identity['key'])
            identity['previous_keys'] = sorted(set(previous))
            history = list(old_identity.get('previous_sources', []))
            if old_identity.get('key') and old_identity['key'] != identity['key']:
                history.append({field: old_identity.get(field) for field in ('key', 'source_sha256', 'source_file', 'source_url', 'source_format', 'source_offset', 'source_order', 'raw_motion_text', 'source_block', 'outcome_quote')})
            identity['previous_sources'] = history[-8:]
        item['motions'].append(motion)
    # Count unbound native outcome markers as source-coverage leads. A clerk's
    # hearing-closure vote or an unfamiliar formal delimiter is not permission
    # to manufacture a motion, but it must not disappear from the audit either.
    bound_outcomes = []
    text = source.get('text', '')
    for block in blocks:
        start = text.find(block['source_block'], block['source_offset'])
        if start >= 0:
            outcome_start = text.find(block['outcome_quote'], start, start+len(block['source_block']))
            if outcome_start >= 0:
                bound_outcomes.append((outcome_start, outcome_start+len(block['outcome_quote'])))
    unbound_outcomes = []
    for marker in re.finditer(r'(?im)^[ \t]*(?:Motion[ \t]+)?(?:NOT CARRIED|CARRIED(?:[ \t]+UNANIMOUSLY)?|DEFEATED|WITHDRAWN|TABLED)\b[^\n]*', text):
        if not any(marker.start() < stop and start < marker.end() for start, stop in bound_outcomes):
            unbound_outcomes.append({'source_offset':marker.start(), 'source_quote':marker[0].strip()})
    return items, {'status': 'source_authoritative', 'source_motions': len(blocks), 'held': held, 'unmapped_legacy_ids': unresolved,
                   'unbound_outcome_leads': unbound_outcomes,
                   'mapped_motions': sum(len(item['motions']) for item in items)}


def existing_agenda_item(item, existing_items):
    """Only a unique exact order/title can retain an agenda ID automatically."""
    candidates = [old for old in existing_items if str(old.get('item_order') or '') == str(item.get('item_order') or '') and normalize_text(old.get('title')) == normalize_text(item.get('title'))]
    if len(candidates) > 1:
        raise RuntimeError('Ambiguous existing agenda identity; no agenda refresh applied')
    return candidates[0] if candidates else None


def _receipt_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def source_candidate_inventory(root, archive_path):
    """Fingerprint every selector input, including unchosen sources and URL sidecars."""
    from pathlib import Path
    folder = Path(root) / archive_path / 'Minutes'
    return [{'name': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in sorted(folder.iterdir()) if path.is_file() and path.suffix.lower() in ('.pdf', '.html', '.url')] if folder.is_dir() else []


def loaded_ballot_guard_digest():
    """Hash executable objects in this worker, never newer Python files on disk.

    A worker must restart to adopt new imported code. Swift is read by the OCR
    subprocess at execution time, so its current asset bytes are an input too.
    """
    import importlib
    import inspect
    import types
    from pathlib import Path
    modules = ('canonical_motions', 'vote_evidence', 'ballot_reconstruction', 'official_ballots',
               'meeting_ballots', 'committee_ballots', 'vote_policy', 'native_header_ocr')
    guards = {}
    def constant(value):
        if isinstance(value, types.CodeType):
            return {"bytecode": value.co_code.hex(), "constants": constant(value.co_consts),
                    "names": value.co_names, "locals": value.co_varnames, "freevars": value.co_freevars,
                    "cellvars": value.co_cellvars, "argcount": value.co_argcount,
                    "posonly": value.co_posonlyargcount, "kwonly": value.co_kwonlyargcount,
                    "flags": value.co_flags, "exceptions": value.co_exceptiontable.hex()}
        if isinstance(value, bytes):
            return {"bytes": value.hex()}
        if value is Ellipsis:
            return {"ellipsis": True}
        if isinstance(value, re.Pattern):
            return {'pattern': value.pattern, 'flags': value.flags}
        if isinstance(value, (str, int, float, bool, type(None))):
            return value
        if isinstance(value, (tuple, list)):
            return [constant(item) for item in value]
        if isinstance(value, (set, frozenset)):
            return sorted((constant(item) for item in value), key=str)
        if isinstance(value, dict):
            return {str(key): constant(item) for key, item in value.items()}
        raise TypeError
    for name in modules:
        module = importlib.import_module(f'{__package__}.{name}')
        values = {}
        for key, value in vars(module).items():
            if inspect.isfunction(value) and value.__module__ == module.__name__:
                values[key] = {'code': constant(value.__code__), 'defaults': constant(value.__defaults__), 'kwdefaults': constant(value.__kwdefaults__)}
            elif isinstance(value, re.Pattern) or key.isupper():
                try:
                    values[key] = constant(value)
                except TypeError:
                    pass
        guards[name] = values
    guards['native_header_vision.swift'] = hashlib.sha256((Path(__file__).parent / 'native_header_vision.swift').read_bytes()).hexdigest()
    return _receipt_digest(guards)


def source_validation_inputs(context, inventory):
    """Stable semantic evidence: daily policy checks and avatars cannot bust caches."""
    day = str(context.get('source', {}).get('local_date') or context.get('meeting', {}).get('meeting_date') or '')[:10]
    def policy_evidence(value):
        if isinstance(value, dict):
            result = {key: policy_evidence(item) for key, item in value.items()
                      if key not in ('validated_as_of', 'checked_as_of', 'checked_date', 'enabled_through', 'identity_document_sha256')}
            if 'enabled_through' in value:
                result['covers_meeting_date'] = bool(day and value.get('enabled_from', '') <= day <= value['enabled_through'])
            return result
        if isinstance(value, list):
            return [policy_evidence(item) for item in value]
        return value
    people = [{key: row.get(key) for key in ('id', 'name')} for row in context.get('people', [])]
    memberships = [{key: row.get(key) for key in ('person_id', 'name', 'role', 'start_date', 'end_date', 'classification', 'organization_id')} for row in context.get('memberships', [])]
    semantic = {'context_status': context.get('status'), 'error_type': context.get('error_type'),
                'meeting': {key: context.get('meeting', {}).get(key) for key in ('id', 'meeting_date', 'archive_path', 'classification', 'title', 'type', 'organization_id', 'minutes_url', 'municipality_slug')},
                'people': sorted(people, key=lambda row: str(row['id'])),
                'memberships': sorted(memberships, key=lambda row: json.dumps(row, sort_keys=True, default=str)),
                'policy': policy_evidence(context.get('policy', {}))}
    source = context.get('source', {})
    # Extraction environments and OCR cache availability can change the facts
    # produced by the same PDF and loaded code. Bind the actual derived facts.
    date_evidence = {key: value for key, value in (source.get('source_date_evidence') or {}).items()
                     if key not in ('render_file', 'ocr_receipt')}
    semantic['source'] = {key: source.get(key) for key in ('source_file', 'source_sha256', 'source_url', 'source_format',
        'source_classification', 'local_date', 'stored_date', 'error', 'error_type', 'roster_quote', 'roster_unknown', 'ambiguous_names')}
    semantic['source']['present'] = [{key: person.get(key) for key in ('id', 'name')} for person in source.get('present', [])]
    semantic['source']['text_sha256'] = hashlib.sha256(source.get('text', '').encode()).hexdigest()
    semantic['source']['date_evidence'] = date_evidence
    return {'version': 2, 'guard_sha256': loaded_ballot_guard_digest(),
            'candidate_inventory_sha256': _receipt_digest(inventory), 'evidence_sha256': _receipt_digest(semantic)}


def source_receipt_current(root, metadata, validation_inputs=None):
    """Only a finished receipt for this source AND these validation inputs can skip."""
    from pathlib import Path
    receipt = (metadata or {}).get('motion_source_ingestion') or {}
    if not validation_inputs or receipt.get('validation_inputs') != validation_inputs:
        return False
    if receipt.get('status') != 'source_authoritative' or not receipt.get('source_file'):
        return False
    path = (Path(root) / receipt['source_file']).resolve()
    if not path.is_relative_to(Path(root).resolve()) or not path.is_file():
        return False
    return hashlib.sha256(path.read_bytes()).hexdigest() == receipt.get('source_sha256')


def write_source_receipt(supabase, meeting_id, report, source):
    """Preserve unrelated metadata and expose retryable partial writes honestly."""
    current = supabase.table('meetings').select('meta,updated_at').eq('id', meeting_id).single().execute().data
    if isinstance(current, list):
        current = current[0]
    metadata = {**(current.get('meta') or {}), 'motion_source_ingestion': {
        **report, 'source_sha256': source['source_sha256'], 'source_file': source['source_file'],
    }}
    query = supabase.table('meetings').update({'meta': metadata}).eq('id', meeting_id)
    if current.get('updated_at'):
        query = query.eq('updated_at', current['updated_at'])
    if not query.execute().data:
        raise RuntimeError('Meeting changed concurrently; retry source audit metadata')
