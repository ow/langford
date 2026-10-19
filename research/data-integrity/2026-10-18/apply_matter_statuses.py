"""Apply a reviewed status proposal with optimistic concurrency and rollback data."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from supabase import create_client
from pipeline.config import SUPABASE_URL, SUPABASE_SECRET_KEY

parser = argparse.ArgumentParser()
parser.add_argument('--proposal', type=Path, required=True)
parser.add_argument('--rollback', type=Path, required=True)
parser.add_argument('--apply', action='store_true')
args = parser.parse_args()
client = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)
proposal = json.loads(args.proposal.read_text())
records = []
for update in proposal['lifecycle_updates']:
    current = client.table('matters').select('id,status,meta').eq('id', update['id']).single().execute().data
    if current['status'] != update['old_status']:
        raise RuntimeError(f"Status changed for {update['id']}; regenerate proposal")
    expected_meta = dict(update['meta'])
    expected_meta.pop('lifecycle_evidence', None)
    current_without_evidence = dict(current.get('meta') or {})
    current_without_evidence.pop('lifecycle_evidence', None)
    if current_without_evidence != expected_meta:
        raise RuntimeError(f"Metadata changed for {update['id']}; regenerate proposal")
    records.append({'before': current, 'after': {'status': update['status'],
        'meta': {**(current.get('meta') or {}), 'lifecycle_evidence': update['meta']['lifecycle_evidence']}}, 'applied': False})
backup = {'created_at': datetime.now(timezone.utc).isoformat(), 'records': records}
if args.rollback.exists():
    raise RuntimeError('Rollback path already exists; never overwrite earlier before-values')
args.rollback.write_text(json.dumps(backup, indent=2)+'\n')
args.rollback.chmod(0o600)
print(f"Validated {len(records)} rows; before-values saved; apply={args.apply}", flush=True)
if args.apply:
    for record in records:
        before = record['before']
        query = client.table('matters').update(record['after']).eq('id', before['id']).eq('status', before['status'])
        query = query.is_('meta', 'null') if before['meta'] is None else query.eq('meta', json.dumps(before['meta'], separators=(',', ':')))
        result = query.execute()
        if len(result.data) != 1:
            raise RuntimeError(f"Concurrent status/meta change for {before['id']}; stopped, inspect rollback receipt")
        record['applied'] = True
        args.rollback.write_text(json.dumps(backup, indent=2)+'\n')
        if sum(r['applied'] for r in records) % 25 == 0:
            print(f"Applied {sum(r['applied'] for r in records)}/{len(records)}", flush=True)
    print(f"Applied {len(records)} reviewed status changes", flush=True)
