"""Read-only exact-row verification of applied office repair."""
import json
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor
from pipeline import config
OUT=Path(__file__).parent;r=json.loads((OUT/'historical-office-applied-receipt.json').read_text());b=json.loads((OUT/'historical-person-before-snapshot.json').read_text())
def freeze(obj):return json.loads(json.dumps(obj,default=str))
with psycopg2.connect(config.DATABASE_URL,connect_timeout=15) as db:
 with db.cursor(cursor_factory=RealDictCursor) as c:
  for change in r['updated_people']:
   c.execute('SELECT name,slug,is_councillor,meta,updated_at FROM people WHERE id=%s',(change['person_id'],));assert freeze(c.fetchone())==change['after'];assert change['before']['slug']==change['after']['slug']
  for key,table in [('inserted_people','people'),('inserted_elections','elections'),('inserted_terms','council_terms'),('inserted_memberships','memberships')]:
   for row in r[key]:
    c.execute('SELECT * FROM '+table+' WHERE id=%s',(row['id'],));assert freeze(c.fetchone())==row
  for row in r['preserved_existing_memberships']:
   c.execute('SELECT * FROM memberships WHERE id=%s',(row['id'],));assert freeze(c.fetchone())==row
  changed={p['person_id'] for p in r['updated_people']}
  for old in b['people']:
   if old['id'] in changed:continue
   c.execute('SELECT * FROM people WHERE id=%s',(old['id'],));assert freeze(c.fetchone())==old
  result={'verified_name_expansions':len(r['updated_people']),'verified_new_people':len(r['inserted_people']),'winnie_person_id':r['inserted_people'][0]['id'],'existing_s_sifert_person_id_unchanged':91,'verified_inserted_memberships':len(r['inserted_memberships']),'existing_memberships_preserved':len(r['preserved_existing_memberships']),'election_id':r['inserted_elections'][0]['id'],'council_term_id':r['inserted_terms'][0]['id'],'preserved_existing_person_ids':r['preserved_existing_people']}
  (OUT/'historical-office-applied-verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
