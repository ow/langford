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
        bindings.append((block, identity, choices))
    bound_ids = {choices[0]['id'] for block, identity, choices in bindings if len(choices) == 1 and body_counts[normalize_text(block['motion_text'])] == 1 and normalize_text(choices[0].get('text_content')) == normalize_text(block['motion_text'])}
    unresolved = [row['id'] for row in existing_motions if row['id'] not in bound_ids]
    held = []
    for block, identity, choices in bindings:
        key = normalize_text(block['motion_text'])
        if len(choices) > 1 or body_counts[key] != 1:
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
            match = re.search(r'(?im)^\s*'+role+r'(?:\s+BY)?\s*:\s*([^\n]+)', source_header)
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


def source_receipt_current(root, metadata):
    """A cached success is usable only for the exact completed source binary."""
    from pathlib import Path
    receipt = (metadata or {}).get('motion_source_ingestion') or {}
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
