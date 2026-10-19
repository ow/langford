"""PG17 motion FTS guard. Default operations are snapshot / TEMP-only rehearsal.

Apply/reverse are deliberately unavailable pending review of measured rehearsal.
No source content, vectors or credentials are printed; evidence belongs in ignored storage.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'apps/pipeline'))
from pipeline import config
import psycopg2

OLD = "to_tsvector('english'::regconfig, COALESCE(plain_english_summary, text_content, ''::text))"
NEW = "to_tsvector('english'::regconfig, ((COALESCE(text_content, ''::text) || ' '::text) || COALESCE(plain_english_summary, ''::text)))"
FORWARD = ROOT / 'sql/motions_full_text_search_forward.sql'
REVERSE = ROOT / 'sql/motions_full_text_search_reverse.sql'

def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()

def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def durable(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.')
    os.fchmod(fd, 0o600)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f, indent=2, default=str)
            f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.link(temp, path)  # exclusive: never replace an earlier snapshot/receipt
        d = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(d)
        finally: os.close(d)
    finally: os.unlink(temp)
    return file_sha(path)

def rows(c, sql, args=()):
    c.execute(sql, args)
    names = [d.name for d in c.description]
    return [dict(zip(names, row)) for row in c.fetchall()]

def expression(c, table='public.motions'):
    return rows(c, "SELECT pg_get_expr(d.adbin,d.adrelid) expression FROM pg_attrdef d JOIN pg_attribute a ON a.attrelid=d.adrelid AND a.attnum=d.adnum WHERE d.adrelid=%s::regclass AND a.attname='text_search'", (table,))[0]['expression']

def fingerprint(c, table='public.motions'):
    # to_jsonb includes exact vector text and every source/metadata/timestamp column.
    data = rows(c, f"SELECT id, to_jsonb(m)-'text_search' value FROM {table} m ORDER BY id")
    return {str(r['id']): sha(r['value']) for r in data}

def catalog(c):
    queries = {
        'columns': "SELECT a.attnum,a.attname,a.atttypid,a.atttypmod,a.attnotnull,a.attgenerated,a.attidentity,a.attacl::text,a.attcollation,pg_get_expr(d.adbin,d.adrelid) default_expression FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum WHERE a.attrelid='public.motions'::regclass AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum",
        'table': "SELECT oid,relowner,relacl::text,relrowsecurity,relforcerowsecurity,relkind,reloptions FROM pg_class WHERE oid='public.motions'::regclass",
        'indexes': "SELECT i.indexrelid,pg_get_indexdef(i.indexrelid) definition,i.indisvalid,i.indisready,i.indisunique,i.indclass::text,i.indcollation::text,i.indoption::text FROM pg_index i WHERE indrelid='public.motions'::regclass ORDER BY indexrelid",
        'constraints': "SELECT oid,conname,contype,conrelid,confrelid,convalidated,pg_get_constraintdef(oid) definition FROM pg_constraint WHERE conrelid='public.motions'::regclass OR confrelid='public.motions'::regclass ORDER BY oid",
        'triggers': "SELECT oid,tgname,tgenabled,pg_get_triggerdef(oid) definition FROM pg_trigger WHERE tgrelid='public.motions'::regclass ORDER BY oid",
        'policies': "SELECT * FROM pg_policies WHERE schemaname='public' AND tablename='motions' ORDER BY policyname",
        'functions': "SELECT p.oid,p.oid::regprocedure::text signature,p.proowner,p.proacl::text,p.prosecdef,p.proconfig,pg_get_functiondef(p.oid) definition FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname IN ('hybrid_search_motions','match_motions','match_motions_by_person') ORDER BY p.oid",
    }
    return {name: rows(c, sql) for name, sql in queries.items()}

def snapshot(c):
    c.execute("SELECT current_setting('server_version_num')::integer")
    version = c.fetchone()[0]
    assert 170000 <= version < 180000, 'requires reviewed PG17'
    cat = catalog(c)
    votes = rows(c, 'SELECT to_jsonb(v) value FROM public.votes v ORDER BY id')
    references = {}
    for table in ('votes','key_votes','transcript_segments'):
        refs = rows(c, f'SELECT id,motion_id FROM public.{table} ORDER BY id')
        references[table] = {'count': len(refs), 'sha256': sha(refs)}
    return {'server_version_num': version, 'expression': expression(c), 'catalog': cat,
            'motion_non_fts': fingerprint(c), 'votes_sha256': sha(votes),
            'references': references,
            'null_vectors': rows(c, 'SELECT count(*) count FROM public.motions WHERE embedding IS NULL')[0]['count']}

def contract(c, expected):
    actual = snapshot(c)
    assert actual == expected, 'live before-state changed; recapture and review, never blind retry'

def verify_values(c, table, expr):
    c.execute(f'SELECT count(*) FROM {table} WHERE text_search IS DISTINCT FROM ({expr})')
    assert c.fetchone()[0] == 0, 'generated value mismatch'

def temp_indexes(c):
    return rows(c, "SELECT ci.relname,am.amname,i.indisvalid,i.indisready,i.indclass::text,i.indisunique FROM pg_index i JOIN pg_class ci ON ci.oid=i.indexrelid JOIN pg_am am ON am.oid=ci.relam WHERE i.indrelid='pg_temp.fts_rehearsal'::regclass ORDER BY ci.relname")

def recall_probes(c, indexed_table="public.motions"):
    # Select concrete lexemes independently from each field; original source stays private.
    probes = rows(c, f"""SELECT DISTINCT ON (m.id) m.id, t.term
        FROM public.motions m CROSS JOIN LATERAL unnest(tsvector_to_array(to_tsvector('english',coalesce(m.text_content,'')))) t(term)
        CROSS JOIN LATERAL (SELECT count(*) hits FROM (SELECT 1 FROM {indexed_table} idx WHERE idx.text_search @@ plainto_tsquery('english',t.term) LIMIT 31) hit) n
        WHERE n.hits BETWEEN 1 AND 30 AND m.id=ANY(ARRAY[1474,1505,1711,1925,1927,2153,3089]::bigint[])
          AND t.term ~ '^[a-z]{5,}$'
          AND to_tsvector('english',coalesce(m.text_content,'')) @@ plainto_tsquery('english',t.term)
          AND NOT (to_tsvector('english',coalesce(m.plain_english_summary,'')) @@ plainto_tsquery('english',t.term))
        ORDER BY m.id,n.hits,length(t.term) DESC,t.term""")
    missing = sorted({1474,1505,1711,1925,1927,2153,3089} - {p['id'] for p in probes})
    if missing:
        # A complete native paragraph is an independently meaningful source conjunction,
        # unlike inventing arbitrary rare token pairs. Quote it for the RPC phrase parser.
        paragraphs = rows(c, f"""SELECT DISTINCT ON (m.id) m.id, '"' || regexp_replace(trim(t.paragraph),'["\\n\\r]+',' ','g') || '"' term
            FROM public.motions m CROSS JOIN LATERAL regexp_split_to_table(m.text_content,E'\\n[[:space:]]*\\n') t(paragraph)
            CROSS JOIN LATERAL (SELECT count(*) hits FROM (SELECT 1 FROM {indexed_table} idx WHERE idx.text_search @@ plainto_tsquery('english',t.paragraph) LIMIT 31) hit) n
            WHERE m.id=ANY(%s::bigint[]) AND length(trim(t.paragraph))>20 AND n.hits BETWEEN 1 AND 30
            AND to_tsvector('english',m.text_content) @@ plainto_tsquery('english',t.paragraph)
            AND NOT (to_tsvector('english',coalesce(m.plain_english_summary,'')) @@ plainto_tsquery('english',t.paragraph))
            ORDER BY m.id,n.hits,length(t.paragraph),t.paragraph""", (missing,))
        probes.extend(paragraphs)
    assert len(probes) == 7, ('no bounded meaningful source query',missing,[p['id'] for p in probes])
    for p in probes: p['field'] = 'body_only'
    summary = rows(c, f"""SELECT m.id,t.term FROM public.motions m
        CROSS JOIN LATERAL unnest(tsvector_to_array(to_tsvector('english',coalesce(m.plain_english_summary,'')))) t(term)
        CROSS JOIN LATERAL (SELECT count(*) hits FROM (SELECT 1 FROM {indexed_table} idx WHERE idx.text_search @@ plainto_tsquery('english',t.term) LIMIT 31) hit) n
        WHERE n.hits BETWEEN 1 AND 30 AND t.term ~ '^[a-z]{5,}$' AND to_tsvector('english',coalesce(m.plain_english_summary,'')) @@ plainto_tsquery('english',t.term) AND NOT (to_tsvector('english',coalesce(m.text_content,'')) @@ plainto_tsquery('english',t.term))
        ORDER BY m.id,n.hits,length(t.term) DESC,t.term LIMIT 1""")
    if not summary:
        summary = rows(c, f"""SELECT m.id, '"' || replace(m.plain_english_summary,'"',' ') || '"' term
            FROM public.motions m
            CROSS JOIN LATERAL (SELECT count(*) hits FROM (SELECT 1 FROM {indexed_table} idx WHERE idx.text_search @@ plainto_tsquery('english',m.plain_english_summary) LIMIT 31) hit) n
            WHERE length(m.plain_english_summary)>20 AND n.hits BETWEEN 1 AND 30
            AND to_tsvector('english',m.plain_english_summary) @@ plainto_tsquery('english',m.plain_english_summary)
            AND NOT (to_tsvector('english',coalesce(m.text_content,'')) @@ plainto_tsquery('english',m.plain_english_summary))
            ORDER BY m.id,n.hits LIMIT 1""")
    assert summary, 'no bounded meaningful summary-only query'
    summary[0]['field'] = 'summary_only'
    return probes + summary

def matching_ids(c, table, expr, term):
    c.execute(f"SELECT id FROM {table} WHERE ({expr}) @@ plainto_tsquery('english',%s) ORDER BY id", (term,))
    return [r[0] for r in c.fetchall()]

def rpc_copy_probes(c, before, probes):
    # Private function copies use exact existing bodies, changing only relation/name binding.
    for f in before['catalog']['functions']:
        name = f['signature'].split('(')[0]
        if name == 'hybrid_search_motions':
            arity = 9 if 'date,date,bigint)' in f['signature'] else 6
            tempname = f'fts_hybrid_{arity}'
        elif name == 'match_motions':
            arity = 4 if f['signature'].count(',') == 3 else 3
            tempname = f'fts_match_{arity}'
        else:
            tempname = 'fts_person'
        definition = f['definition'].replace(f'CREATE OR REPLACE FUNCTION public.{name}(', f'CREATE FUNCTION pg_temp.{tempname}(')
        definition = definition.replace('FROM motions m', 'FROM pg_temp.fts_rehearsal m').replace('JOIN motions ON', 'JOIN pg_temp.fts_rehearsal motions ON')
        assert definition != f['definition'] and 'FROM motions m' not in definition
        c.execute(definition)
    c.execute('SELECT embedding::text FROM public.motions WHERE embedding IS NOT NULL ORDER BY id LIMIT 1')
    vector = c.fetchone()[0]
    # Actual public RPCs are BEFORE probes only; new-term assertions use temporary copies.
    public_results = {}
    for arity in (6,9):
        tail = ',NULL::date,NULL::date,NULL::bigint' if arity == 9 else ''
        c.execute('SAVEPOINT public_rpc_probe')
        try:
            c.execute(f"SELECT id,rank_score FROM public.hybrid_search_motions(%s::text,%s::halfvec,3::integer,1::float8,1::float8,50::integer{tail})", ('council',vector))
            result = c.fetchall()
            assert result and all(score > 0 for _,score in result)
            public_results[str(arity)] = {'ids': [x[0] for x in result], 'state': 'existing_public_before_expression'}
        except psycopg2.errors.AmbiguousFunction:
            c.execute('ROLLBACK TO SAVEPOINT public_rpc_probe')
            assert arity == 6
            public_results[str(arity)] = {'state':'preexisting_ambiguous_default_overload','sqlstate':'42725','exact_body_verified_in_unique_temp_copy':True}
        finally: c.execute('RELEASE SAVEPOINT public_rpc_probe')
        for p in probes:
            c.execute(f"SELECT id,rank_score FROM pg_temp.fts_hybrid_{arity}(%s::text,NULL::halfvec,30::integer,1::float8,0::float8,50::integer{tail})", (p['term'],))
            positive = [r[0] for r in c.fetchall() if r[1] > 0]
            assert p['id'] in positive, (arity,p['id'],'new keyword absent from private RPC copy')
    # Actual semantic-only overloads consume a stored vector; no embedding generation.
    funcs = [f for f in before['catalog']['functions'] if f['signature'].startswith('match_motions(')]
    for f in funcs:
        tail = ',NULL::bigint' if f['signature'].count(',') == 3 else ''
        arity = 4 if tail else 3
        c.execute('SAVEPOINT public_match_probe')
        try:
            c.execute(f'SELECT id FROM public.match_motions(%s::halfvec,0.5::float8,3::integer{tail})', (vector,))
            assert c.fetchall()
            public_results[f'match_{arity}'] = {'state':'existing_public_before_expression'}
        except psycopg2.errors.AmbiguousFunction:
            c.execute('ROLLBACK TO SAVEPOINT public_match_probe')
            assert arity == 3
            public_results['match_3'] = {'state':'preexisting_ambiguous_default_overload','sqlstate':'42725','exact_body_verified_in_unique_temp_copy':True}
        finally: c.execute('RELEASE SAVEPOINT public_match_probe')
        c.execute(f'SELECT id FROM pg_temp.fts_match_{arity}(%s::halfvec,0.5::float8,3::integer{tail})', (vector,))
        assert c.fetchall()
    c.execute("SELECT v.person_id,m.embedding::text FROM public.votes v JOIN public.motions m ON m.id=v.motion_id WHERE v.person_id IS NOT NULL AND m.embedding IS NOT NULL ORDER BY m.id,v.person_id LIMIT 1")
    person, person_vector = c.fetchone()
    c.execute('SELECT id FROM public.match_motions_by_person(%s::halfvec,%s::bigint,0.5::float8,3::integer)', (person_vector,person))
    by_person = [r[0] for r in c.fetchall()]
    assert by_person
    c.execute('SELECT id FROM pg_temp.fts_person(%s::halfvec,%s::bigint,0.5::float8,3::integer)', (person_vector,person))
    assert c.fetchall()
    c.execute('SELECT DISTINCT motion_id FROM public.votes WHERE person_id=%s AND motion_id=ANY(%s::bigint[])', (person,by_person))
    assert set(by_person) == {r[0] for r in c.fetchall()}
    public_results['by_person'] = {'ids':by_person, 'state':'existing_public_before_expression'}
    # Filter controls use a real target's exact meeting date and municipality.
    c.execute('SELECT mt.meeting_date,mt.municipality_id,m.embedding::text,m.id FROM public.motions m JOIN public.meetings mt ON mt.id=m.meeting_id WHERE m.embedding IS NOT NULL AND mt.municipality_id IS NOT NULL ORDER BY m.id LIMIT 1')
    day, municipality, scoped_vector, scoped_id = c.fetchone()
    for schema, function in [('public','hybrid_search_motions'),('pg_temp','fts_hybrid_9')]:
        base = f'SELECT id FROM {schema}.{function}(%s::text,%s::halfvec,30::integer,0::float8,1::float8,50::integer,%s::date,%s::date,%s::bigint)'
        c.execute(base, ('council',scoped_vector,day,day,municipality))
        scoped_ids = [r[0] for r in c.fetchall()]
        assert scoped_id in scoped_ids
        c.execute('SELECT m.id FROM public.motions m JOIN public.meetings mt ON mt.id=m.meeting_id WHERE m.id=ANY(%s::bigint[]) AND mt.meeting_date=%s AND mt.municipality_id=%s', (scoped_ids,day,municipality))
        assert set(scoped_ids) == {r[0] for r in c.fetchall()}
        c.execute(base, ('council',scoped_vector,day,day,-1))
        assert c.fetchall() == []
        # Impossible date range must exclude both lexical and semantic branches.
        c.execute(base.replace('0::float8,1::float8','1::float8,1::float8'), ('council',scoped_vector,'9999-12-31','0001-01-01',municipality))
        assert c.fetchall() == []
        public_results[schema+'_filtered_controls'] = {'positive_ids':scoped_ids,'wrong_municipality':[], 'inverted_date_range':[]}
    return public_results


def detailed_recall(c, before, probes):
    proof = []
    for p in probes:
        c.execute('SET LOCAL enable_seqscan=off'); c.execute('SET LOCAL enable_indexscan=off'); c.execute('SET LOCAL enable_bitmapscan=on')
        c.execute("EXPLAIN (FORMAT JSON) SELECT id FROM pg_temp.fts_rehearsal WHERE text_search @@ plainto_tsquery('english',%s)", (p['term'],))
        plan = c.fetchone()[0]
        assert 'fts_rehearsal_text_search_idx' in json.dumps(plan), 'GIN probe did not use the actual copied FTS index'
        indexed = matching_ids(c, 'pg_temp.fts_rehearsal', 'text_search', p['term'])
        c.execute('SET LOCAL enable_seqscan=on'); c.execute('SET LOCAL enable_indexscan=off'); c.execute('SET LOCAL enable_bitmapscan=off')
        sequential = matching_ids(c, 'pg_temp.fts_rehearsal', NEW, p['term'])
        c.execute('SET LOCAL enable_indexscan=on'); c.execute('SET LOCAL enable_bitmapscan=on')
        assert indexed == sequential and p['id'] in indexed
        old = matching_ids(c, 'public.motions', 'text_search', p['term'])
        if p['field'] == 'body_only': assert p['id'] not in old
        else: assert p['id'] in old
        proof.append({**p,'new_matching_ids':indexed,'old_matching_ids':old})
    return {'terms': proof, 'rpc_before': rpc_copy_probes(c,before,probes)}


def rehearse(c, before):
    contract(c, before)
    assert before['expression'] == OLD, 'unexpected starting expression'
    c.execute('CREATE TEMP TABLE fts_rehearsal (LIKE public.motions INCLUDING ALL) ON COMMIT DROP')
    # Explicit column list avoids generated-column writes, default sequences and triggers.
    columns = [r['attname'] for r in before['catalog']['columns'] if not r['attgenerated']]
    from psycopg2 import sql
    ids = sql.SQL(',').join(map(sql.Identifier, columns))
    c.execute(sql.SQL('INSERT INTO pg_temp.fts_rehearsal ({0}) SELECT {0} FROM public.motions').format(ids))
    assert fingerprint(c, 'pg_temp.fts_rehearsal') == before['motion_non_fts']
    indexes = temp_indexes(c)
    # LIKE omits incoming FKs; probe every real reference against the temp parent IDs.
    for table in ('votes','key_votes','transcript_segments'):
        c.execute(f'CREATE TEMP TABLE refs_{table} ON COMMIT DROP AS SELECT motion_id FROM public.{table} WHERE motion_id IS NOT NULL')
        c.execute(f'ALTER TABLE pg_temp.refs_{table} ADD FOREIGN KEY (motion_id) REFERENCES pg_temp.fts_rehearsal(id)')
    timings = {}
    storage = {}
    storage['before'] = rows(c, "SELECT pg_relation_size('pg_temp.fts_rehearsal') heap_bytes,pg_total_relation_size('pg_temp.fts_rehearsal') total_bytes")[0]
    recall = None
    for label, path, expected in [('forward', FORWARD, NEW), ('reverse', REVERSE, OLD)]:
        statement = path.read_text().replace('ALTER TABLE public.motions', 'ALTER TABLE pg_temp.fts_rehearsal')
        start = time.monotonic(); c.execute(statement); timings[label] = time.monotonic() - start
        storage[label] = rows(c, "SELECT pg_relation_size('pg_temp.fts_rehearsal') heap_bytes,pg_total_relation_size('pg_temp.fts_rehearsal') total_bytes")[0]
        assert expression(c, 'pg_temp.fts_rehearsal') == expected
        verify_values(c, 'pg_temp.fts_rehearsal', expected)
        assert fingerprint(c, 'pg_temp.fts_rehearsal') == before['motion_non_fts']
        assert temp_indexes(c) == indexes, 'temp index identity/opclass changed'
        if label == 'forward': recall = detailed_recall(c, before, recall_probes(c, 'pg_temp.fts_rehearsal'))
        c.execute('SET LOCAL enable_seqscan=off')
        c.execute("SELECT count(*) FROM pg_temp.fts_rehearsal WHERE text_search @@ to_tsquery('english','council')")
        indexed = c.fetchone()[0]
        c.execute('SET LOCAL enable_seqscan=on'); c.execute('SET LOCAL enable_indexscan=off'); c.execute('SET LOCAL enable_bitmapscan=off')
        c.execute(f"SELECT count(*) FROM pg_temp.fts_rehearsal WHERE ({expected}) @@ to_tsquery('english','council')")
        assert c.fetchone()[0] == indexed
        c.execute('SET LOCAL enable_indexscan=on'); c.execute('SET LOCAL enable_bitmapscan=on')
    # Synthetic body-only/summary-only probes are separate temp rows, never public data.
    c.execute("CREATE TEMP TABLE fts_terms (body text, summary text, doc tsvector GENERATED ALWAYS AS (to_tsvector('english',coalesce(body,'')||' '||coalesce(summary,''))) STORED) ON COMMIT DROP")
    c.execute("INSERT INTO pg_temp.fts_terms(body,summary) VALUES ('quartzbody','zephyrsummary'),(NULL,'zephyrsummary'),('quartzbody',NULL),(NULL,NULL)")
    c.execute("SELECT count(*) FILTER(WHERE doc @@ to_tsquery('english','quartzbody')),count(*) FILTER(WHERE doc @@ to_tsquery('english','zephyrsummary')) FROM pg_temp.fts_terms")
    assert c.fetchone() == (2,2)
    c.execute("SELECT doc @@ to_tsquery('english','quartzbody <-> zephyrsummary') FROM pg_temp.fts_terms WHERE body IS NOT NULL AND summary IS NOT NULL")
    assert c.fetchone()[0] is True  # documented cross-field phrase behavior
    c.execute("INSERT INTO pg_temp.fts_terms(body,summary) VALUES ('','')")
    c.execute("SELECT count(*) FROM pg_temp.fts_terms WHERE doc <> ''::tsvector AND coalesce(body,'')='' AND coalesce(summary,'')=''")
    assert c.fetchone()[0] == 0
    contract(c, before)  # public table/catalog still untouched inside this transaction
    return {'storage_bytes': storage, 'recall': recall, 'cross_field_phrase_match': True, 'timings_seconds': timings, 'temp_indexes': indexes, 'motions': len(before['motion_non_fts']),
            'limitations': ['TEMP copy has no RLS/ACL equivalence or original outgoing FKs/triggers',
                'incoming FK references explicitly copied and validated against temp parent IDs',
                'all five exact RPC bodies copied privately; public before probes labeled separately; legacy short calls may be ambiguous',
                'no production lock-contention estimate; apply must assert real catalog under exclusive lock'],
            'public_mutations': 0, 'paid_calls': 0}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['snapshot','rehearse'])
    p.add_argument('--before', type=Path)
    p.add_argument('--before-sha256')
    p.add_argument('--out', required=True, type=Path)
    a = p.parse_args()
    code = {'runner': file_sha(Path(__file__)), 'forward': file_sha(FORWARD), 'reverse': file_sha(REVERSE)}
    conn = psycopg2.connect(config.DATABASE_URL, connect_timeout=15)
    conn.set_session(readonly=a.mode == 'snapshot', isolation_level='REPEATABLE READ')
    try:
        with conn.cursor() as c:
            c.execute("SET LOCAL lock_timeout='2s'"); c.execute("SET LOCAL statement_timeout='30s'")
            if a.mode == 'snapshot':
                out = {'code': code, 'before': snapshot(c)}
            else:
                assert a.before and a.before_sha256 and file_sha(a.before) == a.before_sha256
                captured = json.loads(a.before.read_text())
                assert captured['code'] == code, 'runner/SQL changed since capture'
                out = {'code': code, 'before_sha256': a.before_sha256, 'rehearsal': rehearse(c, captured['before'])}
        conn.rollback()
        if a.mode == 'rehearse':
            conn.set_session(readonly=True, isolation_level='REPEATABLE READ')
            with conn.cursor() as c: contract(c, captured['before'])
            conn.rollback(); out['independent_transaction_public_readback'] = 'PASS'
        print(json.dumps({'receipt_sha256': durable(a.out, out), 'mode': a.mode, 'rehearsal_summary': ({'motions':out['rehearsal']['motions'],'timings_seconds':out['rehearsal']['timings_seconds'],'public_mutations':0,'paid_calls':0} if 'rehearsal' in out else None)}, default=str))
    finally:
        conn.rollback(); conn.close()

if __name__ == '__main__': main()
