"""Dry-run recovery of uniquely named opposition, using exact motion-text matches.

No attendance inference and no writes. Ambiguous identities or unmatched wording
remain held. Reads snapshots created by audit_votes.py and vote-people-snapshot.json.
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
from pipeline.ingestion.vote_evidence import minutes_motion_blocks,normalize_text

ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
motions=json.loads((OUT/'motions-audit.json').read_text())
people=json.loads((OUT/'vote-people-snapshot.json').read_text())
surnames=defaultdict(list)
for person in people:
    parts=normalize_text(person['name']).split()
    if len(parts)>=2 and len(parts[-1])>=3:surnames[parts[-1]].append(person)
blocks=defaultdict(list)
for file in (ROOT/'archive/langford').glob('**/minutes.md'):
    for block in minutes_motion_blocks(file.read_text()):
        after='\n'.join(block['after_outcome'].splitlines()[:9])
        after=re.split(r'(?im)^\s*\*{0,2}(?:Motion\s+)?(?:CARRIED|DEFEATED|WITHDRAWN)\b',after)[0]
        opposed=re.search(r'(?im)^\s*(OPPOSED\s*:\s*[^\n]*|[^\n]{0,180}\bopposed\b[^\n]*)',after)
        if not opposed:continue
        quote=opposed.group(1)
        if not re.match(r'OPPOSED\s*:',quote,re.I):
            quote=quote[:re.search(r'\bopposed\b',quote,re.I).end()]
        quote=re.split(r'\bOn the (?:Main )?Motion\b',quote,flags=re.I)[0].strip()
        quote=re.split(r'\s+\d+\.(?:\d+)?\s',quote)[0]
        if not re.search(r'\b(Mayor|Councillor|Councillors)\b',quote,re.I):continue
        names=[];ambiguities=[]
        for surname,matches in surnames.items():
            if re.search(r'\b'+re.escape(surname)+r'\b',normalize_text(quote)):
                if len(matches)==1:names+=matches
                else:ambiguities.append(surname)
        if not names:continue
        blocks[(file.parent.name[:10],normalize_text(block['motion_text']))].append((file,block,quote,names,ambiguities))
proposals=[];held=[]
for motion in motions:
    candidates=blocks.get((motion['meetings']['meeting_date'][:10],normalize_text(motion['text_content'])),[])
    if not candidates:continue
    # Deduplicate repeated export versions only when outcome + named identities agree.
    identities={(b['result'],tuple(sorted(p['id'] for p in ps))) for f,b,q,ps,a in candidates}
    if len(identities)!=1 or any(a for f,b,q,ps,a in candidates):
        held.append({'motion_id':motion['id'],'reason':'ambiguous source or surname'});continue
    file,block,quote,names,_=candidates[0]
    if motion['result']!=block['result']:
        held.append({'motion_id':motion['id'],'reason':'stored outcome differs from matched source'});continue
    existing={v['person_id']:v['vote'] for v in motion['votes']}
    for person in names:
        if person['id'] in existing:
            if existing[person['id']]!='No':held.append({'motion_id':motion['id'],'person_id':person['id'],'reason':'existing conflicting vote'})
            continue
        proposals.append({'motion_id':motion['id'],'meeting_id':motion['meeting_id'],'person_id':person['id'],'person_name':person['name'],'previous_vote':None,'proposed_vote':'No','source_quote':quote,'source_file':str(file.relative_to(ROOT)),'source_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'matched_motion_text':block['motion_text']})
plan={'summary':{'named_opposition_candidates':len(proposals),'motions':len({p['motion_id'] for p in proposals}),'held':len(held)},'safety':'Dry-run. Exact normalized motion match and unique person surname only; recheck original source PDF before apply. No Yes inference. No existing rows changed.','candidates':proposals,'held':held}
(OUT/'named-vote-repair-plan.json').write_text(json.dumps(plan,indent=2));print(plan['summary'])
