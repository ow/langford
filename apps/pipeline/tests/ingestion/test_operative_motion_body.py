"""Actual original minutes own the raw/operative separation contract."""
import hashlib
import json
from pathlib import Path
import subprocess

import fitz
import pytest

from pipeline.ingestion.operative_motion_body import derive_operative_motion_body
from pipeline.ingestion.vote_evidence import minutes_motion_blocks

FIXTURES = Path(__file__).parents[1] / 'fixtures/operative-motion-bodies'
PROVENANCE = {r['motion_id']: r for r in json.loads((FIXTURES/'provenance.json').read_text())['sources']}


def original_block(motion_id):
    record = PROVENANCE[motion_id]
    source = FIXTURES/record['fixture']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == record['original_sha256']
    text = subprocess.run(['pdftotext', '-layout', str(source), '-'], capture_output=True, check=True).stdout.decode()
    # Ordinary loader removes the minutes-title line, not the source date/page-count.
    import re
    text = re.sub(r'(?im)^\s*Minutes of[^\n]*\n', '\n', text)
    text = re.sub(r'(?m)^\s*\d+\s*$', '', text).replace('\f', '\n')
    blocks = list(minutes_motion_blocks(text))
    actors = record['raw_body_locator']
    locator = {669: 'solicitor-', 2616: '10:03'}.get(motion_id, '')
    candidates = [b for b in blocks if locator in b['motion_text'] and all(name in b['source_block'].splitlines()[i] for i, name in enumerate(actors))]
    # 2616 shares GUIRY with another motion but not its unique MORLEY seconder.
    assert len(candidates) == 1
    return source, record, candidates[0]


@pytest.mark.parametrize('motion_id', [669, 2689, 228, 2616, 192])
def test_original_minutes_separate_operative_words_without_rewriting_raw_witness(motion_id):
    source, record, block = original_block(motion_id)
    before = json.loads(json.dumps(block))
    view = derive_operative_motion_body(block, source_file=source,
        source_sha256=record['original_sha256'], source_date=record['source_date'])
    assert block == before
    assert view['raw_block'] == before
    if motion_id in (669, 2689):
        assert 'Page 2 of 2' not in view['operative_body']
        assert 'Community Charter' in view['operative_body']
        assert 'b)' in view['operative_body']
        assert len(view['excluded_spans']) == 2
        assert all(s['kind'] == 'page_decoration' and s['geometry']['page'] == 2 for s in view['excluded_spans'])
    elif motion_id == 228:
        assert view['operative_body'] == 'THAT Council adjourn the meeting.'
        assert view['excluded_spans'][0]['kind'] == 'execution_event'
        assert '4:08 pm' in view['excluded_spans'][0]['quote']
    elif motion_id == 2616:
        assert view['motion_kind'] == 'amendment'
        assert view['match_aliases'] == ['AMENDMENT: ' + view['operative_body']]
        assert view['context'][0]['quote'] == 'Amendment:'
    else:
        assert view['operative_body'] is None
        assert view['status'] == 'documentary_event_only_held'
    for span in view['excluded_spans']:
        assert before['source_block'][span['start']:span['end']] == span['quote']


def test_body_dates_and_conditional_or_mixed_adjournment_are_preserved(tmp_path):
    # Transport is a real native PDF; no fixture supplies a geometry/admission verdict.
    path = tmp_path/'Minutes.pdf'
    for body in ['THAT Council meet on June 24, 2021.',
                 'THAT Council adjourn the meeting if the report is completed.\nMayor Goodmanson adjourned the meeting at 4:08 pm.',
                 'THAT Council adjourn the meeting.\nTHAT staff report back.\nMayor Goodmanson adjourned the meeting at 4:08 pm.']:
        doc = fitz.open(); doc.new_page().insert_text((70, 160), 'MOVED BY: HARDER\nSECONDED: WAGNER\n'+body+'\nCARRIED.', fontsize=8); doc.save(path); doc.close()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        block={'motion_text': body, 'source_block': 'MOVED BY: HARDER\nSECONDED: WAGNER\n'+body+'\nCARRIED.', 'source_offset': 11, 'source_order': 2}
        view=derive_operative_motion_body(block, source_file=path, source_sha256=digest, source_date='2021-06-24')
        assert view['operative_body'] == body
        assert view['excluded_spans'] == []


