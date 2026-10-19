"""Prepare only: documentary names, oath dates and statutory continuation.

No database/network writes. Full term-start history before2018 remains incomplete;
precise continuing-office interval does not assert an invented2014start date.
"""
import json,hashlib,re,subprocess
from pathlib import Path
from pipeline.ingestion.vote_evidence import normalize_text
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
before=json.loads((OUT/'historical-person-before-snapshot.json').read_text());office=json.loads((OUT/'historical-office-before-snapshot.json').read_text());people={p['id']:p for p in before['people']}
specs={
 '2018_declaration':('archive/langford/Council/2018/11/2018-11-05 Regular Council [legacy]/Agenda/20181105-Inaugural-Agenda-Package.pdf',r'In view of the above results,[\s\S]*?for a four-year term\.'),
 '2018_councillor_oaths':('archive/langford/Council/2018/11/2018-11-05 Regular Council [legacy]/Minutes/20181105-Signed-Minutes-Inaugural-Meeting.pdf',r'Chief Administrative Officer Kiedyk \(Deputy Corporate Officer\) swore into office Councillors D\. Blackwell,[\s\S]*?and R\. Wade\.'),
 '2018_mayor_oath':('archive/langford/Council/2018/11/2018-11-19 Regular Council [legacy]/Minutes/20181119-Signed.pdf',r'Corporate Officer Braden Hutchins swore Mayor Young into office\.'),
 '2022_successor_oaths':('archive/langford/Council/2022/11/2022-11-22 700pm Special Council [c145d400]/Agenda/Agenda.pdf',r'Chief Administrative Officer Kiedyk \(Deputy Corporate Officer\) sworn into office Mayor\s+Goodmanson and Councillors K\. Guiry,[\s\S]*?Yacucha\.'),
 '2018_winnie_council_roster':('archive/langford/Council/2019/06/2019-06-17 Regular Council [legacy]/Agenda/20190617-Agenda-Package.pdf',r'MAYOR AND COUNCIL[\s\S]*?COUNCIL ADVISORY COMMITTEES'),
}
proofs={}
for key,(relative,pattern) in specs.items():
 path=ROOT/relative;digest=hashlib.sha256(path.read_bytes()).hexdigest();cache=Path('/private/tmp')/('historical-proof-'+digest+'.txt')
 if not cache.exists():subprocess.run(['pdftotext','-layout',str(path),str(cache)],check=True,capture_output=True,timeout=90)
 text=cache.read_text();hit=re.search(pattern,text)
 if not hit:raise RuntimeError('Missing exact documentary quote:'+key)
 proofs[key]={'source_file':relative,'source_sha256':digest,'source_url':Path(str(path)+'.url').read_text().strip(),'native_text_sha256':hashlib.sha256(text.encode()).hexdigest(),'source_quote':hit[0],'pdf_page':text[:hit.start()].count('\f')+1}
 # Ensure date proof belongs to the quoted official minutes, not another item.
 if key=='2018_councillor_oaths':assert 'November 5th, 2018' in text[:hit.start()]
 if key=='2018_mayor_oath':assert 'November 19th, 2018' in text[:hit.start()]
 if key=='2022_successor_oaths':assert 'Special Inaugural Council Minutes\nNovember 7, 2022' in text[max(0,hit.start()-4000):hit.start()]
 assert normalize_text(hit[0]) in normalize_text(text)
assert 'Winnie Sifert' in proofs['2018_winnie_council_roster']['source_quote']
name_map={133:'Denise Blackwell',134:'Matt Sahlstrom',135:'Lanny Seaton',136:'Norma Stewart',137:'Roger Wade'}
name_changes=[]
for pid,name in name_map.items():
 old=people[pid];assert old['name'][0]==name[0] and old['name'].split()[-1]==name.split()[-1]
 name_changes.append({'person_id':pid,'before':{k:old[k] for k in ('name','slug','is_councillor','meta','updated_at')},'after':{'name':name,'is_councillor':True,'meta':{**(old['meta'] or {}),'historical_identity_evidence':{'original_display_name':old['name'],'canonical_name':name,'source_url':proofs['2018_declaration']['source_url'],'source_sha256':proofs['2018_declaration']['source_sha256'],'oath_source_url':proofs['2018_councillor_oaths']['source_url'],'verified_on':'2026-10-18'}}},'preserve_slug':True})
