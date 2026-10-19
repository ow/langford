"""Prepare/apply reviewed native text corrections without changing vote rows.

Default is read-only. Apply uses complete before-row CAS, original source hashes,
the frozen independent identity review, and a durable precommit receipt.
Rollback is allowed only while every affected after-value still matches.
"""
from collections import defaultdict
from datetime import datetime, timezone
from datetime import date
from pathlib import Path
import argparse
import hashlib
import json

import psycopg2
from psycopg2.extras import Json, RealDictCursor

from pipeline import config
from pipeline.ingestion.official_ballots import load_official_minutes
from pipeline.ingestion.vote_evidence import normalize_text, outcome_family
from pipeline.ingestion.matter_lifecycle import lifecycle_evidence

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
PLAN = OUT / 'canonical-text-recovery-plan.json'
RECEIPT = OUT / 'canonical-text-recovery-applied-receipt.json'
PENDING = OUT / 'canonical-text-recovery-pending-receipt.json'
INPUTS = ['canonical-motion-legacy-mapping-proposals.json',
          'canonical-official-motion-inventory.json',
          'canonical-nonexact-independent-review.json']
MOTION_COLUMNS = 'id,meeting_id,agenda_item_id,text_content,result,meta,updated_at'
VOTE_COLUMNS = 'id,motion_id,person_id,vote,recusal_reason,created_at,updated_at'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def serial(value):
    return json.loads(json.dumps(value, default=str))


def save(path, value):
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(serial(value), indent=2) + '\n')
    temporary.replace(path)


def source_guard(change):
    assert digest(ROOT / change['source_file']) == change['source_sha256'], 'native_source_changed'


def locked_rows(cur, change, expected_key):
    cur.execute(f'SELECT {MOTION_COLUMNS} FROM motions WHERE id=%s FOR UPDATE', (change['motion_id'],))
    assert serial(dict(cur.fetchone())) == change[expected_key], 'motion_changed_since_review'
    cur.execute(f'SELECT {VOTE_COLUMNS} FROM votes WHERE motion_id=%s ORDER BY id FOR UPDATE', (change['motion_id'],))
    assert serial(list(cur.fetchall())) == change['before_votes'], 'vote_rows_changed_since_review'


