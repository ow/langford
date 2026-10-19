"""Independent read-only HTML pilot checks, without the ballot presence parser.

Requires a unique actual DOM motion, original bytes, exact roster initials and
surname identities, a source carried outcome, and explicit No quotes scoped to
that DOM motion. The selected pilot has all listed attendees on every candidate
ballot; temporary departure/return narratives are separately reported for review.
"""
from collections import Counter
import hashlib,json,re
from pathlib import Path
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
plan_bytes=(OUT/'full-ballot-audit.json').read_bytes()
plan=json.loads(plan_bytes)
people=json.loads((OUT/'vote-people-snapshot.json').read_text())
selected=[r for r in plan['motions'] if r['status']=='reconstructable_candidate' and r.get('source_format')=='official_html_structural']
assert {r['meeting_id'] for r in selected}=={389,390,391,392,394}
assert len(selected)==57

def norm(value):return re.sub(r'[^a-z0-9]+',' ',value.casefold()).strip()

sources={};records=[]
for row in selected:
    path=ROOT/row['source_file']
    if path not in sources:
        binary=path.read_bytes();soup=BeautifulSoup(binary,'html.parser')
        table=soup.select_one('.AgendaHeaderAttendanceTable');present=[]
        for block in table.find_all('div',recursive=False):
            label=block.select_one('.Label');value=block.select_one('.Value')
            if label and value and norm(label.get_text(' ',strip=True))=='present':
                for item in value.select('li'):
                    text=item.get_text(' ',strip=True)
                    assert not re.search(r'\b(arrived|joined|left|returned|absent)\b',text,re.I), 'Header presence annotation requires separate review'
                    name=re.search(r'\b([A-Z])\.\s*([A-Za-z]+)\b',text)
                    assert name, f'Unparsed source roster entry{text}'
                    matches=[p for p in people if p['name'][0].casefold()==name[1].casefold() and p['name'].split()[-1].casefold()==name[2].casefold()]
                    assert len(matches)==1,f'Unresolved exact roster identity{text}'
                    present.append(matches[0]['id'])
        assert len(present)==len(set(present)) and 4<=len(present)<=7
        narratives=[]
        for node in soup.select('.AgendaItemMinutes'):
            text=node.get_text(' ',strip=True)
            if re.search(r'\b(left|returned|arrived|joined|recused|conflict of interest)\b',text,re.I):
                narratives.append({'text':text,'nested_motion_nodes':len(node.select('.AgendaItemMotion'))})
        sources[path]={'soup':soup,'sha256':hashlib.sha256(binary).hexdigest(),'roster':present,'presence_narratives':narratives}
    source=sources[path]
    assert source['sha256']==row['source_sha256']
    matches=[node for node in source['soup'].select('.AgendaItemMotion') if node.select_one('.MotionText') and norm(node.select_one('.MotionText').get_text(' ',strip=True))==norm(row['source_motion_text'])]
    assert len(matches)==1,f'DOM motion ambiguity{row["motion_id"]}'
    node=matches[0];result=node.select_one('.MotionResult').get_text(' ',strip=True)
    assert re.search(r'\bCARRIED\b',result,re.I) and not re.search(r'\bNOT CARRIED\b',result,re.I)
    assert {v['person_id'] for v in row['votes']}==set(source['roster'])
    assert len(row['votes'])==len(source['roster'])
    post=node.select_one('.PostMotionText');post=post.get_text(' ',strip=True) if post else ''
    for vote in row['votes']:
        if vote['evidence']=='explicit_named':assert norm(vote['source_quote']) in norm(post)
        else:assert vote['evidence']=='inferred_official_dissent_recording_rule' and vote['vote']=='Yes'
    assert row['yes']==sum(v['vote']=='Yes' for v in row['votes'])
    assert row['no']==sum(v['vote']=='No' for v in row['votes'])
    assert row['yes']>row['no']
    records.append({'motion_id':row['motion_id'],'meeting_id':row['meeting_id'],'source_sha256':source['sha256'],
        'source_url':row['source_url'],'source_result':result,'post_motion_text':post,'source_roster_person_ids':source['roster'],
        'yes':row['yes'],'no':row['no'],'explicit_vote_count':sum(v['evidence']=='explicit_named' for v in row['votes'])})
proof={'mode':'independent_read_only_review','plan_sha256':hashlib.sha256(plan_bytes).hexdigest(),
    'summary':{'motions':len(records),'source_meetings':len(sources),'vote_rows':sum(r['yes']+r['no'] for r in records),'explicit_no_rows':sum(r['no'] for r in records)},
    'source_presence_narratives':{str(p.relative_to(ROOT)):s['presence_narratives'] for p,s in sources.items()},'records':records}
(OUT/'html-ballot-pilot-independent-review.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof['summary']))
