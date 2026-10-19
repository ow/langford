"""Read-only aggregate verification and written inventory after approved repair."""
import json
from pathlib import Path
from datetime import datetime,timezone
import psycopg2
from psycopg2.extras import RealDictCursor
from pipeline import config
OUT=Path(__file__).parent
with psycopg2.connect(config.DATABASE_URL,connect_timeout=15) as db:
 with db.cursor(cursor_factory=RealDictCursor) as c:
  c.execute("""WITH ballot AS (SELECT motion_id,count(*) n,count(*) FILTER(WHERE vote='Yes') y,count(*) FILTER(WHERE vote='No') no FROM votes GROUP BY motion_id) SELECT count(*) motions,count(*) FILTER(WHERE m.result IS NOT NULL) with_result,count(*) FILTER(WHERE m.result IS NULL) missing_result,count(*) FILTER(WHERE b.n>0) motions_with_recorded_votes,coalesce(sum(b.n),0)::int individual_vote_rows,count(*) FILTER(WHERE m.result IS NOT NULL AND b.n IS NULL) result_without_individual_votes,count(*) FILTER(WHERE m.result LIKE 'CARR%' AND b.no>b.y) partial_carried_opposition,count(*) FILTER(WHERE m.meta->>'individual_vote_coverage'='reconstructed_complete') complete_reconstructed_ballots FROM motions m LEFT JOIN ballot b ON b.motion_id=m.id""")
  totals=dict(c.fetchone())
  c.execute("""SELECT p.id,p.name,count(*)::int individual_choices,count(*) FILTER(WHERE m.meta->>'individual_vote_coverage'='reconstructed_complete')::int complete_ballot_choices,count(*) FILTER(WHERE (m.meta->'ballot_reconstruction'->'choice_provenance'->>('person_'||p.id)) LIKE 'inferred_%')::int inferred_choices FROM votes v JOIN people p ON p.id=v.person_id JOIN motions m ON m.id=v.motion_id GROUP BY p.id,p.name ORDER BY count(*) DESC""");people=list(c.fetchall())
  c.execute('SELECT id,motion_id,person_id,vote,updated_at FROM votes ORDER BY id');votes=list(c.fetchall())
  result={'at':datetime.now(timezone.utc).isoformat(),'totals':totals,'people':people,'votes':votes}
  (OUT/'full-current-vote-inventory.json').write_text(json.dumps(result,indent=2,default=str))
  (OUT/'vote-repair-verification.json').write_text(json.dumps(totals,indent=2))
  print(json.dumps({'totals':totals,'colby':[p for p in people if 'harder' in p['name'].lower()]}))
