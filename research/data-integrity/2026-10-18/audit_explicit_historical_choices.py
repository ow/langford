"""Read-only census of explicit old individual choices; no silence inference."""
import json,hashlib
from pathlib import Path
from collections import defaultdict,Counter
from datetime import datetime
from pipeline.ingestion import official_ballots as e
from pipeline.ingestion.vote_evidence import normalize_text,named_vote_declarations,named_votes,outcome_family
from pipeline.ingestion.ballot_reconstruction import validate_roster_entries
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
s=json.loads((OUT/'ballot-source-current-snapshot.json').read_text());people=json.loads((OUT/'vote-people-current-snapshot.json').read_text());inv=json.loads((OUT/'full-current-vote-inventory.json').read_text());meetings={m['id']:m for m in s['meetings']};existing={(v['motion_id'],v['person_id']):v for v in inv['votes']};sources={};records=[];holds=[]
for m in s['motions']:
 if not m['result'] or meetings[m['meeting_id']]['meeting_date']>='2021-10-18':continue
 meeting=meetings[m['meeting_id']]
 if m['meeting_id'] not in sources:sources[m['meeting_id']]=e.load_official_minutes(meeting,root=ROOT,people=people,cache_dir='/private/tmp/langford-ballot-source-audit')
 src=sources[m['meeting_id']]
 if src.get('error') or src.get('source_classification')!='Council' or not src.get('local_date'):continue
 date=src['local_date']
 if abs((datetime.fromisoformat(date)-datetime.fromisoformat(meeting['meeting_date'])).days)>1:continue
 blocks=src['index'].get(normalize_text(m['text_content']),[])
 if len(blocks)!=1 or outcome_family(blocks[0]['result'])!=outcome_family(m['result']):continue
 block=blocks[0];declarations=named_vote_declarations(block)
 if not declarations:continue
 ids={r['person_id'] for r in s['memberships'] if r['classification']=='Council' and r['start_date'] and r['start_date']<=date and(not r['end_date'] or r['end_date']>=date)};eligible=[p for p in people if p['id'] in ids];bad=[];declared=defaultdict(set)
 for d in declarations:
  resolved,unknown=validate_roster_entries(d['names'],eligible)
  if d.get('unparsed') or unknown or not resolved or (d.get('declared_count') is not None and d['declared_count']!=len(resolved)):bad.append(d)
  for p in resolved:declared[p['id']].add(d['vote'])
 if any(len(v)>1 for v in declared.values()):bad.append({'reason':'conflicting_choices'})
 if bad:holds.append({'motion_id':m['id'],'reason':'unresolved_declaration','declarations':bad});continue
 choices=named_votes(block,[p['name'] for p in eligible]);nameids={p['name']:p['id'] for p in eligible}
 for v in choices:
  pid=nameids[v['person_name']];prior=existing.get((m['id'],pid))
  row={'motion_id':m['id'],'meeting_id':m['meeting_id'],'person_id':pid,'person_name':v['person_name'],'vote':v['vote'],'source_quote':v['source_quote'],'source_file':src['source_file'],'source_sha256':src['source_sha256'],'source_date':date,'source_motion_text':block['motion_text'],'source_block':block['source_block'],'existing':prior,'status':'already_recorded' if prior and prior['vote']==v['vote'] else 'existing_conflict' if prior else 'new_explicit_choice_proposal'}
  records.append(row)
out={'mode':'read_only_old_explicit_named_choices_no_silence_inference','summary':dict(Counter(r['status'] for r in records)),'choices':records,'unresolved':holds}
(OUT/'historical-explicit-choice-census.json').write_text(json.dumps(out,indent=2));print(json.dumps({'choices':len(records),'summary':out['summary'],'held_declarations':len(holds)}))