def prepare(cur):
    assert not RECEIPT.exists() and not PENDING.exists(), 'preserve_existing_receipt'
    review = json.loads((OUT / INPUTS[2]).read_text())
    proposals = json.loads((OUT / INPUTS[0]).read_text())
    canonical = json.loads((OUT / INPUTS[1]).read_text())
    assert review['input_sha256'][INPUTS[0]] == digest(OUT / INPUTS[0]), 'mapping_review_input_changed'
    assert review['input_sha256'][INPUTS[1]] == digest(OUT / INPUTS[1]), 'native_inventory_review_changed'
    eligible = {r['legacy_motion_id']: r for r in review['records'] if r['literal_replacement_eligible']}
    assert len(eligible) == 106
    proposed = {r['legacy_motion_id']: r for r in proposals['mappings'] if r['legacy_motion_id'] in eligible}
    native = {r['canonical_source_motion_key']: r for r in canonical['canonical_motions']}
    ids = sorted(eligible)
    cur.execute(f'SELECT {MOTION_COLUMNS} FROM motions WHERE id=ANY(%s) ORDER BY id', (ids,))
    rows = {r['id']: serial(dict(r)) for r in cur.fetchall()}
    assert len(rows) == len(ids), 'motion_inventory_changed'
    cur.execute(f'SELECT {VOTE_COLUMNS} FROM votes WHERE motion_id=ANY(%s) ORDER BY id', (ids,))
    votes = defaultdict(list)
    for vote in cur.fetchall():
        votes[vote['motion_id']].append(serial(dict(vote)))
    cur.execute('SELECT id,name FROM people ORDER BY id')
    people = list(cur.fetchall())
    current = json.loads((OUT / 'ballot-source-current-snapshot.json').read_text())
    meetings = {m['id']: m for m in current['meetings']}
    sources = {}
    changes, skipped, held = [], [], []
    for mid in ids:
        old, proposal, approval = rows[mid], proposed[mid], eligible[mid]
        node = native[proposal['canonical_source_motion_key']]
        try:
            assert node['source_file'] == proposal['source_file'] == approval['source_file']
            assert digest(ROOT / node['source_file']) == node['source_sha256'] == proposal['source_sha256']
            assert hashlib.sha256(proposal['official_motion_text'].encode()).hexdigest() == approval['source_body_sha256']
            assert old['meeting_id'] == proposal['meeting_id'] == node['meeting_id']
            if old['meeting_id'] not in sources:
                sources[old['meeting_id']] = load_official_minutes(
                    meetings[old['meeting_id']], root=ROOT, people=people,
                    cache_dir=Path('/private/tmp/canonical-text-recovery-native'))
            source = sources[old['meeting_id']]
            assert not source.get('error'), source.get('error')
            assert source['source_sha256'] == node['source_sha256']
            assert source.get('local_date'), 'native_header_date_not_yet_proven'
            assert abs((date.fromisoformat(source['local_date']) - date.fromisoformat(meetings[old['meeting_id']]['meeting_date'][:10])).days) <= 1, 'native_header_and_catalog_date_conflict'
            blocks = source['index'].get(normalize_text(proposal['official_motion_text']), [])
            assert len(blocks) == 1, 'current_native_boundary_not_exact_unique_reviewed_body'
            block = blocks[0]
            assert outcome_family(block['result']) == outcome_family(node['source_result']), 'native_outcome_review_differs'
            if old['result']:
                assert outcome_family(old['result']) == outcome_family(block['result']), 'existing_outcome_conflict'
            new_result = old['result'] or block['result']
            if normalize_text(old['text_content']) == normalize_text(block['motion_text']) and old['result'] == new_result:
                skipped.append({'motion_id': mid, 'reason': 'already_exact_official_body_and_result'})
                continue
            assert old['text_content'] == proposal['original_motion_text'], 'legacy_text_changed_since_identity_review'
            assert (old['meta'] or {}).get('individual_vote_coverage') != 'reconstructed_complete', 'complete_ballot_requires_separate_body_proof_refresh'
            provenance = {
                'original_motion_text': old['text_content'], 'original_result': old['result'],
                'official_motion_text': block['motion_text'], 'official_result': block['result'],
                'source_file': source['source_file'], 'source_url': source['source_url'],
                'source_sha256': source['source_sha256'], 'source_block': block['source_block'],
                'source_date': source['local_date'], 'source_date_evidence': source.get('source_date_evidence'),
                'canonical_inventory_key': proposal['canonical_source_motion_key'],
                'identity_review_sha256': digest(OUT / INPUTS[2]),
                'source_boundary_check': 'unique_entire_reviewed_native_body_and_same_first_formal_outcome',
                'agenda_item_id_preserved': old['agenda_item_id'],
            }
            new_meta = {**(old['meta'] or {}), 'source_motion_correction': provenance}
            if not old['result']:
                new_meta['vote_record'] = {**new_meta.get('vote_record', {}),
                    'outcome_validation': 'exact_native_source_after_independent_identity_review',
                    'outcome_source_quote': block['outcome_quote']}
            changes.append({'motion_id': mid, 'before_motion': old, 'before_votes': votes[mid],
                'after_text': block['motion_text'], 'after_result': new_result, 'after_meta': new_meta,
                'source_file': source['source_file'], 'source_sha256': source['source_sha256']})
        except AssertionError as error:
            held.append({'motion_id': mid, 'reason': str(error)})
    cur.execute('SELECT DISTINCT a.matter_id FROM agenda_items a JOIN motions m ON m.agenda_item_id=a.id WHERE m.id=ANY(%s) AND a.matter_id IS NOT NULL', ([c['motion_id'] for c in changes],))
    matterids = [r['matter_id'] for r in cur.fetchall()]
    cur.execute('SELECT id,title,identifier,status,meta FROM matters WHERE id=ANY(%s)', (matterids,))
    matters = serial(list(cur.fetchall()))
    stale = []
    for matter in matters:
        evidence_id = (matter['meta'] or {}).get('lifecycle_evidence', {}).get('motion_id')
        change = next((c for c in changes if c['motion_id'] == evidence_id), None)
        if change and not lifecycle_evidence(matter, {**change['before_motion'], 'text_content': change['after_text'], 'result': change['after_result']}):
            stale.append(matter['id'])
    plan = {'mode': 'read_only_prepared', 'created_at': datetime.now(timezone.utc).isoformat(),
        'apply_script_sha256': digest(Path(__file__)), 'input_sha256': {n: digest(OUT / n) for n in INPUTS},
        'changes': changes, 'skipped': skipped, 'held': held, 'affected_matters': matters,
        'stale_lifecycle_matter_ids': stale,
        'summary': {'eligible_reviewed_identities': len(eligible), 'motion_text_corrections': len(changes),
            'literal_recorded_results_restored': sum(not c['before_motion']['result'] for c in changes),
            'already_corrected': len(skipped), 'held': len(held), 'vote_rows_preserved': sum(len(c['before_votes']) for c in changes),
            'agenda_relinks': 0, 'vote_mutations': 0, 'stale_lifecycle_matters': len(stale)}}
    save(PLAN, plan)
    print(json.dumps(plan['summary']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--rollback', action='store_true')
    parser.add_argument('--expected-plan-sha256', help='Exact independently reviewed plan bytes; required for apply')
    args = parser.parse_args()
    with psycopg2.connect(config.DATABASE_URL, connect_timeout=20) as db:
        db.set_session(isolation_level='SERIALIZABLE')
        with db.cursor(cursor_factory=RealDictCursor) as cur:
            if args.rollback:
                receipt = json.loads(RECEIPT.read_text())
                assert receipt['mode'] == 'applied'
                for change in receipt['changes']:
                    locked_rows(cur, change, 'after_motion')
                    before = change['before_motion']
                    cur.execute('UPDATE motions SET text_content=%s,result=%s,meta=%s WHERE id=%s',
                        (before['text_content'], before['result'], Json(before['meta']), change['motion_id']))
                db.commit()
                receipt['rolled_back_at'] = datetime.now(timezone.utc).isoformat()
                save(RECEIPT, receipt)
                print('Guarded rollback complete')
            elif args.apply:
                assert not RECEIPT.exists() and not PENDING.exists(), 'existing_or_uncertain_receipt_requires_readback'
                plan_bytes = PLAN.read_bytes()
                plan_sha256 = hashlib.sha256(plan_bytes).hexdigest()
                assert args.expected_plan_sha256 == plan_sha256, 'exact_reviewed_plan_sha256_required'
                plan = json.loads(plan_bytes)
                assert plan['apply_script_sha256'] == digest(Path(__file__)), 'applier_changed'
                assert not plan['stale_lifecycle_matter_ids'], 'affected_matter_lifecycle_review_required'
                for name, sha in plan['input_sha256'].items():
                    assert digest(OUT / name) == sha, 'review_input_changed'
                for change in plan['changes']:
                    source_guard(change)
                    locked_rows(cur, change, 'before_motion')
                for change in plan['changes']:
                    cur.execute(f'UPDATE motions SET text_content=%s,result=%s,meta=%s WHERE id=%s RETURNING {MOTION_COLUMNS}',
                        (change['after_text'], change['after_result'], Json(change['after_meta']), change['motion_id']))
                    change['after_motion'] = serial(dict(cur.fetchone()))
                receipt = {**plan, 'mode': 'pending_commit', 'plan_sha256': plan_sha256,
                    'applied_at': datetime.now(timezone.utc).isoformat()}
                save(PENDING, receipt)
                db.commit()
                receipt['mode'] = 'applied'
                save(RECEIPT, receipt)
                print(json.dumps(receipt['summary']))
            else:
                prepare(cur)
                db.rollback()


if __name__ == '__main__':
    main()
