"""Read exact CAS before-values for the independently reviewed historical plan."""
import json,hashlib
from pathlib import Path
from datetime import datetime,timezone
import psycopg2
from psycopg2.extras import RealDictCursor
from pipeline import config
out=Path(__file__).parent;raw=(out/'roster-source-recovery-plan.json').read_bytes();plan=json.loads(raw);ids=sorted({r['motion_id'] for r in plan['motions']+plan['canonical_body_corrections']})
with psycopg2.connect(config.DATABASE_URL,connect_timeout=15) as db:
 db.set_session(readonly=True,isolation_level='REPEATABLE READ')
 with db.cursor(cursor_factory=RealDictCursor) as c:
  c.execute('SELECT id,meeting_id,agenda_item_id,text_content,result,meta,updated_at FROM motions WHERE id=ANY(%s) ORDER BY id',(ids,));motions=list(c.fetchall())
  c.execute('SELECT id,motion_id,person_id,vote,updated_at FROM votes WHERE motion_id=ANY(%s) ORDER BY id',(ids,));votes=list(c.fetchall())
  r={'at':datetime.now(timezone.utc).isoformat(),'plan_sha256':hashlib.sha256(raw).hexdigest(),'motions':motions,'votes':votes};(out/'roster-source-recovery-before.json').write_text(json.dumps(r,indent=2,default=str));print(json.dumps({'motions':len(motions),'existing_choices':len(votes),'plan_sha256':r['plan_sha256']}))
