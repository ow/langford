"""Independently read back exact applied bodies, outcomes, metadata and ballots."""
import json
from datetime import datetime, timezone
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor
from pipeline import config

out = Path(__file__).parent
receipt = json.loads((out/'canonical-text-recovery-applied-receipt.json').read_text())
assert receipt['mode'] == 'applied'
canonical = lambda value: json.loads(json.dumps(value, default=str))
with psycopg2.connect(config.DATABASE_URL, connect_timeout=20) as db:
    db.set_session(readonly=True)
    with db.cursor(cursor_factory=RealDictCursor) as cur:
        verified, preserved = [], []
        for change in receipt['changes']:
            cur.execute('SELECT id,meeting_id,agenda_item_id,text_content,result,meta,updated_at FROM motions WHERE id=%s', (change['motion_id'],))
            assert canonical(dict(cur.fetchone())) == change['after_motion'], 'applied_motion_readback_differs'
            cur.execute('SELECT id,motion_id,person_id,vote,recusal_reason,created_at,updated_at FROM votes WHERE motion_id=%s ORDER BY id', (change['motion_id'],))
            actual = canonical(list(cur.fetchall()))
            assert actual == change['before_votes'], 'existing_vote_rows_changed'
            assert change['after_motion']['agenda_item_id'] == change['before_motion']['agenda_item_id']
            verified.append(change['motion_id'])
            preserved.extend(vote['id'] for vote in actual)
result = {'mode':'verified_read_only', 'at':datetime.now(timezone.utc).isoformat(),
          'plan_sha256':receipt['plan_sha256'], 'verified_motion_ids':verified,
          'preserved_vote_ids':preserved, 'summary':{'exact_motion_readbacks':len(verified),
          'unchanged_vote_rows':len(preserved), 'agenda_relinks':0, 'database_writes':0}}
(out/'canonical-text-recovery-verification.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result['summary']))
