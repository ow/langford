"""CAS apply/rollback of the exact oath-backed historical-office proposal.

Default is a read-only dry run. Existing IDs, slugs, votes and transcripts remain
unchanged. Inserted rows and every updated field are retained for guarded rollback.
"""
import argparse,hashlib,json,subprocess
from datetime import datetime,timezone
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor,Json
from psycopg2 import sql
from pipeline import config
from pipeline.ingestion.vote_evidence import normalize_text
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--apply',action='store_true');p.add_argument('--rollback',action='store_true');p.add_argument('--receipt',type=Path,default=OUT/'historical-office-applied-receipt.json');args=p.parse_args()
if args.apply and args.rollback:p.error('Choose apply or rollback')
def freeze(obj):return json.loads(json.dumps(obj,default=str))
def equal(a,b):return freeze(a)==freeze(b)
if args.receipt.exists() and json.loads(args.receipt.read_text()).get('mode')=='applied' and not args.rollback:raise RuntimeError('Preserve applied receipt; use separate dryrun receipt')
plan_bytes=(OUT/'historical-office-repair-plan.json').read_bytes();plan=json.loads(plan_bytes)
before=json.loads((OUT/'historical-person-before-snapshot.json').read_text());offices=json.loads((OUT/'historical-office-before-snapshot.json').read_text())
if not args.rollback:
 for key,path in [('people_before_snapshot_sha256',OUT/'historical-person-before-snapshot.json'),('office_before_snapshot_sha256',OUT/'historical-office-before-snapshot.json')]:
  if hashlib.sha256(path.read_bytes()).hexdigest()!=plan[key]:raise RuntimeError('Before snapshot changed')
 for proof in plan['sources'].values():
  path=ROOT/proof['source_file']
  if hashlib.sha256(path.read_bytes()).hexdigest()!=proof['source_sha256']:raise RuntimeError('Official binary changed')
  cache=Path('/private/tmp')/('historical-proof-'+proof['source_sha256']+'.txt')
  if not cache.exists():subprocess.run(['pdftotext','-layout',str(path),str(cache)],check=True,capture_output=True,timeout=90)
  text=cache.read_text()
  if hashlib.sha256(text.encode()).hexdigest()!=proof['native_text_sha256'] or normalize_text(proof['source_quote']) not in normalize_text(text):raise RuntimeError('Exact official quote changed')
