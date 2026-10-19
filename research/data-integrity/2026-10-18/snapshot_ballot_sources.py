import json
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor
from pipeline import config
out=Path(__file__).parent
with psycopg2.connect(config.DATABASE_URL,connect_timeout=15) as db:
 with db.cursor(cursor_factory=RealDictCursor) as c:
  queries={'meetings':"SELECT m.id,m.title,m.meeting_date,m.type,m.archive_path,m.minutes_url,m.meta,o.name organization_name,o.classification FROM meetings m LEFT JOIN organizations o ON o.id=m.organization_id WHERE m.municipality_id=1",'memberships':"SELECT p.id person_id,p.name,ms.organization_id,ms.role,ms.start_date,ms.end_date,o.name organization_name,o.classification FROM memberships ms JOIN people p ON p.id=ms.person_id JOIN organizations o ON o.id=ms.organization_id WHERE o.municipality_id=1",'attendance':"SELECT a.meeting_id,a.person_id,a.attendance_mode,a.notes FROM attendance a JOIN meetings m ON m.id=a.meeting_id WHERE m.municipality_id=1",'motions':"SELECT m.id,m.meeting_id,m.agenda_item_id,m.text_content,m.result,m.meta,m.mover,m.seconder,a.item_order,a.title item_title FROM motions m JOIN agenda_items a ON a.id=m.agenda_item_id"}
  data={}
  for key,q in queries.items():c.execute(q);data[key]=list(c.fetchall())
  (out/'ballot-source-snapshot.json').write_text(json.dumps(data,indent=2,default=str));print({k:len(v) for k,v in data.items()})
