"""Read complete-motion proof+choices in one consistent PostgreSQL snapshot."""
import json
from pathlib import Path
from datetime import datetime,timezone
import psycopg2
from psycopg2.extras import RealDictCursor
from pipeline import config
out=Path(__file__).parent
with psycopg2.connect(config.DATABASE_URL,connect_timeout=15) as db:
 db.set_session(readonly=True,isolation_level='REPEATABLE READ')
 with db.cursor(cursor_factory=RealDictCursor) as c:
  c.execute("SELECT id,meeting_id,agenda_item_id,text_content,result,meta,updated_at FROM motions WHERE meta->>'individual_vote_coverage'='reconstructed_complete' ORDER BY id");motions=list(c.fetchall());ids=[m['id'] for m in motions]
  c.execute('SELECT id,motion_id,person_id,vote,updated_at FROM votes WHERE motion_id=ANY(%s) ORDER BY id',(ids,));votes=list(c.fetchall())
  r={'at':datetime.now(timezone.utc).isoformat(),'motions':motions,'votes':votes};(out/'complete-ballots-current-snapshot.json').write_text(json.dumps(r,indent=2,default=str));print(json.dumps({'complete_motions':len(motions),'choices':len(votes)}))