db=psycopg2.connect(config.DATABASE_URL,connect_timeout=15);receipt=None
try:
 with db.cursor(cursor_factory=RealDictCursor) as c:
  if args.apply or args.rollback:c.execute('LOCK TABLE people,memberships,elections,council_terms IN SHARE ROW EXCLUSIVE MODE')
  if args.rollback:
   receipt=json.loads(args.receipt.read_text());assert receipt['mode']=='applied'
   # All rows/fields must remain exactly as written before any rollback mutation.
   for change in receipt['updated_people']:
    c.execute('SELECT name,slug,is_councillor,meta,updated_at FROM people WHERE id=%s FOR UPDATE',(change['person_id'],));live=c.fetchone()
    if not equal(live,change['after']):raise RuntimeError('Rollback held: person changed')
   for group,table in [('inserted_memberships','memberships'),('inserted_terms','council_terms'),('inserted_elections','elections'),('inserted_people','people')]:
    for row in receipt[group]:
     c.execute(sql.SQL('SELECT * FROM {} WHERE id=%s FOR UPDATE').format(sql.Identifier(table)),(row['id'],))
     if not equal(c.fetchone(),row):raise RuntimeError('Rollback held: inserted '+table+' row changed')
   # Refuse to cascade newly created downstream history, even if parent timestamps
   # did not change. Remove only our exact rows in dependency order.
   inserted_ids={table:{r['id'] for r in receipt[group]} for group,table in [('inserted_memberships','memberships'),('inserted_terms','council_terms'),('inserted_elections','elections'),('inserted_people','people')]}
   for table in ['memberships','council_terms','elections','people']:
    for target in inserted_ids[table]:
     c.execute("SELECT nr.nspname schema_name,cl.relname table_name,a.attname column_name FROM pg_constraint con JOIN pg_class cl ON cl.oid=con.conrelid JOIN pg_namespace nr ON nr.oid=cl.relnamespace JOIN pg_attribute a ON a.attrelid=con.conrelid AND a.attnum=con.conkey[1] WHERE con.contype='f' AND con.confrelid=%s::regclass AND array_length(con.conkey,1)=1",(table,))
     for ref in c.fetchall():
      c.execute(sql.SQL('SELECT count(*) n FROM {}.{} WHERE {}=%s').format(sql.Identifier(ref['schema_name']),sql.Identifier(ref['table_name']),sql.Identifier(ref['column_name'])),(target,))
      if c.fetchone()['n']:raise RuntimeError('Rollback held: new downstream reference to '+table)
     c.execute(sql.SQL('DELETE FROM {} WHERE id=%s').format(sql.Identifier(table)),(target,))
   for change in receipt['updated_people']:
    b=change['before'];c.execute('UPDATE people SET name=%s,is_councillor=%s,meta=%s WHERE id=%s',(b['name'],b['is_councillor'],Json(b['meta']),change['person_id']))
   db.commit();receipt['mode']='rolled_back';receipt['rolled_back_at']=datetime.now(timezone.utc).isoformat();args.receipt.write_text(json.dumps(receipt,indent=2,default=str));print('Rolled back exact historical-office repair')
  else:
   ids=plan['preserve_person_ids'];c.execute('SELECT * FROM people WHERE id=ANY(%s) FOR UPDATE',(ids,));live={r['id']:r for r in c.fetchall()}
   if set(live)!={r['id'] for r in before['people']}:raise RuntimeError('Canonical person inventory changed')
   for row in before['people']:
    if not equal(live[row['id']],row):raise RuntimeError('Person changed since reviewed before snapshot:'+str(row['id']))
   c.execute('SELECT * FROM memberships WHERE person_id=ANY(%s) ORDER BY id FOR UPDATE',(ids,));memberships=list(c.fetchall())
   if not equal(memberships,sorted(before['memberships'],key=lambda r:r['id'])):raise RuntimeError('Existing memberships changed')
   c.execute('SELECT id,name,classification,municipality_id FROM organizations WHERE id=1');
   if not equal(c.fetchone(),plan['organization_before']):raise RuntimeError('Council organization changed')
   c.execute("SELECT * FROM elections WHERE election_date BETWEEN '2014-01-01' AND '2018-12-31' ORDER BY id FOR UPDATE");
   if not equal(c.fetchall(),offices['elections']):raise RuntimeError('Historical election inventory changed')
   c.execute("SELECT * FROM council_terms WHERE municipality_id=1 AND start_date<'2022-11-07' ORDER BY id FOR UPDATE");
   if not equal(c.fetchall(),offices['council_terms']):raise RuntimeError('Historical council-term inventory changed')
   for change in plan['name_changes']:
    c.execute('SELECT id FROM people WHERE lower(name)=lower(%s) AND id<>%s',(change['after']['name'],change['person_id']))
    if c.fetchone():raise RuntimeError('Full name already belongs to another ID')
   c.execute('SELECT id FROM people WHERE lower(name)=lower(%s) OR slug=%s',(plan['new_person']['name'],plan['new_person']['slug']))
   if c.fetchone():raise RuntimeError('Winnie canonical person now exists; revise before proposing a duplicate')
   receipt={'mode':'applied' if args.apply else 'dry_run','created_at':datetime.now(timezone.utc).isoformat(),'plan_sha256':hashlib.sha256(plan_bytes).hexdigest(),'apply_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'summary':{'name_changes':len(plan['name_changes']),'new_people':1,'new_elections':1,'new_terms':1,'new_memberships':len(plan['memberships'])},'updated_people':[],'inserted_people':[],'inserted_elections':[],'inserted_terms':[],'inserted_memberships':[],'preserved_existing_people':ids,'preserved_existing_memberships':before['memberships']}
   if args.apply:
    for change in plan['name_changes']:
     b={k:live[change['person_id']][k] for k in ('name','slug','is_councillor','meta','updated_at')};after=change['after'];c.execute('UPDATE people SET name=%s,is_councillor=%s,meta=%s WHERE id=%s RETURNING name,slug,is_councillor,meta,updated_at',(after['name'],after['is_councillor'],Json(after['meta']),change['person_id']));receipt['updated_people'].append({'person_id':change['person_id'],'before':b,'after':dict(c.fetchone())})
    n=plan['new_person'];c.execute('INSERT INTO people(name,slug,is_councillor,meta) VALUES(%s,%s,%s,%s) RETURNING *',(n['name'],n['slug'],n['is_councillor'],Json(n['meta'])));receipt['inserted_people'].append(dict(c.fetchone()))
    e=plan['election'];c.execute('INSERT INTO elections(name,election_date,classification,term_length_years,results_status,source_url) VALUES(%s,%s,%s,%s,%s,%s) RETURNING *',(e['name'],e['election_date'],e['classification'],e['term_length_years'],e['results_status'],e['source_url']));election=dict(c.fetchone());receipt['inserted_elections'].append(election)
    t=plan['council_term'];c.execute('INSERT INTO council_terms(municipality_id,election_id,name,start_date,end_date,meta) VALUES(%s,%s,%s,%s,%s,%s) RETURNING *',(t['municipality_id'],election['id'],t['name'],t['start_date'],t['end_date'],Json(t['meta'])));term=dict(c.fetchone());receipt['inserted_terms'].append(term)
    for m in plan['memberships']:
     c.execute('INSERT INTO memberships(person_id,organization_id,role,start_date,end_date,meta,council_term_id) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *',(m['person_id'],m['organization_id'],m['role'],m['start_date'],m['end_date'],Json(m['meta']),term['id'] if m['council_term'] else None));receipt['inserted_memberships'].append(dict(c.fetchone()))
    # Durable pending recovery evidence precedes commit; final applied mode is
    # published only once PostgreSQL confirms the transaction.
    pending=args.receipt.with_suffix('.pending.json');pending.write_text(json.dumps({**receipt,'mode':'pending_commit'},indent=2,default=str));db.commit();args.receipt.write_text(json.dumps(receipt,indent=2,default=str));pending.unlink()
   else:db.rollback();args.receipt.write_text(json.dumps(receipt,indent=2,default=str))
   print(json.dumps(receipt['summary']))
except Exception:
 db.rollback();raise
finally:db.close()
