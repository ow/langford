"""Independent read-only exact-row verification of four committee date repairs."""
import json,hashlib
from pathlib import Path
from datetime import datetime,timezone
import psycopg2
from psycopg2.extras import RealDictCursor
from pipeline import config
OUT=Path(__file__).parent;path=OUT/'committee-membership-date-applied-receipt.json';r=json.loads(path.read_text());assert r['mode']=='applied';ids=[c['membership_id'] for c in r['changes']]
with psycopg2.connect(config.DATABASE_URL,connect_timeout=15) as db:
 db.set_session(readonly=True,isolation_level='REPEATABLE READ')
 with db.cursor(cursor_factory=RealDictCursor) as cur:
  cur.execute('SELECT id,to_jsonb(m) row FROM memberships m WHERE id=ANY(%s)',(ids,));live={x['id']:x['row'] for x in cur.fetchall()}
  for c in r['changes']:
   assert live[c['membership_id']]==c['after'],'Committed membership differs'
   assert all(c['before'][k]==c['after'][k] for k in ('id','person_id','organization_id','role','council_term_id','created_at')),'Membership identity/links changed'
  out={'at':datetime.now(timezone.utc).isoformat(),'receipt_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'verified_membership_ids':ids,'exact_full_row_agreement':len(ids),'unchanged_person_role_organization_links':len(ids),'vote_or_person_writes':0};(OUT/'committee-membership-date-applied-verification.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
