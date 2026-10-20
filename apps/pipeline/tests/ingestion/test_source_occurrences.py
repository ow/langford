"""Original formal occurrences own ballots; repeated headings do not."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import pytest
from pipeline.ingestion.official_ballots import load_official_minutes
from pipeline.ingestion.meeting_ballots import evaluate_ballot, merge_ballot_evidence
from pipeline.ingestion.canonical_motions import canonical_motion_plan, source_identity, normalize_text
from ingestion.ballot_fixture import POLICY

ROOT=Path(__file__).resolve().parents[4]
FIXTURE=ROOT/'apps/pipeline/tests/fixtures/source-occurrences'
DATA=json.loads((FIXTURE/'cases.json').read_bytes())


def context_for(tmp_path, meeting_id):
    meeting=deepcopy(DATA['meetings'][str(meeting_id)])
    people=DATA['people']
    members=[{'person_id':p['id'],'name':p['name'],'organization_id':1,'classification':'Council','role':'Mayor'if p['id']==1 else'Councillor','start_date':'2022-11-07','end_date':None}for p in people]
    source=load_official_minutes(meeting,root=ROOT,people=people,cache_dir=tmp_path/'cache')
    return {'status':'available','meeting':meeting,'source':source,'people':people,'memberships':members,
            'policy':{**POLICY,'committee_of_the_whole_scope':{'basis':'Council sitting as Committee of the Whole; Procedure Bylaw sections4/56'}}}


@pytest.mark.skipif(not shutil.which('pdftotext'),reason='Original formal ownership requires Poppler')
@pytest.mark.parametrize('case',['legacy_first','legacy_second','bound_second','heading_repeat','resumed_main','indented_resumed_main','omitted_resumed_anchor'])
def test_original_formal_envelope_owns_ballot_not_duplicate_words(tmp_path,case):
    mid=289 if case=='heading_repeat'else 20 if case=='resumed_main'else 167 if case in ('indented_resumed_main','omitted_resumed_anchor')else 348
    context=context_for(tmp_path,mid)
    motion=deepcopy(DATA['motions'][str(2912 if case=='heading_repeat'else 1791 if case=='resumed_main'else 1767 if mid==167 else 3457 if case=='legacy_first'else 3459)])
    if case=='bound_second':
        block=next(b for b in context['source']['blocks']if normalize_text(b['motion_text'])==normalize_text(motion['text_content']))
        # A real persisted canonical identity is re-proved against its original
        # complete envelope, not trusted because it supplies a matching key.
        motion['meta']={'canonical_source_motion':source_identity(mid,context['source'],block)}
    if case=='omitted_resumed_anchor':
        block=next(b for b in context['source']['blocks']if b.get('formal_source_kind')=='resumed_main_motion')
        block['source_block']=block['source_block'].split('\n',1)[1].lstrip()
    original=deepcopy(context['source'])
    result=evaluate_ballot(motion,context)
    assert all(context['source'][key]==original[key]for key in ('text','roster_quote','blocks','operative_views'))
    if case=='omitted_resumed_anchor':
        assert result['status']=='source_motion_not_exact_or_ambiguous'
        assert not result.get('votes')
        assert result['source_occurrence_hold'][0]['matching_formal_envelopes']==1
        assert result['source_occurrence_hold'][0]['own_formal_envelopes']==0
    elif case.startswith('legacy_'):
        assert result['status']=='source_motion_not_exact_or_ambiguous'
        assert not result.get('votes')
        assert result['source_occurrence_hold'][0]['matching_formal_envelopes']==2
        choices,metadata=merge_ballot_evidence(motion,[],context)
        assert not choices
        assert metadata['individual_vote_coverage']!='reconstructed_complete'
    else:
        assert result['status']=='reconstructable_candidate'
        expected={1:'Yes',20:'Yes',21:'Yes',22:'Yes',23:'Yes',34:'Yes',35:'Yes'}
        if case=='resumed_main':expected.update({22:'No',23:'No',35:'No'})
        assert {v['person_id']:v['vote']for v in result['votes']}==expected
        if case=='heading_repeat':
            assert result['operative_motion_body']['status']=='native_body_not_uniquely_bound_held'
        elif case in ('resumed_main','indented_resumed_main'):
            assert result['proof']['source_occurrence_validation']['envelope']['kind']=='resumed_main_motion'
        else:
            assert result['proof']['source_occurrence_validation']['method']=='current_bound_original_formal_envelope'
            assert result['proof']['source_motion_identity']['key']==motion['meta']['canonical_source_motion']['key']


@pytest.mark.skipif(not shutil.which('pdftotext'),reason='Original formal coverage requires Poppler')
def test_recovered_ocr_introduction_does_not_resolve_duplicate_legacy_ownership(tmp_path):
    context=context_for(tmp_path,348)
    legacy=[deepcopy(DATA['motions'][str(mid)])for mid in (3457,3459)]
    items,report=canonical_motion_plan([],context,legacy)
    assert report['formal_source_coverage']=='all_formal_envelopes_accounted_for'
    assert not report.get('unparsed_formal_occurrence_leads')
    recovered=[block for block in context['source']['blocks']if 'iVIOVED BY: HARDER'in block['source_block'].split(block['motion_text'],1)[0]]
    assert len(recovered)==1
    assert recovered[0]['motion_text']=='THATthe Committee of the Whole receive this report for information.'
    assert any(row['reason']=='original_formal_occurrence_not_unique'for row in report['held'])
    assert all(normalize_text(m['motion_text'])!=normalize_text(DATA['motions']['3459']['text_content'])for item in items for m in item['motions'])
