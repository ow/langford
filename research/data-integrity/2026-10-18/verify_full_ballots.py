"""Read-only verification of an applied ballot receipt against every stored choice."""
import argparse,json
from pathlib import Path
from collections import Counter
import psycopg2
from psycopg2.extras import RealDictCursor
from pipeline import config
p=argparse.ArgumentParser();p.add_argument('receipt',type=Path);args=p.parse_args();r=json.loads(args.receipt.read_text());ids=[c['motion_id'] for c in r['changes']]
with psycopg2.connect(config.DATABASE_URL,connect_timeout=15) as db:
 with db.cursor(cursor_factory=RealDictCursor) as cur:
  cur.execute('SELECT id,meta FROM motions WHERE id=ANY(%s)',(ids,));motions={m['id']:m for m in cur.fetchall()}
  cur.execute('SELECT id,motion_id,person_id,vote FROM votes WHERE motion_id=ANY(%s)',(ids,));votes=cur.fetchall()
  for change in r['changes']:
   mid=change['motion_id'];expected={(v['person_id'],v['vote']) for v in change['after_meta']['ballot_reconstruction']['votes']};actual={(v['person_id'],v['vote']) for v in votes if v['motion_id']==mid}
   assert actual==expected,(mid,actual,expected)
   assert motions[mid]['meta']==change['after_meta'],mid
   for old in change['before_votes']:assert any(v['id']==old['id'] and v['vote']==old['vote'] for v in votes),('existing_vote_changed',old['id'])
  result={'verified_motions':len(ids),'verified_vote_rows':len(votes),'inserted_vote_rows':sum(len(c['inserted_votes']) for c in r['changes']),'existing_vote_rows_preserved':sum(len(c['before_votes']) for c in r['changes']),'provenance_counts':dict(Counter(v['evidence'] for c in r['changes'] for v in c['after_meta']['ballot_reconstruction']['votes']))}
  args.receipt.with_name(args.receipt.stem+'-verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
