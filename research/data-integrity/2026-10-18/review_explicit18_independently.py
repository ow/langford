"""Independent native PDF witness review, without production ballot/name parsers."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[3]
out = Path(__file__).parent
plan_path = out/'explicit18-partial-choice-plan.json'
plan_bytes = plan_path.read_bytes()
plan = json.loads(plan_bytes)
people = {20:'Mark Morley',21:'Colby Harder',22:'Mary Wagner',23:'Kimberley Guiry',34:'Keith Yacucha',35:'Lillian Szpak'}
norm = lambda text: re.sub(r'[^a-z0-9]+',' ',text.casefold()).strip()
sources = {}
records = []
for row in plan['records']:
    path = root/row['source_file']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == row['source_sha256']
    if str(path) not in sources:
        sources[str(path)] = subprocess.check_output(['pdftotext','-layout',str(path),'-'], text=True)
    native = norm(sources[str(path)])
    witness = norm(row['source_block'])
    assert native.count(witness) == 1, 'entire native formal witness must match uniquely'
    assert norm(row['source_motion_text']) == norm(row['current_motion']['text_content'])
    assert row['source_result'] == row['current_motion']['result']
    assert not row['current_votes']
    assert row['current_motion']['id'] == row['motion_id']
    assert row['current_motion']['meeting_id'] == row['meeting_id']
    choices = []
    for choice in row['named_choices']:
        assert people[choice['person_id']] == choice['person_name']
        assert choice['vote'] == 'No' and choice['evidence'] == 'explicit_named'
        quote = norm(choice['source_quote'])
        assert witness.count(quote) == 1
        surname = choice['person_name'].split()[-1].casefold()
        assert re.search(r'\b'+re.escape(surname)+r'\b',quote)
        assert re.search(r'\b(?:opposed|against)\b',quote)
        choices.append({'person_id':choice['person_id'],'vote':'No','source_quote':choice['source_quote']})
    records.append({'motion_id':row['motion_id'],'source_sha256':row['source_sha256'],
                    'unique_entire_native_block':True,'exact_current_body_and_outcome':True,
                    'choices':choices})
assert len(records) == 9 and sum(len(r['choices']) for r in records) == 18
result = {'mode':'independent_original_PDF_explicit_choices_only',
          'plan_sha256':hashlib.sha256(plan_bytes).hexdigest(),
          'review_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'summary':{'motions':9,'source_files':len(sources),'explicit_No_choices':18,
                     'full_ballot_claims':0,'database_writes':0},
          'scope':'Native named No only. No attendance inference, unrecorded Yes, complete-ballot or threshold inference.',
          'records':records}
(out/'explicit18-independent-native-review.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result['summary']))
