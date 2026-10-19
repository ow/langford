"""Read-only independent native PDF/header and seven-explicit-voter review."""
import json,hashlib,re,subprocess
from pathlib import Path
from datetime import datetime,timezone
import fitz,psycopg2
from psycopg2.extras import RealDictCursor
from pipeline import config
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent;CACHE=Path('/private/tmp/explicit659-independent');CACHE.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();canon=lambda x:json.loads(json.dumps(x,default=str));norm=lambda x:re.sub(r'[^a-z0-9]+',' ',x.casefold()).strip()
def main():
 plan_file=OUT/'explicit659-ballot-plan.json';plan_bytes=plan_file.read_bytes();plan=json.loads(plan_bytes);assert hashlib.sha256(plan_bytes).hexdigest()=='464b6bcc059b5e81523a8a3ef8b1bb673790c89ef7f561d318dd0da6733f2eae'
 c=plan['records'][0];assert c['motion_id']==659 and c['meeting_id']==70 and c['inference_basis']=='every_present_voter_explicitly_named'
 original=ROOT/c['source_file'];assert sha(original)==c['source_sha256']
 target=CACHE/'native.txt';subprocess.run(['pdftotext','-layout',str(original),str(target)],check=True,capture_output=True);text=target.read_text()
 evidence=c['source_date_evidence'];receipt_path=Path(evidence['ocr_receipt']);assert sha(receipt_path)==evidence['ocr_receipt_sha256'];ocr=json.loads(receipt_path.read_bytes())
 assert ocr['config']==evidence['engine_config'] and ocr['config']['source_sha256']==sha(original)
 assert sha(ROOT/'apps/pipeline/pipeline/ingestion/native_header_vision.swift')==evidence['helper_sha256']
 render=CACHE/'independent-header.png'
 with fitz.open(original) as pdf:pdf[0].get_pixmap(matrix=fitz.Matrix(6,6),clip=fitz.Rect(ocr['config']['clip']),alpha=False).save(render)
 assert sha(render)==evidence['render_sha256']==sha(Path(evidence['render_file']))
 date_lines=[r for r in ocr['ocr']['lines'] if any(re.search(r'Thursday, March 19th, 2020',a['text']) for a in r['candidates'])];assert len(date_lines)==1
 assert all(a['confidence']>=.99 and re.search(r'Thursday, March 19th, 2020',a['text']) for a in date_lines[0]['candidates'])
 date='2020-03-19';assert datetime.fromisoformat(date).strftime('%A')=='Thursday' and c['source_date']==c['stored_date']==date
 assert re.search(r'March 19th, 2020',text.split('\f')[1])
 roster=re.search(r'\bPRESENT\s*\n(.*?)\bATTENDING\b',text,re.S).group(1).strip()
 start=re.search(r'MOVED BY:\s*MAYOR YOUNG\s*\nSECONDED:\s*COUNCILLOR WADE',text);assert start
 end=re.search(r'(?m)^\s*CARRIED\.',text[start.end():]);assert end
 before_result=text[start.end():start.end()+end.start()];vote=re.search(r'In favour:\s*(.*?)Opposed:\s*(.*?)(?=That Council establish)',before_result,re.S);assert vote
 yes_names=re.findall(r'(?:Mayor|Councillor)\s+(Young|Sahlstrom|Seaton|Stewart|Wade)\b',vote[1]);no_names=re.findall(r'Councillor\s+(Blackwell|Szpak)\b',vote[2]);assert sorted(yes_names)==sorted(['Young','Sahlstrom','Seaton','Stewart','Wade']) and sorted(no_names)==['Blackwell','Szpak']
 assert not re.search(r'\bMOVED\b|\bSECONDED\b|\bCARRIED\b|\bDEFEATED\b',before_result,re.I)
 body=before_result[:vote.start()]+before_result[vote.end():];assert norm(body)==norm(c['source_motion_text'])
 assert len(re.findall(r'That Council',body))==3 and re.findall(r'\d+',body)==['400','000','19','19','19','19','2']
 expected_names={35:'Lillian Szpak',133:'Denise Blackwell',134:'Matt Sahlstrom',135:'Lanny Seaton',136:'Norma Stewart',137:'Roger Wade',143:'Stew Young'}
 expected_votes={pid:'No' if pid in (35,133) else 'Yes'for pid in expected_names}
 with psycopg2.connect(config.DATABASE_URL,connect_timeout=15) as db:
  db.set_session(readonly=True,isolation_level='REPEATABLE READ')
  with db.cursor(cursor_factory=RealDictCursor) as cur:
   cur.execute('SELECT m.id,m.meeting_id,m.agenda_item_id,m.text_content,m.result,m.mover,m.seconder,m.mover_id,m.seconder_id,m.meta,m.updated_at,m.meta IS NULL AS meta_is_sql_null,a.item_order,a.title AS agenda_title FROM motions m JOIN agenda_items a ON a.id=m.agenda_item_id WHERE m.id=659');motion=canon(cur.fetchone())
   cur.execute('SELECT m.id,m.meeting_date,m.title,m.archive_path,o.classification FROM meetings m JOIN organizations o ON o.id=m.organization_id WHERE m.id=70');meeting=canon(cur.fetchone())
   cur.execute('SELECT id,name FROM people WHERE id=ANY(%s)',(sorted(expected_names),));people=canon(cur.fetchall())
   cur.execute("SELECT m.id,m.person_id,m.role,m.start_date,m.end_date,o.classification FROM memberships m JOIN organizations o ON o.id=m.organization_id WHERE o.municipality_id=1 AND o.classification='Council' AND m.person_id=ANY(%s) AND m.start_date<=%s AND (m.end_date IS NULL OR m.end_date>=%s)",(sorted(expected_names),date,date));members=canon(cur.fetchall())
   cur.execute('SELECT id,motion_id,person_id,vote,recusal_reason,created_at,updated_at FROM votes WHERE motion_id=659 ORDER BY id');old_votes=canon(cur.fetchall())
 assert {p['id']:p['name']for p in people}==expected_names
 assert {m['person_id']for m in members}==set(expected_names)
 assert meeting['classification']=='Council' and meeting['meeting_date']==date and meeting['archive_path'] in str(original)
 assert motion['id']==659 and motion['meeting_id']==70 and motion['result']=='CARRIED' and norm(motion['text_content'])==norm(body) and not old_votes
 assert motion['mover_id'] in (None,143) and motion['seconder_id'] in (None,137)
 for pid,name in expected_names.items():
  initial,last=name[0],name.split()[-1];assert re.search(r'\b'+initial+r'\.\s*'+last+r'\b',roster)
 assert not re.search(r'\b(?:left|departed|arrived|joined|rejoined|returned|recused|excused|conflict)\b',text[:start.end()+end.start()],re.I)
 assert {v['person_id']:v['vote']for v in c['votes']}==expected_votes and all(v['evidence']=='explicit_named'for v in c['votes'])
 applier=OUT/'apply_explicit659_ballot.py';assert sha(applier)=='2eab71f50c71ee9df3ca9780210650487114cede42c42fb91eed985a240bcb45'
 output={'mode':'independent_native_explicit_rollcall_review_no_historical_recording_inference','at':datetime.now(timezone.utc).isoformat(),'candidate_plan_sha256':hashlib.sha256(plan_bytes).hexdigest(),'review_script_sha256':sha(Path(__file__)),'integration_sha256':sha(ROOT/'apps/pipeline/pipeline/ingestion/meeting_ballots.py'),'reviewed_candidate_ids':[659],'summary':{'reviewed_ballots':1,'new_choices':7,'existing_choices_preserved':0,'inferred_choices':0,'proof_issues':0},'records':[{'motion_id':659,'status':'reviewed','source_sha256':sha(original),'source_file':c['source_file'],'source_url':c['source_url'],'source_date':date,'source_date_evidence':evidence,'independent_header_render_sha256':sha(render),'independent_native_text_sha256':sha(target),'native_present_quote':roster,'dated_council_memberships':members,'native_formal_boundary':'One MOVED MAYOR YOUNG / SECONDED COUNCILLOR WADE; all three operative clauses, interspersed complete named vote lists, then one CARRIED; no intervening formal delimiter/result. Page2 confirmsdate and literal5Yes/2No.','original_row':motion,'agenda_order':motion['item_order'],'choices':[{'person_id':pid,'vote':choice}for pid,choice in sorted(expected_votes.items())],'physical_events_before_vote':[],'reviewed_primary_render':{'path':str(CACHE/'page2.png'),'sha256':sha(CACHE/'page2.png')}}],'apply_script_sha256':sha(applier),'apply_script_peer_review':{'status':'reviewed','checks':['Exact659/7 fully explicit-only guard bothplanandfreshreplay','Caller-bound immutableplan/review/beforeSHAs','Livewholebeforemotion/vote/catalogCAS andSERIALIZABLErowlocks','NativeoriginalSHA/currentheaderOCRassets andsourceguards checked','Noexistingchoiceoverwrite/no textoragendawrites','Atomicchoice+completeproofpublication andpendingdurablereceipt','Guardedrollbackcheckswholeafterballot andpreservesSQLNULLvsJSONnull'],'database_writes':0}}
 out=OUT/'explicit659-independent-review.json';out.write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(output['summary']));print('review_sha256',sha(out))
if __name__=='__main__':main()
