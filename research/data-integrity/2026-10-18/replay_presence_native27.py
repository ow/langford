"""Read-only physical grammar replay; no ballot eligibility or database writes."""
import hashlib,json,re,subprocess,types
from collections import Counter
from pathlib import Path
from datetime import datetime,timezone
from pipeline.ingestion import official_ballots as official
from pipeline.ingestion import ballot_reconstruction as current
from pipeline.ingestion.committee_ballots import CAC_CITIZENS,CAC_COUNCILLORS
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
norm=lambda s:re.sub(r'[^a-z0-9]+',' ',s.casefold()).strip()
baseline=types.ModuleType('pipeline.ingestion.pre_presence')
exec(subprocess.run(['git','show','230ef91:apps/pipeline/pipeline/ingestion/ballot_reconstruction.py'],cwd=ROOT,capture_output=True,text=True,check=True).stdout,baseline.__dict__)
census=json.loads((OUT/'presence179-native-source-census.json').read_bytes())
snapshot=json.loads((OUT/'ballot-source-current-snapshot.json').read_bytes());meetings={m['id']:m for m in snapshot['meetings']}
people=json.loads((OUT/'vote-people-current-snapshot.json').read_bytes());records=[]
for prior in census['records']:
 mid=prior['meeting_id'];meeting=meetings[mid]
 source=official.load_official_minutes(meeting,root=ROOT,people=people,cache_dir=Path('/private/tmp/presence27-replay-native'))
 assert not source.get('error'),(mid,source)
 binary=ROOT/source['source_file'];assert sha(binary)==prior['source_sha256']==source['source_sha256']
 if binary.suffix.lower()=='.html':
  from bs4 import BeautifulSoup
  raw=BeautifulSoup(binary.read_text(),'html.parser').get_text('\n',strip=True)
 else:raw=subprocess.run(['pdftotext','-layout',str(binary),'-'],capture_output=True,text=True,check=True).stdout
 pool=[];roles={}
 if source['source_classification']=='Committee':
  known={p['id']:p for p in people if norm(p['name']) in CAC_CITIZENS|CAC_COUNCILLORS};known.update({p['id']:p for p in source['present']});pool=list(known.values())
  new,held=current.physical_presence_events(source['text'],pool)
 else:
  original=official.physical_presence_events
  def capture(text,voting_people,role_bindings=None):
   pool.extend(voting_people);roles.update(role_bindings or {});return current.physical_presence_events(text,voting_people,role_bindings)
  official.physical_presence_events=capture
  try:new,held=official.event_timeline(source,snapshot['memberships'])
  finally:official.physical_presence_events=original
 old,oldheld=baseline.physical_presence_events(source['text'],pool,roles)
 oldkeys={(e['offset'],e['person_id'],e['state'])for e in old};ids={p['id']:p['name']for p in pool}
 enriched=[]
 for event in new:
  pos=event['offset'];start=source['text'].rfind('\n\n',0,pos);stop=source['text'].find('\n\n',pos)
  paragraph=source['text'][start+2 if start>=0 else 0:stop if stop>=0 else len(source['text'])].strip()
  quote=event['source_quote'];identity=norm(ids[event['person_id']]).split()[-1]
  witness=norm(paragraph) in norm(raw)
  assert witness,(mid,pos,paragraph)
  assert identity in norm(re.sub(r'\b(Councillor|Mayor)(?=[A-Z][a-z])',r'\1 ',quote)).split() or event.get('role_binding'),(mid,event)
  enriched.append({**event,'name':ids[event['person_id']],'newly_accepted':(pos,event['person_id'],event['state'])not in oldkeys,'native_paragraph':paragraph,'native_paragraph_verified':witness})
 records.append({'meeting_id':mid,'date':source['local_date'],'classification':source['source_classification'],'source_file':source['source_file'],'source_url':source['source_url'],'source_sha256':source['source_sha256'],'timeline_identity_pool':pool,'events':enriched,'retained_holds':held,'baseline_events':old,'baseline_holds':oldheld,'baseline_events_removed':[e for e in old if (e['offset'],e['person_id'],e['state'])not in {(x['offset'],x['person_id'],x['state'])for x in new}],'census_tokens':[{'offset':e['offset'],'before_quote':e['source_quote'],'still_held':any(h['offset']==e['offset']for h in held)}for e in prior['events']]})
result={'mode':'read_only_native_physical_replay_no_ballot_eligibility_claim','created_at':datetime.now(timezone.utc).isoformat(),'helper_sha256':sha(ROOT/'apps/pipeline/pipeline/ingestion/ballot_reconstruction.py'),'baseline_commit':'230ef91','census_sha256':sha(OUT/'presence179-native-source-census.json'),'summary':{'sources':len(records),'events':sum(len(r['events'])for r in records),'newly_accepted_events':sum(e['newly_accepted']for r in records for e in r['events']),'baseline_events_removed':sum(len(r['baseline_events_removed'])for r in records),'retained_holds':sum(len(r['retained_holds'])for r in records),'census_tokens':sum(len(r['census_tokens'])for r in records),'census_tokens_still_held':sum(e['still_held']for r in records for e in r['census_tokens']),'database_writes':0},'records':records}
p=OUT/'presence27-native-physical-replay.json';p.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['summary']));print('sha256',sha(p))
for r in records:
 print(r['meeting_id'],r['classification'],'new',[(e['name'],e['state'],e['verb'])for e in r['events']if e['newly_accepted']],'removed',len(r['baseline_events_removed']),'held',[(h['offset'],h['source_quote'][:100])for h in r['retained_holds']])
