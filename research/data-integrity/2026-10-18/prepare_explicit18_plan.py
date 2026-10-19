"""Freeze public-source named-choice proposal/current rows only; no DB writes."""
import json,hashlib
from pathlib import Path
from collections import defaultdict
import psycopg2
from psycopg2.extras import RealDictCursor
from pipeline import config
from pipeline.ingestion.official_ballots import load_official_minutes
from pipeline.ingestion.vote_evidence import normalize_text
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
census=json.loads((OUT/'remaining-explicit-choice-census.json').read_text());snapshot=json.loads((OUT/'ballot-source-current-snapshot.json').read_text());people=json.loads((OUT/'vote-people-current-snapshot.json').read_text());meetings={m['id']:m for m in snapshot['meetings']};groups=defaultdict(list)
for r in census['records']:
 assert not r['existing_conflict'];groups[r['motion_id']].append(r)
ids=sorted(groups);assert len(ids)==9 and 2473 not in ids
with psycopg2.connect(config.DATABASE_URL,connect_timeout=15)as db:
 db.set_session(readonly=True,isolation_level='REPEATABLE READ')
 with db.cursor(cursor_factory=RealDictCursor)as c:
  c.execute('SELECT id,meeting_id,agenda_item_id,text_content,result,meta,updated_at,meta IS NULL AS meta_is_sql_null FROM motions WHERE id=ANY(%s) ORDER BY id',(ids,));motions=json.loads(json.dumps(c.fetchall(),default=str))
  c.execute('SELECT id,motion_id,person_id,vote,recusal_reason,created_at,updated_at FROM votes WHERE motion_id=ANY(%s) ORDER BY id',(ids,));votes=json.loads(json.dumps(c.fetchall(),default=str))
sources={};records=[]
for motion in motions:
 rows=groups[motion['id']];meeting=meetings[motion['meeting_id']]
 if meeting['id'] not in sources:sources[meeting['id']]=load_official_minutes(meeting,root=ROOT,people=people,cache_dir='/private/tmp/langford-ballot-source-audit')
 source=sources[meeting['id']];blocks=source['index'].get(normalize_text(motion['text_content']),[]);assert len(blocks)==1;block=blocks[0]
 records.append({'motion_id':motion['id'],'meeting_id':motion['meeting_id'],'source_file':source['source_file'],'source_sha256':source['source_sha256'],'source_url':source['source_url'],'source_date':source.get('local_date'),'source_motion_text':block['motion_text'],'source_result':block['result'],'source_block':block['source_block'],'named_choices':[{'person_id':r['person_id'],'person_name':r['person_name'],'vote':r['vote'],'source_quote':r['source_quote'],'evidence':'explicit_named'}for r in rows],'before_meta_is_sql_null':motion.pop('meta_is_sql_null'),'current_motion':motion,'current_votes':[v for v in votes if v['motion_id']==motion['id']]})
assert sum(len(r['named_choices']) for r in records)==18
out={'mode':'frozen_explicit_named_partial_vote_proposal_requires_guard_rebind_and_independent_review','summary':{'motions':9,'new_explicit_choices':18,'existing_votes_preserved':len(votes),'full_ballot_claims':0,'database_writes':0},'records':records,'code_sha256s_pending_source_key_checkpoint':True};f=OUT/'explicit18-partial-choice-plan.json';f.write_text(json.dumps(out,indent=2)+'\n');print(out['summary']);print(hashlib.sha256(f.read_bytes()).hexdigest())
