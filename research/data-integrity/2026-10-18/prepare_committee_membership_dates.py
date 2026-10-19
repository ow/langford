"""Read-only primary-source committee appointment date correction plan.

No apply mode: exact before-values and rollback values are saved for review.
"""
from pathlib import Path
import json,hashlib,re,subprocess
import psycopg2
from psycopg2.extras import RealDictCursor
from pipeline import config
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
proofs={}
specs={
 'councillors':('archive/langford/Council/2023/02/2023-02-22 700pm Regular Council [5b91d08c]/Minutes/Minutes - SIGNED.pdf',r'(?s)9\.6\s+Committee Terms of Reference.*?MOVED BY:.*?Motion CARRIED\.'),
 'whiteway':('archive/langford/Council/2024/07/2024-07-15 300pm Special Council [ff6f7de5]/Minutes/Minutes - SIGNED.pdf',r'(?s)THAT Council appoint Jacquie Whiteway to the Community Advisory Committee\s+for a term ending on December 31, 2026\.'),
}
for key,(relative,pattern)in specs.items():
 path=ROOT/relative;text=subprocess.check_output(['pdftotext','-layout',str(path),'-']).decode();hit=re.search(pattern,text);assert hit,key
 proofs[key]={'source_file':relative,'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'source_url':Path(str(path)+'.url').read_text().strip(),'source_quote':hit[0],'pdf_page':text[:hit.start()].count('\f')+1,'effective_from':'2023-02-21'if key=='councillors'else'2024-07-15'}
assert 'February 21, 2023'in subprocess.check_output(['pdftotext','-layout',str(ROOT/specs['councillors'][0]),'-']).decode()[:500]
with psycopg2.connect(config.DATABASE_URL,connect_timeout=15)as db:
 db.set_session(readonly=True)
 with db.cursor(cursor_factory=RealDictCursor)as cur:
  cur.execute('SELECT to_jsonb(m) membership,p.name,o.name organization_name FROM memberships m JOIN people p ON p.id=m.person_id JOIN organizations o ON o.id=m.organization_id WHERE m.organization_id=9 AND m.person_id=ANY(%s) ORDER BY m.person_id',([20,21,34,40],));before=list(cur.fetchall())
assert len(before)==4
changes=[]
for row in before:
 old=row['membership'];key='whiteway'if old['person_id']==40 else'councillors';proof=proofs[key];after={**old,'start_date':proof['effective_from']};after['meta']={**(old.get('meta')or{}),'committee_appointment_date_correction':{'original_start_date':old['start_date'],'source_url':proof['source_url'],'source_sha256':proof['source_sha256'],'source_quote':proof['source_quote'],'method':'explicit_official_council_appointment_resolution','verified_on':'2026-10-18'}}
 if key=='whiteway':after['end_date']='2026-12-31'
 changes.append({'membership_id':old['id'],'person_id':old['person_id'],'name':row['name'],'organization_id':9,'organization_name':row['organization_name'],'before':old,'after':after,'rollback':old,'changed_fields':['start_date','meta']+(['end_date']if key=='whiteway'else[]),'guard':'Require entire live membership to equal before; preserve identity/role/othermetadata. Rollback only if current equals applied after.'})
result={'mode':'read_only_committee_appointment_dates_plan_no_writes','summary':{'memberships':4,'start_date_corrections':4,'explicit_citizen_term_end_corrections':1,'database_writes':0},'source_proofs':proofs,'changes':changes,'preserve':'All person IDs, historical vote IDs, agenda links, Council term memberships, other roles and unrelated metadata remain unchanged. No guessed initial citizen appointment dates; Klaver andS.Mayer untouched.'}
f=OUT/'committee-membership-date-correction-plan.json';f.write_text(json.dumps(result,indent=2,default=str)+'\n');print(json.dumps(result['summary']));print('plan_sha256',hashlib.sha256(f.read_bytes()).hexdigest())
