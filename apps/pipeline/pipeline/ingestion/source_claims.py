"""Complete semantic meeting claims and checked ingestion receipt transitions.

Claims are observations, never source authority. No database metadata can enroll
an approved transcription. Full-row CAS belongs to the writer separately.
"""
from copy import deepcopy
import hashlib
import json

CLAIM_COLUMNS = 'id,meeting_id,text_content,result,mover_id,seconder_id,meta'
CLAIM_META_KEYS = ('canonical_source_motion', 'operative_motion_body', 'full_transcription_validation',
                   'source_motion', 'prior_ballot_proof', 'ballot_reconstruction', 'vote_record', 'prior_vote_record',
                   'source_motion_correction', 'canonical_text_restoration', 'canonical_text_restoration_history',
                   'source_legacy_binding', 'pending_ballot_proof', 'source_binding_hold', 'individual_vote_coverage')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def project_claim(row):
    return {**{key: deepcopy(row.get(key)) for key in ('id', 'meeting_id', 'text_content', 'result', 'mover_id', 'seconder_id')},
            'meta': {key: deepcopy((row.get('meta') or {}).get(key)) for key in CLAIM_META_KEYS
                     if key in (row.get('meta') or {})}}


def build_claim_inventory(rows, *, meeting_id, expected_count):
    claims = sorted((project_claim(row) for row in rows), key=lambda row: str(row['id']))
    complete = (isinstance(expected_count, int) and expected_count == len(claims)
                and all(row['id'] is not None and row['meeting_id'] == meeting_id for row in claims)
                and len({row['id'] for row in claims}) == len(claims))
    return {'status': 'complete' if complete else 'meeting_claim_inventory_incomplete',
            'meeting_id': meeting_id, 'expected_count': expected_count,
            'claims': claims, 'fingerprint': digest(claims)}


def valid_inventory(inventory, meeting_id):
    if not isinstance(inventory, dict) or inventory.get('status') != 'complete':
        return False
    rebuilt = build_claim_inventory(inventory.get('claims', []), meeting_id=meeting_id,
                                    expected_count=inventory.get('expected_count'))
    return rebuilt == inventory


def load_claim_inventory(supabase, meeting_id):
    def read_complete():
        rows, count = [], None
        while True:
            result = supabase.table('motions').select(CLAIM_COLUMNS, count='exact').eq('meeting_id', meeting_id).order('id').range(len(rows), len(rows)+999).execute()
            if count is None:
                count = result.count
            elif count != result.count:
                return build_claim_inventory(rows, meeting_id=meeting_id, expected_count=None)
            batch = result.data
            rows.extend(batch)
            if (not isinstance(count, int) or len(rows) > count
                    or len({row.get('id') for row in rows}) != len(rows)):
                return build_claim_inventory(rows, meeting_id=meeting_id, expected_count=None)
            if len(batch) < 1000:
                return build_claim_inventory(rows, meeting_id=meeting_id, expected_count=count)
    # Two complete ordered semantic reads also detect same-count mutations.
    first = read_complete()
    second = read_complete()
    return first if first == second else build_claim_inventory([], meeting_id=meeting_id, expected_count=None)


def intended_claim_transition(before, after, persisted_rows):
    """Verify exact successful writer results, preserving every unrelated claim.

    Callers record actual returned/persisted full rows after each intended write;
    they cannot authorize arbitrary changes by reloading the entire post-state.
    """
    meeting_id = before.get('meeting_id') if isinstance(before, dict) else None
    if not valid_inventory(before, meeting_id) or not valid_inventory(after, meeting_id):
        return False
    expected = {row['id']: row for row in before['claims']}
    for row in persisted_rows:
        claim = project_claim(row)
        if claim['id'] is None or claim['meeting_id'] != meeting_id:
            return False
        expected[claim['id']] = claim
    return sorted(expected.values(), key=lambda row: str(row['id'])) == after['claims']


def intended_inventory(before, persisted_rows):
    if not valid_inventory(before, before.get('meeting_id')):
        raise RuntimeError('Complete initial claims required')
    expected = {row['id']: row for row in before['claims']}
    for row in persisted_rows:
        expected[row['id']] = project_claim(row)
    return build_claim_inventory(list(expected.values()), meeting_id=before['meeting_id'], expected_count=len(expected))


def record_intended_claim_write(before, writes, payload, returned_rows):
    """Bind each returned semantic row to its actual intended mutation payload."""
    expected = {row['id']: row for row in intended_inventory(before, writes)['claims']}
    if len(returned_rows) != 1:
        raise RuntimeError('Expected exactly one persisted motion claim')
    actual = project_claim(returned_rows[0])
    identity = payload.get('id', actual['id'])
    if identity != actual['id'] or identity is None:
        raise RuntimeError('Persisted motion identity differs from intended write')
    prior = expected.get(identity, {})
    intended = project_claim({**prior, **payload, 'id': identity})
    if intended != actual or intended['meeting_id'] != before['meeting_id']:
        raise RuntimeError('Persisted semantic motion claim differs from intended write')
    writes.append(actual)
