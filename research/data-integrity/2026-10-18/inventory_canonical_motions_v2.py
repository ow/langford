"""Read-only canonical native inventory using the regular production parser.

Keeps original frozen 113-mapping inputs immutable. Outcome leads remain leads,
not fabricated motions. No Supabase, paid models, inserts or retirements.
"""
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import hashlib, json, re, subprocess

from pipeline.ingestion.official_ballots import html_minutes_text
from pipeline.ingestion.vote_evidence import minutes_motion_blocks
from pipeline.ingestion.canonical_motions import source_identity

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).parent
baseline=json.loads((OUT/'canonical-official-motion-inventory.json').read_text())
parser_file=ROOT/'apps/pipeline/pipeline/ingestion/vote_evidence.py'
parser_sha=hashlib.sha256(parser_file.read_bytes()).hexdigest()


def inspect(row):
    if row.get('error'):
        return {'meeting_id':row['meeting_id'],'error':row['error']},[]
    path=ROOT/row['source_file']
    raw_sha=hashlib.sha256(path.read_bytes()).hexdigest()
    if raw_sha!=row['source_sha256']:
        return {'meeting_id':row['meeting_id'],'error':'source_changed_since_frozen_inventory'},[]
    if path.suffix.lower()=='.pdf':
        text=subprocess.check_output(['pdftotext','-layout',str(path),'-'],text=True)
    else:
        text=html_minutes_text(path)
    clean=re.sub(r'(?im)^\s*Minutes of[^\n]*\n','\n',text)
    clean=re.sub(r'(?m)^\s*\d+\s*$','',clean).replace('\f','\n')
    blocks=list(minutes_motion_blocks(clean))
    bound=[];canonical=[]
    for block in blocks:
        start=clean.find(block['source_block'],block['source_offset'])
        outcome_start=clean.find(block['outcome_quote'],start,start+len(block['source_block'])) if start>=0 else -1
        if outcome_start>=0:bound.append((outcome_start,outcome_start+len(block['outcome_quote'])))
        canonical.append({**source_identity(row['meeting_id'],row,block),'meeting_id':row['meeting_id'],
            'source_result':block['result'],'before_outcome_votes':block['before_outcome_votes'],'after_outcome':block['after_outcome']})
    markers=list(re.finditer(r'(?im)^[ \t]*(?:Motion[ \t]+)?(?:NOT CARRIED|CARRIED(?:[ \t]+UNANIMOUSLY)?|DEFEATED|WITHDRAWN|TABLED)\b[^\n]*',clean))
    leads=[{'source_offset':m.start(),'source_quote':m[0].strip()} for m in markers if not any(m.start()<stop and start<m.end() for start,stop in bound)]
    return {'meeting_id':row['meeting_id'],'source_file':row['source_file'],'source_sha256':raw_sha,
        'native_text_sha256':hashlib.sha256(clean.encode()).hexdigest(),'formal_decisions':len(blocks),
        'outcome_markers':len(markers),'unbound_outcome_leads':leads},canonical

with ThreadPoolExecutor(max_workers=4) as pool:
    inspected=list(pool.map(inspect,baseline['sources']))
if hashlib.sha256(parser_file.read_bytes()).hexdigest()!=parser_sha:
    raise RuntimeError('Production parser changed during inventory; refusing mixed-version artifact')
sources=[row for row,_ in inspected];motions=[motion for _,records in inspected for motion in records]
report={'mode':'read_only_production_parser_canonical_inventory_v2','at':datetime.now(timezone.utc).isoformat(),
    'input_sha256':hashlib.sha256((OUT/'canonical-official-motion-inventory.json').read_bytes()).hexdigest(),
    'parser_sha256':parser_sha,'summary':{'source_entries':len(sources),'formal_decisions':len(motions),
    'source_kinds':dict(Counter(m['formal_source_kind'] for m in motions)),
    'outcome_markers':sum(s.get('outcome_markers',0) for s in sources),
    'unbound_outcome_leads':sum(len(s.get('unbound_outcome_leads',[])) for s in sources),
    'source_errors':dict(Counter(s['error'] for s in sources if s.get('error'))),
    'universal_completeness_claim':False,'live_writes':0,'paid_model_calls':0},'sources':sources,'canonical_motions':motions}
(OUT/'canonical-official-motion-inventory-v2.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report['summary'],indent=2))
