"""DRAFT: reviewed PG17 motion-search expression apply/reverse/readback.

Not executed during preparation. Apply requires exact immutable before/review hashes.
Never retry when a pending receipt exists, including after an uncertain commit.
Reverse the search expression before historical full-row restoration rollback.
"""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sys
import time

OWNER = Path(__file__).with_name('motion_search_migration.py')
spec = importlib.util.spec_from_file_location('motion_search_migration', OWNER)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def runtime():
    return {'guarded_runner': m.file_sha(Path(__file__)), 'owner': m.file_sha(OWNER),
            'forward': m.file_sha(m.FORWARD), 'reverse': m.file_sha(m.REVERSE)}

def loaded(path, digest):
    assert path and digest and m.file_sha(path) == digest, 'immutable input hash mismatch'
    return json.loads(path.read_text())

def expected_after(before, target):
    after = copy.deepcopy(before)
    after['expression'] = target
    for column in after['catalog']['columns']:
        if column['attname'] == 'text_search': column['default_expression'] = target
    return after

def validate_probes(probes):
    assert len(probes) == 8
    assert {p['id'] for p in probes if p['field'] == 'body_only'} == {1474,1505,1711,1925,1927,2153,3089}
    assert sum(p['field'] == 'summary_only' for p in probes) == 1
    assert all(isinstance(p['term'], str) and p['term'].strip() for p in probes)
    assert all(1 <= len(p['new_matching_ids']) <= 30 and p['id'] in p['new_matching_ids'] for p in probes)

