"""Independent read-only whole-row readback; resolve pending commits without retries."""
import argparse
import hashlib
import json
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor
from pipeline import config


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--receipt', type=Path, required=True)
    cli.add_argument('--expected-receipt-sha256', required=True)
    cli.add_argument('--output', type=Path, required=True)
    args = cli.parse_args()
    raw = args.receipt.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != args.expected_receipt_sha256:
        raise RuntimeError('Exact immutable receipt bytes required')
    receipt = json.loads(raw)
    if receipt['mode'] not in ('applied', 'pending_commit', 'dry_run'):
        raise RuntimeError('Unsupported receipt mode')
    changes = receipt['changes']
    ids = sorted(c['motion_id'] for c in changes)
    if len(ids) != 22 or len(set(ids)) != 22 or set(ids) & {2903, 2908, 3219, 3457, 3459}:
        raise RuntimeError('Exact 22 reviewed ballots required')
    db = psycopg2.connect(config.DATABASE_URL, connect_timeout=15)
    db.set_session(readonly=True, isolation_level='REPEATABLE READ')
    try:
        with db.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT motions.*,meta IS NULL AS meta_is_sql_null FROM motions WHERE id=ANY(%s) ORDER BY id', (ids,))
            motions = json.loads(json.dumps(cur.fetchall(), default=str))
            cur.execute('SELECT * FROM votes WHERE motion_id=ANY(%s) ORDER BY id', (ids,))
            votes = json.loads(json.dumps(cur.fetchall(), default=str))
        db.rollback()
    finally:
        db.close()
    before_motions = sorted((c['before_motion'] for c in changes), key=lambda r: r['id'])
    before_votes = sorted((v for c in changes for v in c['before_votes']), key=lambda r: r['id'])
    before_equal = motions == before_motions and votes == before_votes
    after_equal = False
    if receipt['mode'] in ('applied', 'pending_commit'):
        after_motions = sorted((c['after_motion'] for c in changes), key=lambda r: r['id'])
        after_votes = sorted((v for c in changes for v in c['before_votes'] + c['inserted_votes']), key=lambda r: r['id'])
        after_equal = motions == after_motions and votes == after_votes
        if len(after_votes) != 154 or sum(len(c['inserted_votes']) for c in changes) != 147 or len(before_votes) != 7:
            raise RuntimeError('Receipt choice counts differ')
    state = 'exact_committed_after' if after_equal else 'exact_unchanged_before' if before_equal else 'held_independent_change_or_partial_state'
    if receipt['mode'] == 'applied' and not after_equal:
        raise RuntimeError('Applied receipt does not match independent full-row readback')
    if receipt['mode'] == 'dry_run' and not before_equal:
        raise RuntimeError('Dry-run before rows changed')
    report = {'database_writes': 0, 'receipt_sha256': digest, 'state': state,
              'ballots': len(motions), 'choices': len(votes),
              'entire_motion_rows_equal': after_equal or before_equal,
              'entire_vote_rows_and_ids_equal': after_equal or before_equal,
              'snapshot_sha256': hashlib.sha256(json.dumps({'motions': motions, 'votes': votes}, sort_keys=True).encode()).hexdigest()}
    with args.output.open('x') as f:
        f.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    if state.startswith('held_'):
        raise RuntimeError('Uncertain state requires investigation; never blindly retry')


if __name__ == '__main__':
    main()
