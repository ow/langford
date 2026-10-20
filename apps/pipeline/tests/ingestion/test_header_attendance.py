"""Original-page attendance contract at ordinary ballot evaluation boundary."""
from copy import deepcopy
from pathlib import Path
import shutil
import pytest
from pipeline.ingestion.official_ballots import load_official_minutes
from pipeline.ingestion.meeting_ballots import evaluate_ballot
from .ballot_fixture import POLICY

ROOT=Path(__file__).resolve().parents[4]
PEOPLE=[{'id':1,'name':'Scott Goodmanson'},{'id':20,'name':'Mark Morley'},{'id':21,'name':'Colby Harder'},{'id':22,'name':'Mary Wagner'},{'id':23,'name':'Kimberley Guiry'},{'id':34,'name':'Keith Yacucha'},{'id':35,'name':'Lillian Szpak'}]

@pytest.mark.skipif(not shutil.which('pdftotext'),reason='Original PDF contract requires Poppler')
@pytest.mark.parametrize('case',['before_arrival','straddling','retained_exit','resumed_session','missing_year','missing_meridiem','future_close','conditional_close','reversed_clock','conditional_tail','future_tail','dated_tail','extra_clock','scheduled_tail','glued_resume','narrative_reconvene','date_only_resume','subject_tail','following_tail','partial_date_tail','partial_date_session'])
def test_original_header_annotations_preserve_clock_and_session_uncertainty(tmp_path,case):
    mid=187 if case in ('before_arrival','missing_meridiem','future_close','conditional_close','reversed_clock','conditional_tail','future_tail','dated_tail','extra_clock','scheduled_tail','subject_tail','following_tail','partial_date_tail')else 286 if case=='straddling'else 226
    day={187:'2025-03-25',286:'2025-06-10',226:'2025-04-07'}[mid]
    archive=f'apps/pipeline/tests/fixtures/header-attendance/{mid}'
    meeting={'id':mid,'archive_path':archive,'meeting_date':day,'classification':'Council','municipality_slug':'langford','organization_id':1}
    members=[{'person_id':p['id'],'name':p['name'],'organization_id':1,'classification':'Council','role':'Mayor'if p['id']==1 else'Councillor','start_date':'2022-11-07','end_date':None}for p in PEOPLE]
    source=load_official_minutes(meeting,root=ROOT,people=PEOPLE,cache_dir=tmp_path/'cache')
    # Negative native-source variants preserve all other actual PDF content.
    if case in ('missing_year','missing_meridiem'):
        import fitz
        folder=tmp_path/'variant'/'Minutes';folder.mkdir(parents=True)
        original=ROOT/source['source_file'];doc=fitz.open(original);page=doc[0]
        needle='2025'if case=='missing_year'else'am'
        if case=='missing_year':
            words=page.get_text('words');target=next(w for w in words if w[4]=='2025'and w[1]>170 and w[1]<300)
        else:
            words=page.get_text('words');target=next(w for w in words if w[4]=='am'and w[1]>150)
        page.add_redact_annot(fitz.Rect(target[:4]),fill=(1,1,1));page.apply_redactions();doc.save(folder/'Minutes.pdf')
        Path(str(folder/'Minutes.pdf')+'.url').write_text(source['source_url'])
        meeting={**meeting,'archive_path':'variant'}
        source=load_official_minutes(meeting,root=tmp_path,people=PEOPLE,cache_dir=tmp_path/'variant-cache')
    if case in ('future_close','conditional_close','reversed_clock','conditional_tail','future_tail','dated_tail','extra_clock','scheduled_tail','subject_tail','following_tail','partial_date_tail'):
        from pipeline.ingestion.vote_evidence import normalize_text
        block=next(b for b in source['blocks']if '9:42' in b['motion_text'])
        old_body,old_block=block['motion_text'],block['source_block']
        if case=='reversed_clock':
            source['text']=source['text'].replace(old_block,'Council discussed business at 9:41 am, then at 9:39 am.\n'+old_block,1)
        else:
            suffix={'conditional_tail':' if staff confirm availability.','future_tail':' when Council meets tomorrow.','dated_tail':' on March 26, 2025.','extra_clock':' at 10:20 am.','scheduled_tail':' as scheduled next day.','subject_tail':' subject to staff confirmation.','following_tail':' on the following day.','partial_date_tail':' on March 26.'}.get(case)
            new_body=old_body+suffix if suffix else old_body.replace('9:42 am to','9:42 am tomorrow to')if case=='future_close'else old_body.replace('THAT Council close','THAT Council if required close')
            block['motion_text']=new_body
            block['source_block']=old_block.replace(old_body,new_body)
            source['text']=source['text'].replace(old_block,block['source_block'],1)
            source['index']={normalize_text(b['motion_text']):[b]for b in source['blocks']}
    if case in ('glued_resume','narrative_reconvene','date_only_resume'):
        replacement={'glued_resume':'THATCouncil resume','narrative_reconvene':'Council reconvened','date_only_resume':'Council continued the meeting'}[case]
        source['text']=source['text'].replace('THAT Council resume',replacement)
    if case=='partial_date_session':
        import re
        source['text']=source['text'].replace('THAT Council resume','Council continued the meeting')
        source['text']=re.sub(r'April\s+8,\s*2025','April 8',source['text'])
    if case=='retained_exit':
        assert source['header_attendance']['annotations'][0]['dates']==['2025-04-07','2025-04-08']
        assert 'April 8, 2025'in ' '.join(source['header_attendance']['native_roster_quote'].split())
    original=deepcopy(source)
    text={'before_arrival':'THAT Council close the meeting at 9:42 am to the public pursuant to section 90 (1) (k) of the Community Charter to consider:','missing_meridiem':'THAT Council close the meeting at 9:42 am to the public pursuant to section 90 (1) (k) of the Community Charter to consider:','straddling':'THAT Council adjourn the meeting.','retained_exit':'THAT Council give Langford Zoning Bylaw, Amendment No. 733 (2795 and 2799 Scafe Road), Bylaw No. 2194, 2025 first, second and third readings.','resumed_session':'THAT Council adjourn the meeting.','missing_year':'THAT Council adjourn the meeting.','future_close':'','conditional_close':'','reversed_clock':'','conditional_tail':'','future_tail':'','dated_tail':'','extra_clock':'','scheduled_tail':'','subject_tail':'','following_tail':'','partial_date_tail':'','glued_resume':'THAT Council adjourn the meeting.','narrative_reconvene':'THAT Council adjourn the meeting.','date_only_resume':'THAT Council adjourn the meeting.','partial_date_session':'THAT Council adjourn the meeting.'}[case]
    # Use the exact complete native motion body, including any statutory list.
    if mid==187:text=next(b['motion_text']for b in source['blocks']if '9:42' in b['motion_text'])
    result=evaluate_ballot({'id':999,'meeting_id':mid,'text_content':text,'result':'CARRIED'},{'status':'available','meeting':meeting,'source':source,'people':PEOPLE,'memberships':members,'policy':POLICY})
    assert all(source[key]==original[key]for key in ('text','roster_quote','blocks','operative_views'))
    if case in ('before_arrival','retained_exit'):
        assert result['status']=='reconstructable_candidate'
        expected_absent=34 if case=='before_arrival'else 21
        assert {v['person_id']:v['vote']for v in result['votes']}=={p['id']:'Yes'for p in PEOPLE if p['id']!=expected_absent}
        if case=='before_arrival':assert result['proof']['header_attendance_validation']['absent_person_ids']==[34]
        else:assert any(e['person_id']==21 and e['state']=='absent'for e in result['proof']['presence_events'])
    else:
        assert result['status']=={'straddling':'header_arrival_vote_time_unresolved','resumed_session':'resumed_session_presence_unresolved','missing_year':'header_attendance_annotation_invalid','missing_meridiem':'header_attendance_annotation_invalid','future_close':'header_arrival_vote_time_unresolved','conditional_close':'header_arrival_vote_time_unresolved','reversed_clock':'header_arrival_vote_time_unresolved','conditional_tail':'header_arrival_vote_time_unresolved','future_tail':'header_arrival_vote_time_unresolved','dated_tail':'header_arrival_vote_time_unresolved','extra_clock':'header_arrival_vote_time_unresolved','scheduled_tail':'header_arrival_vote_time_unresolved','subject_tail':'header_arrival_vote_time_unresolved','following_tail':'header_arrival_vote_time_unresolved','partial_date_tail':'header_arrival_vote_time_unresolved','glued_resume':'resumed_session_presence_unresolved','narrative_reconvene':'resumed_session_presence_unresolved','date_only_resume':'resumed_session_presence_unresolved','partial_date_session':'resumed_session_presence_unresolved'}[case]
        assert not result.get('votes')

