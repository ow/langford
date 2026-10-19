"""Original pixels may repair hidden roster text, never a guessed identity."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import shutil

import pytest

from pipeline.ingestion.meeting_ballots import evaluate_ballot
from pipeline.ingestion.official_ballots import load_official_minutes
from .ballot_fixture import POLICY

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = 'apps/pipeline/tests/fixtures/roster-ocr'
PEOPLE = [{'id':1,'name':'Scott Goodmanson'},{'id':20,'name':'Mark Morley'},
          {'id':21,'name':'Colby Harder'},{'id':22,'name':'Mary Wagner'},
          {'id':23,'name':'Kimberley Guiry'},{'id':34,'name':'Keith Yacucha'},
          {'id':35,'name':'Lillian Szpak'}]


@pytest.mark.skipif(not shutil.which('pdftotext'), reason='Native original PDF contract requires Poppler')
@pytest.mark.parametrize('case', ['verified', 'changed_pdf', 'unrecognised_member', 'changed_name', 'ambiguous_name', 'wrong_organization', 'ended_office', 'receipt_tamper', 'low_confidence'])
def test_original_roster_view_requires_bound_pixels_identity_and_dated_office(tmp_path, monkeypatch, case):
    import pipeline.ingestion.roster_ocr as owner
    meeting = {'id':310,'archive_path':FIXTURE,'meeting_date':'2023-05-08',
               'classification':'Council','municipality_slug':'langford','organization_id':1}
    people = deepcopy(PEOPLE)
    memberships = [{'person_id':p['id'],'name':p['name'],'organization_id':1,
                    'classification':'Council','role':'Mayor' if p['id']==1 else 'Councillor',
                    'start_date':'2022-11-07','end_date':None} for p in people]
    source = load_official_minutes(meeting,root=ROOT,people=people,cache_dir=tmp_path/'cache')
    assert 'S. Goodnnanson' in source['roster_quote']
    if case == 'changed_pdf':
        copy = tmp_path/'modified.pdf'
        copy.write_bytes((ROOT/source['source_file']).read_bytes()+b'\n%changed\n')
        source['source_file'] = str(copy)
    if case == 'unrecognised_member':
        source['roster_quote'] += '\nCouncillor Q. Unrecognised'
    if case == 'changed_name':
        people[0]['name'] = 'Stephen Goodmanson'
    if case == 'ambiguous_name':
        people.append({'id':999,'name':'Sam Goodmanson'})
    if case == 'wrong_organization':
        memberships[0]['organization_id'] = 99
    if case == 'ended_office':
        memberships[0]['end_date'] = '2023-05-07'
    if case in {'receipt_tamper','low_confidence'}:
        store = tmp_path/'proofs';shutil.copytree(owner.STORE,store)
        target = store/(source['source_sha256']+'.json')
        receipt = json.loads(target.read_bytes())
        receipt['target_ocr_line']['candidates'][0]['confidence'] = .5
        target.write_text(json.dumps(receipt))
        if case == 'low_confidence':
            index = json.loads((store/'index.json').read_bytes())
            index[source['source_sha256']] = hashlib.sha256(target.read_bytes()).hexdigest()
            (store/'index.json').write_text(json.dumps(index))
        monkeypatch.setattr(owner,'STORE',store)
    original = deepcopy(source)
    context = {'status':'available','meeting':meeting,'source':source,
               'people':people,'memberships':memberships,'policy':POLICY}
    result = evaluate_ballot({'id':3092,'meeting_id':310,'result':'CARRIED',
                             'text_content':'THAT Council approve the agenda as presented.'},context)
    assert source == original  # No PDF text, source offsets, or raw roster mutation.
    if case != 'verified':
        assert result['status'] == 'held_original_roster_ocr_proof_invalid'
        assert not result.get('votes')
        return
    assert result['status'] == 'reconstructable_candidate'
    assert {v['person_id']:v['vote'] for v in result['votes']} == {1:'Yes',20:'Yes',21:'Yes',22:'Yes',23:'Yes',34:'Yes',35:'Yes'}
    proof = result['proof']['roster_source_validation']
    assert 'S. Goodnnanson' in proof['raw_roster_quote']
    assert 'S. Goodmanson' in proof['corrected_roster_view']
    assert proof['dated_office']['organization_id'] == 1
    assert proof['source_sha256'] == source['source_sha256']
    assert proof['identity_ocr_line']['candidates'][0]['confidence'] == 1
