"""Apply the source identity uniqueness guard and verify its live definition."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import psycopg2
from pipeline import config

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--apply', action='store_true')
args = parser.parse_args()
root = Path(__file__).resolve().parents[3]
source = root/'sql/add_canonical_motion_identity.sql'
sql = source.read_text()
with psycopg2.connect(config.DATABASE_URL, connect_timeout=20) as db:
    with db.cursor() as cur:
        cur.execute("SELECT indexdef FROM pg_indexes WHERE schemaname='public' AND indexname='motions_canonical_source_identity'")
        before = cur.fetchone()
        if args.apply:
            # The migration owns its transaction, duplicate preflight and table lock.
            cur.execute(sql)
        cur.execute("SELECT i.indisunique,i.indisvalid,pg_get_indexdef(i.indexrelid),pg_get_expr(i.indpred,i.indrelid) FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname='motions_canonical_source_identity'")
        row = cur.fetchone()
        if args.apply:
            assert row and row[0] and row[1], 'canonical_identity_index_not_unique_and_valid'
            assert "(meeting_id, (((meta -> 'canonical_source_motion'::text) ->> 'key'::text)))" in row[2], 'unexpected_canonical_identity_index_definition'
            assert row[3] == "(NULLIF(((meta -> 'canonical_source_motion'::text) ->> 'key'::text), ''::text) IS NOT NULL)", 'unexpected_canonical_identity_predicate'
        result = {'mode':'applied_verified' if args.apply else 'read_only_preflight',
                  'at':datetime.now(timezone.utc).isoformat(),
                  'sql_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                  'previous_index_definition':before[0] if before else None,
                  'live_index_definition':row[2] if row else None,
                  'unique_and_valid':bool(row and row[0] and row[1]),
                  'row_mutations':0}
path = Path(__file__).with_name('canonical-identity-index-applied-verification.json' if args.apply else 'canonical-identity-index-preflight.json')
assert not path.exists(), 'preserve_existing_migration_evidence'
path.write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result))
