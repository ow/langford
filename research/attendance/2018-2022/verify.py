"""Independent read-only readback against the visual ledger and original bytes.
Does not import the planner or writer and does not trust writer counts.
"""
import argparse,hashlib,json
from pathlib import Path
from collections import Counter
import psycopg2
from psycopg2.extras import RealDictCursor
from pipeline import config

a=argparse.ArgumentParser();a.add_argument('--before',required=True);a.add_argument('--reviewed',required=True);a.add_argument('--repo',required=True);a.add_argument('--output',required=True);args=a.parse_args()
before=json.loads(Path(args.before).read_text());review=json.loads(Path(args.reviewed).read_text());mapping={'Y':143,'D':133,'M':134,'L':135,'N':136,'S':35,'R':137};ids=[m['id']for m in before['meetings']]
expected={}
for mid,states in review['reviewed'].items():
 for state,letters in zip(['present','absent','unknown'],states.split('|')):
  for letter in letters:expected[int(mid),mapping[letter]]=state
c=psycopg2.connect(config.DATABASE_URL,connect_timeout=15);c.set_session(readonly=True,isolation_level='REPEATABLE READ')
with c.cursor(cursor_factory=RealDictCursor)as q:
 q.execute('SELECT * FROM attendance WHERE meeting_id=ANY(%s) ORDER BY id',(ids,));rows=json.loads(json.dumps(q.fetchall(),default=str))
 q.execute('SELECT id,organization_id,meeting_date,title,type,status,archive_path,minutes_url,agenda_url,meta,slug,chair_person_id FROM meetings WHERE id=ANY(%s) ORDER BY meeting_date,id',(ids,));meetings=json.loads(json.dumps(q.fetchall(),default=str))
 q.execute('SELECT ms.*,p.name FROM memberships ms JOIN people p ON p.id=ms.person_id WHERE ms.organization_id=1 ORDER BY ms.id');memberships=json.loads(json.dumps(q.fetchall(),default=str))
c.rollback();c.close()
assert memberships==before['memberships'],'Council roles/service changed'
old={(r['meeting_id'],r['person_id']):r for r in before['attendance']};actual={(r['meeting_id'],r['person_id']):r for r in rows};dates={m['id']:m['meeting_date']for m in before['meetings']};counts=Counter();by_person={pid:Counter()for pid in mapping.values()};unknown=[];verified=[]
for key,state in expected.items():
 if state=='unknown':
  unknown.append({'meeting_id':key[0],'person_id':key[1]});by_person[key[1]]['unknown']+=1
  assert key not in actual or actual[key]==old.get(key),'An unresolved case was changed'
  continue
 r=actual[key];e=json.loads(r['notes']);assert e['schema']=='council-attendance/v1'and(e['meeting_id'],e['person_id'])==key
 assert e['state']==state and e['local_date']==dates[key[0]]
 docs=[d for d in before['documents']if d['meeting_id']==key[0]and d['source_url']==e['source_url']and(d['file_path']or'').startswith('Minutes/')];assert len(docs)==1
 m=next(m for m in before['meetings']if m['id']==key[0]);source=Path(args.repo)/m['archive_path']/docs[0]['file_path'];assert hashlib.sha256(source.read_bytes()).hexdigest()==e['source_sha256']
 assert r['attendance_mode']==('Unknown'if state=='present'else'Absent')
 assert r['arrival_time']==old.get(key,{}).get('arrival_time')and r['departure_time']==old.get(key,{}).get('departure_time')
 assert e['source_page']==(3 if key==(347,143)else 1)
 assert e['method']==('original_minutes_attendance'if key==(347,143)else'original_roster')
 if key in old:assert r['id']==old[key]['id']and r['created_at']==old[key]['created_at']
 counts[state]+=1;by_person[key[1]][state]+=1;verified.append(key)
# Every non-council row and every unresolved original row must be byte-for-byte
# identical after JSON normalization. No unexpected rows can enter this corpus.
protected=[r for r in before['attendance']if(r['meeting_id'],r['person_id'])not in verified]
for r in protected:assert actual[r['meeting_id'],r['person_id']]==r
assert set(actual)==set(old)|set(verified)
for m,b in zip(meetings,before['meetings']):
 assert m['id']==b['id']
 if m['id']==123:
  assert m['status']=='Cancelled'
  assert m['meta']=={**(b['meta']or{}),'cancellation_evidence':{'schema':'meeting-cancellation/v1',**review['cancellation']}}
  for key in b:
   if key not in ['status','meta']:assert m[key]==b[key]
 else:assert m==b
report={'outcome':'independent_readback_passed','verified_records':len(verified),'states':dict(counts),'unknown_cases':unknown,'by_person':{str(k):dict(v)for k,v in by_person.items()},'cancelled_meetings_excluded':[123],'protected_attendance_rows_unchanged':len(protected),'council_memberships_unchanged':True,'other_88_meeting_records_unchanged':True,'all_source_hashes_rechecked':True,'corpus_attendance_rows':len(rows)}
Path(args.output).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