rows=[]
for pid in [133,134,135,136,137,35,143]:
 mayor=pid==143;key='2018_mayor_oath' if mayor else '2018_councillor_oaths';start='2018-11-19' if mayor else '2018-11-05'
 rows.append({'person_id':pid,'organization_id':1,'role':'Mayor' if mayor else 'Councillor','start_date':start,'end_date':'2022-11-06','council_term':'2018–2022 Council','meta':{'interval_kind':'elected_term_after_documented_oath','start_source_url':proofs[key]['source_url'],'start_source_sha256':proofs[key]['source_sha256'],'start_source_quote':proofs[key]['source_quote'],'end_source_url':proofs['2022_successor_oaths']['source_url'],'end_source_sha256':proofs['2022_successor_oaths']['source_sha256'],'end_basis':'CommunityCharter119(1)(b): immediately before2022inauguralCouncilmeeting; successorsoathNovember7,2022','statute_url':'https://www.bclaws.gov.bc.ca/civix/document/id/complete/statreg/03026_05#section119','verified_on':'2026-10-18'}})
# This is a precise statutory continuation interval, not a guessed2014term start.
rows.append({'person_id':143,'organization_id':1,'role':'Mayor','start_date':'2018-11-05','end_date':'2018-11-18','council_term':None,'meta':{'interval_kind':'documented_continuation_of_previous_term_until_successor_oath','basis':'CommunityCharter119(3): previousMayorcontinuesuntilsuccessortakesoffice; incumbentYoungabsentNov5,re-electedYoungswornNov19. Sameperson, continuousservice.','original_term_start':'not_asserted_pending2014inauguralproof','statute_url':'https://www.bclaws.gov.bc.ca/civix/document/id/complete/statreg/03026_05#section119','source_urls':[proofs['2018_councillor_oaths']['source_url'],proofs['2018_mayor_oath']['source_url']],'source_sha256s':[proofs['2018_councillor_oaths']['source_sha256'],proofs['2018_mayor_oath']['source_sha256']],'verified_on':'2026-10-18'}})
plan={'mode':'source_verified_historical_office_proposal_no_writes','organization_before':office['organization'],'people_before_snapshot_sha256':hashlib.sha256((OUT/'historical-person-before-snapshot.json').read_bytes()).hexdigest(),'office_before_snapshot_sha256':hashlib.sha256((OUT/'historical-office-before-snapshot.json').read_bytes()).hexdigest(),'sources':proofs,'name_changes':name_changes,'new_person':{'name':'Winnie Sifert','slug':'winnie-sifert','is_councillor':True,'meta':{'display_name_source':proofs['2018_winnie_council_roster']['source_url'],'display_name_source_sha256':proofs['2018_winnie_council_roster']['source_sha256'],'historical_identity_evidence':{'canonical_name':'Winnie Sifert','documentary_initial':'W. Sifert','do_not_merge_person_ids':[91],'limitation':'No guessedmembershipdates. ExistingS.Sifertidentity remains unchanged; publiccitysource also separatelynamesdaughterSandySifert.'}}},'new_person_membership_status':'No Winniedatedmembership proposal until exacthistoricaloath/termdate evidence.','election':{'name':'2018 General Local Election','election_date':'2018-10-20','classification':'General','term_length_years':4,'results_status':'official','source_url':proofs['2018_declaration']['source_url']},'council_term':{'municipality_id':1,'name':'2018–2022 Council','start_date':'2018-11-05','end_date':'2022-11-06','meta':{'start_source_url':proofs['2018_councillor_oaths']['source_url'],'start_source_sha256':proofs['2018_councillor_oaths']['source_sha256'],'end_source_url':proofs['2022_successor_oaths']['source_url'],'end_source_sha256':proofs['2022_successor_oaths']['source_sha256'],'mayor_oath_exception':'MayorYoungswornNov19; previousincumbentcontinuesunderCommunityCharter119(3)untilthen.'}},'memberships':rows,'preserve_person_ids':[35,91,133,134,135,136,137,143],'preserve_existing_votes_transcripts_memberships':True,'statutory_source':'https://www.bclaws.gov.bc.ca/civix/document/id/complete/statreg/03026_05#section119','remaining_limitations':['No guessed2014termstart','No historical819inferencebeforeactualruleproof','No S.Sifert/Winnie merge','No rewriteexisting1993–2022Stewservice_history']}
(OUT/'historical-office-repair-plan.json').write_text(json.dumps(plan,indent=2));print(json.dumps({'name_changes':len(name_changes),'new_people':1,'new_memberships':len(rows),'elections':1,'council_terms':1,'source_files':len(proofs),'plan_sha256':hashlib.sha256((OUT/'historical-office-repair-plan.json').read_bytes()).hexdigest()}),flush=True)
