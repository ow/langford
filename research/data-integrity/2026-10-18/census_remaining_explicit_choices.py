"""Read-only source-bound explicit choices still absent; no inferred ballots or writes."""
import json,hashlib,sys
from pathlib import Path
from collections import defaultdict,Counter
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent;sys.path.insert(0,str(ROOT/'apps/pipeline'))
from pipeline.ingestion.official_ballots import load_official_minutes
from pipeline.ingestion.vote_evidence import normalize_text,named_votes,outcome_family,named_vote_declarations
from pipeline.ingestion.ballot_reconstruction import validate_roster_entries
snap=json.loads((OUT/'ballot-source-current-snapshot.json').read_text());people=json.loads((OUT/'vote-people-current-snapshot.json').read_text());inventory=json.loads((OUT/'full-current-vote-inventory.json').read_text());meetings={m['id']:m for m in snap['meetings']};person_ids={p['name']:p['id'] for p in people};existing=defaultdict(dict)
for v in inventory['votes']:existing[v['motion_id']][v['person_id']]=v
sources={};records=[];holds=[]
for motion in snap['motions']:
 if not motion['result'] or motion['meta'].get('individual_vote_coverage')=='reconstructed_complete':continue
 meeting=meetings[motion['meeting_id']]
 if meeting['id'] not in sources:sources[meeting['id']]=load_official_minutes(meeting,root=ROOT,people=people,cache_dir='/private/tmp/langford-ballot-source-audit')
 source=sources[meeting['id']]
 if source.get('error'):continue
 blocks=source['index'].get(normalize_text(motion['text_content']),[])
 if len(blocks)!=1:continue
 block=blocks[0]
 if outcome_family(block['result'])!=outcome_family(motion['result']):continue
 declarations=named_vote_declarations(block)
 if not declarations:continue
 failed=[]
 for declaration in declarations:
  resolved,unknown=validate_roster_entries(declaration['names'],people)
  if declaration.get('unparsed') or unknown or not resolved:failed.append('unparsed_or_unknown_source_names')
  if declaration.get('declared_count') is not None and declaration['declared_count']!=len(resolved):failed.append('count_does_not_match_names')
 if failed:holds.append({'motion_id':motion['id'],'reasons':sorted(set(failed))});continue
 votes=named_votes(block,[p['name'] for p in people]);byid=defaultdict(set)
 for v in votes:byid[person_ids[v['person_name']]].add(v['vote'])
 if any(len(x)!=1 for x in byid.values()):holds.append({'motion_id':motion['id'],'reasons':['conflicting_choices']});continue
 for v in votes:
  pid=person_ids[v['person_name']];old=existing[motion['id']].get(pid)
  if old and old['vote']==v['vote']:continue
  records.append({'motion_id':motion['id'],'meeting_id':meeting['id'],'person_id':pid,'person_name':v['person_name'],'vote':v['vote'],'source_quote':v['source_quote'],'source_file':source['source_file'],'source_sha256':source['source_sha256'],'source_url':source['source_url'],'source_motion_text':block['motion_text'],'source_result':block['result'],'source_date':source.get('local_date'),'existing_conflict':old})
out={'mode':'read_only_named_choices_only_requires_independent_review_before_any_apply','summary':{'new_explicit_choices':sum(not r['existing_conflict'] for r in records),'existing_choice_conflicts':sum(bool(r['existing_conflict']) for r in records),'motions':len({r['motion_id'] for r in records}),'source_files':len({r['source_sha256'] for r in records}),'declaration_holds':len(holds),'database_writes':0},'records':records,'holds':holds};f=OUT/'remaining-explicit-choice-census.json';f.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out['summary'],indent=2));print(hashlib.sha256(f.read_bytes()).hexdigest())