def test_recurring_source_plan_preserves_correct_adjournment_id_and_readable_words(tmp_path):
    """Actual raw extractor's execution tail must not orphan a correct old row."""
    from shutil import copyfile
    from pipeline.ingestion.official_ballots import load_official_minutes
    from pipeline.ingestion.canonical_motions import canonical_motion_plan
    path,record,block=original_block(228)
    folder=tmp_path/'archive/langford/meeting/Minutes';folder.mkdir(parents=True)
    copyfile(path,folder/'Minutes - SIGNED.pdf')
    people=[{'id':i+1,'name':n}for i,n in enumerate(['Scott Goodmanson','Kimberley Guiry','Colby Harder','Mark Morley','Mary Wagner','Keith Yacucha','Lillian Szpak'])]
    meeting={'id':77,'meeting_date':record['source_date'],'classification':'Council','title':'Special Council',
             'archive_path':'archive/langford/meeting','minutes_url':'https://pub-langford.escribemeetings.com/original'}
    source=load_official_minutes(meeting,root=tmp_path,people=people,cache_dir=tmp_path/'cache')
    assert not source.get('error'),source
    old={'id':123,'meeting_id':77,'text_content':'THAT Council adjourn the meeting.','result':'CARRIED','meta':{}}
    items,report=canonical_motion_plan([],{'status':'available','meeting':meeting,'source':source},[old])
    motions=[m for item in items for m in item['motions']]
    retained=[m for m in motions if (m.get('_existing_motion')or{}).get('id')==123]
    assert len(retained)==1,report
    assert retained[0]['motion_text']==old['text_content']
    assert retained[0]['_canonical_source_motion']['raw_motion_text']==block['motion_text']
    assert retained[0]['_source_motion']['source_block']==block['source_block']


def test_raw_and_derived_body_union_cannot_choose_a_different_occurrence(tmp_path):
    from pipeline.ingestion.official_ballots import load_official_minutes
    from pipeline.ingestion.canonical_motions import canonical_motion_plan
    folder=tmp_path/'archive/langford/meeting/Minutes';folder.mkdir(parents=True)
    pdf=folder/'Minutes.pdf'
    document=fitz.open();page=document.new_page()
    page.insert_text((70,70),'City of Langford\nCouncil Minutes\nJanuary 29, 2024\nPRESENT:\nCouncillor C. Harder\nCouncillor M. Wagner\nATTENDING:\n1. ADJOURNMENT\nMOVED BY: HARDER\nSECONDED: WAGNER\nTHAT Council adjourn the meeting.\nThe Mayor adjourned the meeting at 4:08 pm.\nCARRIED.\n2. ADJOURNMENT\nMOVED BY: WAGNER\nSECONDED: HARDER\nTHAT Council adjourn the meeting.\nCARRIED.',fontsize=8)
    document.save(pdf);document.close()
    meeting={'id':77,'meeting_date':'2024-01-29','classification':'Council','title':'Council','archive_path':'archive/langford/meeting'}
    source=load_official_minutes(meeting,root=tmp_path,people=[{'id':1,'name':'Colby Harder'},{'id':2,'name':'Mary Wagner'}],cache_dir=tmp_path/'cache')
    assert len(source['blocks'])==2
    row={'id':123,'meeting_id':77,'text_content':'THAT Council adjourn the meeting.','result':'CARRIED','meta':{}}
    items,report=canonical_motion_plan([],{'status':'available','meeting':meeting,'source':source},[row])
    assert not [m for item in items for m in item['motions']]
    assert report['unmapped_legacy_ids']==[123]