def post_apply_recall(c, probes):
    validate_probes(probes)
    proof = []
    for probe in probes:
        indexed = m.matching_ids(c, 'public.motions', 'text_search', probe['term'])
        direct = m.matching_ids(c, 'public.motions', m.NEW, probe['term'])
        assert indexed == direct == probe['new_matching_ids'] and probe['id'] in indexed
        c.execute("SELECT id,rank_score FROM public.hybrid_search_motions(%s::text,NULL::halfvec,30::integer,1::float8,0::float8,50::integer,NULL::date,NULL::date,NULL::bigint)", (probe['term'],))
        assert probe['id'] in [row[0] for row in c.fetchall() if row[1] > 0]
        proof.append({'motion_id':probe['id'],'field':probe['field'],'term_sha256':m.sha(probe['term']),'matching_ids_sha256':m.sha(indexed)})
    return proof

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['apply','reverse','readback'])
    p.add_argument('--before', type=Path)
    p.add_argument('--before-sha256')
    p.add_argument('--receipt', type=Path)
    p.add_argument('--receipt-sha256')
    p.add_argument('--rehearsal', type=Path)
    p.add_argument('--rehearsal-sha256')
    p.add_argument('--review', type=Path)
    p.add_argument('--review-sha256')
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    code = runtime()
    if a.mode == 'apply':
        captured = loaded(a.before, a.before_sha256)
        assert captured['code'] == {'runner': code['owner'], 'forward': code['forward'], 'reverse': code['reverse']}
        before = captured['before']; target = m.NEW
        assert before['expression'] == m.OLD
        input_hash = a.before_sha256
        rehearsal = loaded(a.rehearsal, a.rehearsal_sha256)
        assert rehearsal['code'] == captured['code'] and rehearsal['before_sha256'] == input_hash
        assert rehearsal['independent_transaction_public_readback'] == 'PASS'
        probes = rehearsal['rehearsal']['recall']['terms']
        rehearsal_sha = a.rehearsal_sha256
    else:
        receipt = loaded(a.receipt, a.receipt_sha256)
        assert receipt['runtime'] == code, 'code drift since receipt'
        before = receipt['after']; target = m.OLD
        input_hash = a.receipt_sha256
        probes = receipt['probes']; rehearsal_sha = receipt['rehearsal_sha256']
        if a.mode == 'reverse': assert receipt['operation'] == 'apply' and before['expression'] == m.NEW
    validate_probes(probes)
    assert all(str(p['id']) in before['motion_non_fts'] for p in probes)
    conn = m.psycopg2.connect(m.config.DATABASE_URL, connect_timeout=15)
    if a.mode == 'readback':
        conn.set_session(readonly=True, isolation_level='REPEATABLE READ')
        try:
            with conn.cursor() as c:
                m.contract(c, before); m.verify_values(c, 'public.motions', before['expression'])
                recall = post_apply_recall(c, probes) if before['expression'] == m.NEW else None
            conn.rollback()
            print(json.dumps({'readback_sha256': m.durable(a.out, {'status':'PASS','receipt_sha256':input_hash,'runtime':code,'state_sha256':m.sha(before),'recall':recall,'paid_calls':0})}))
        finally: conn.rollback(); conn.close()
        return
    # A review is an immutable, explicit code/input binding prepared by the reviewer.
    review = loaded(a.review, a.review_sha256)
    assert review['runtime'] == code and review['input_sha256'] == input_hash
    assert review['operation'] == a.mode and review['status'] == 'approved'
    assert review['rehearsal_sha256'] == rehearsal_sha
    pending = a.out.with_name(a.out.name + '.pending.json')
    assert not a.out.exists() and not pending.exists(), 'existing receipt: independent readback, no retry'
    conn.set_session(isolation_level='SERIALIZABLE')
    attempted = False
    try:
        with conn.cursor() as c:
            c.execute("SET LOCAL lock_timeout='2s'"); c.execute("SET LOCAL statement_timeout='30s'")
            # Bound table set prevents source/vote/reference changes during fingerprint assertions.
            c.execute('LOCK TABLE public.motions IN ACCESS EXCLUSIVE MODE')
            c.execute('LOCK TABLE public.votes,public.key_votes,public.transcript_segments IN SHARE MODE')
            m.contract(c, before)
            path = m.FORWARD if a.mode == 'apply' else m.REVERSE
            start = time.monotonic(); c.execute(path.read_text()); elapsed = time.monotonic()-start
            after = expected_after(before, target)
            m.contract(c, after); m.verify_values(c, 'public.motions', target)
            recall = post_apply_recall(c, probes) if target == m.NEW else None
            assert runtime() == code and m.file_sha(a.review) == a.review_sha256
            result = {'operation':a.mode,'runtime':code,'review_sha256':a.review_sha256,
                      'input_sha256':input_hash,'before':before,'after':after,
                      'rehearsal_sha256':rehearsal_sha,'probes':probes,
                      'ddl_seconds':elapsed,'recall':recall,'paid_calls':0,'status':'pending_commit'}
            pending_sha = m.durable(pending, result)
            assert runtime() == code and m.file_sha(a.review) == a.review_sha256
            if a.mode == 'apply':
                assert m.file_sha(a.before) == a.before_sha256 and m.file_sha(a.rehearsal) == rehearsal_sha
            else: assert m.file_sha(a.receipt) == a.receipt_sha256
            m.contract(c, after)
        attempted = True
        conn.commit()
        result.update(status='committed_requires_independent_readback', pending_sha256=pending_sha)
        applied_sha = m.durable(a.out, result)
        print(json.dumps({'applied_sha256':applied_sha,'ddl_seconds':elapsed,'independent_readback_required':True}))
        # Generated expression replacement removes column statistics. No DDL retry on ANALYZE failure.
        try:
            with conn.cursor() as c:
                c.execute("SET LOCAL lock_timeout='2s'"); c.execute("SET LOCAL statement_timeout='30s'")
                c.execute('ANALYZE public.motions (text_search)')
            conn.commit()
            print('ANALYZE complete')
        except Exception:
            conn.rollback(); print('Committed; ANALYZE follow-up required', file=sys.stderr)
    except Exception:
        conn.rollback()
        if attempted: print('COMMIT attempted: pending receipt requires independent readback; do not retry', file=sys.stderr)
        raise
    finally: conn.close()

if __name__ == '__main__': main()