@pytest.mark.skipif(not shutil.which('pdftotext'), reason='Original PDF contract requires Poppler')
@pytest.mark.parametrize('case', ['original', 'reversal', 'other_day', 'transition', 'missing_mode', 'future_reference', 'wrong_wrapper', 'missing_heading', 'missing_geometry', 'conditional_reference', 'current_reference', 'missing_reference_year', 'stale_witness', 'after_close'])
def test_original_historical_document_references_are_not_session_clocks(tmp_path, case):
    """Real historical titles may be classified; genuine chronology stays binding."""
    from pipeline.ingestion.header_attendance import header_attendance_before_vote
    from pipeline.ingestion.historical_references import original_historical_references
    import hashlib
    meeting = {'id':159, 'archive_path':'apps/pipeline/tests/fixtures/header-attendance/159',
               'meeting_date':'2026-03-03', 'classification':'Council', 'municipality_slug':'langford', 'organization_id':1}
    source = load_official_minutes(meeting, root=ROOT, people=PEOPLE, cache_dir=tmp_path/'cache')
    path = ROOT/source['source_file']
    if case in ('reversal', 'other_day', 'transition'):
        addition = {'reversal':'Council discussed business at 6:59 pm.', 'other_day':'Council continued on March 3, 2026.', 'transition':'Council reconvene.'}[case]
        source['text'] = source['text'].replace('7:12 pm', '7:12 pm\n'+addition)
    if case == 'missing_mode':
        source['text'] = source['text'].replace('5:15pm (ADOPT)', '5:15pm')
        for b in source['blocks']:
            b['motion_text'] = b['motion_text'].replace('5:15pm (ADOPT)', '5:15pm')
            b['source_block'] = b['source_block'].replace('5:15pm (ADOPT)', '5:15pm')
    if case == 'future_reference':
        for field in ('text',): source[field] = source[field].replace('February 12, 2026 5:15pm', 'March 3, 2026 5:15pm')
        for b in source['blocks']:
            for field in ('motion_text', 'source_block'): b[field] = b[field].replace('February 12, 2026 5:15pm', 'March 3, 2026 5:15pm')
    if case in ('conditional_reference', 'current_reference', 'missing_reference_year'):
        before, after = {'conditional_reference':('5:15pm (ADOPT)', '5:15pm (ADOPT) if Council resumes'),
                         'current_reference':('February 12, 2026 5:15pm', 'March 2, 2026 5:15pm'),
                         'missing_reference_year':('February 12, 2026 5:15pm', 'February 12 5:15pm')}[case]
        source['text'] = source['text'].replace(before, after)
        for b in source['blocks']:
            for field in ('motion_text', 'source_block'): b[field] = b[field].replace(before, after)
    if case == 'wrong_wrapper':
        source['blocks'][2]['result'] = 'DEFEATED'
    if case == 'missing_geometry':
        import fitz
        variant = tmp_path/'geometry.pdf'
        with fitz.open(path) as doc:
            page = doc[1]
            target = next(w for w in page.get_text('words') if w[4] == '8.1')
            page.add_redact_annot(fitz.Rect(target[:4]), fill=(1,1,1)); page.apply_redactions(); doc.save(variant)
        path = variant
        source['source_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    proof = original_historical_references(source['text'], path, source['blocks'], source['local_date'], source['source_format'], source['source_sha256'])
    source['historical_chronology_references'] = proof
    if case == 'missing_heading':
        proof['references'] = [r for r in proof['references'] if r['kind'] != 'historical_committee_resolutions_heading_reference']
    if case == 'stale_witness':
        source['text'] = source['text'].replace('7:12 pm', '7:12 pm Council reconvene.')
    original = deepcopy(source)
    block = source['blocks'][15 if case == 'after_close' else 1]
    position = source['text'].index(block['motion_text'])
    result = header_attendance_before_vote(source, block, position)
    assert source == original
    if case == 'original':
        assert result['status'] == 'header_attendance_validated'
        assert result['absent_person_ids'] == [1,23]
        refs = result['clock_bounds'][0]['historical_reference_classification']
        assert len(refs) == 6
        assert [r['kind'] for r in refs].count('historical_received_draft_minutes_reference') == 1
        assert all(source['text'][r['start']:r['end']] == r['consumed_text'] for r in refs)
        members = [{'person_id':p['id'], 'name':p['name'], 'organization_id':1, 'classification':'Council',
                    'role':'Mayor' if p['id']==1 else 'Councillor', 'start_date':'2022-11-07', 'end_date':None} for p in PEOPLE]
        ballot = evaluate_ballot({'id':999, 'meeting_id':159, 'text_content':block['motion_text'], 'result':'CARRIED'},
            {'status':'available', 'meeting':meeting, 'source':source, 'people':PEOPLE, 'memberships':members, 'policy':POLICY})
        assert ballot['status'] == 'reconstructable_candidate'
        assert {v['person_id']:v['vote'] for v in ballot['votes']} == {21:'Yes',22:'Yes',34:'Yes',35:'Yes'}
        assert all(source[key] == original[key] for key in original)
    else:
        assert result['status'] == 'header_arrival_vote_time_unresolved'
