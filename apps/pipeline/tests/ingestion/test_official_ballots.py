"""Original source + per-vote roster + validated policy are required together."""
from pathlib import Path
import hashlib

import pytest

from pipeline.ingestion.meeting_ballots import merge_ballot_evidence

from .ballot_fixture import PEOPLE, MEMBERS, TEXT, POLICY, official_context


def motion(result='CARRIED'):
    return {'id':91,'meeting_id':77,'result':result,'text_content':TEXT,'meta':{'vote_record':{'extracted_vote_proposals':[{'person_name':'Colby Harder','vote':'Yes'}]}}}


def test_native_official_source_reconstructs_complete_ballot_and_provenance(tmp_path):
    context=official_context(tmp_path,opposition='Councillor Goodmanson opposed.')
    choices,metadata=merge_ballot_evidence(motion(),[],context)
    assert {v['person_id']:v['vote'] for v in choices}=={1:'No',21:'Yes',23:'Yes',24:'Yes',25:'Yes',26:'Yes'}
    assert metadata['individual_vote_coverage']=='reconstructed_complete'
    proof=metadata['ballot_reconstruction']
    assert proof['source_sha256']==hashlib.sha256((tmp_path/'archive/meeting/Minutes/Minutes.html').read_bytes()).hexdigest()
    assert proof['choice_provenance']['person_1']=='explicit_named'
    assert proof['choice_provenance']['person_21']=='inferred_official_dissent_recording_rule'
    assert metadata['vote_record']['extracted_vote_proposals']==motion()['meta']['vote_record']['extracted_vote_proposals']


@pytest.mark.parametrize('case,expected',[
    ('policy_changed','changed_document_requires_machine_re_evaluation'),
    ('future','recording_rule_date_not_validated'),
    ('ambiguous_presence','unparsed_presence_event'),
    ('unknown_roster','roster_unknown_names'),
    ('unanimity_conflict','unanimous_result_conflicts_with_named_choice'),
    ('committee_source','source_committee_membership_rules_need_validation'),
    ('missing_memberships','dated_council_membership_unavailable'),
    ('missing_member','council_membership_mismatch'),
])
def test_uncertain_documentary_ballot_never_supplies_missing_yes_votes(tmp_path,case,expected):
    context=official_context(tmp_path,result='CARRIED UNANIMOUSLY' if case=='unanimity_conflict' else 'CARRIED',opposition='Councillor Goodmanson opposed.' if case=='unanimity_conflict' else '',event='Councillor Harder recused herself.' if case=='ambiguous_presence' else '',unknown='<li>Bob Smith</li>' if case=='unknown_roster' else '',source_title='Advisory Committee Meeting' if case=='committee_source' else 'Council Meeting')
    if case=='policy_changed':context['policy']={**POLICY,'policy_status':expected}
    if case=='future':context['policy']={**POLICY,'enabled_through':'2026-01-07'}
    if case=='missing_memberships':context['memberships']=[]
    if case=='missing_member':context['memberships']=MEMBERS[1:]
    choices,metadata=merge_ballot_evidence(motion('CARRIED UNANIMOUSLY' if case=='unanimity_conflict' else 'CARRIED'),[],context)
    assert choices==[]
    assert metadata['ballot_reconstruction']['status']==expected
    assert metadata.get('individual_vote_coverage')!='reconstructed_complete'


def test_preserved_prior_choice_blocks_conflicting_inference_and_keeps_provenance(tmp_path):
    context=official_context(tmp_path)
    prior={'motion':{'meta':{'ballot_reconstruction':{'choice_provenance':{'person_21':'explicit_named'},'source_sha256':'prior-source'}}},'votes':[{'motion_id':70,'person_id':21,'vote':'No'}]}
    choices,metadata=merge_ballot_evidence(motion(),[],context,prior)
    assert [(v['person_id'],v['vote']) for v in choices]==[(21,'No')]
    assert metadata['individual_vote_coverage']=='named_only'
    assert metadata['ballot_reconstruction']['status']=='existing_vote_conflicts_with_reconstructed_ballot'
    assert metadata['prior_ballot_proof']['source_sha256']=='prior-source'
    assert metadata['ballot_reconstruction']['choice_provenance']['person_21']=='explicit_named'


def test_physical_departure_changes_voters_and_unanimity_has_distinct_basis(tmp_path):
    context=official_context(tmp_path,result='CARRIED UNANIMOUSLY',event='Councillor Harder left the room at 7:10 pm.')
    choices,metadata=merge_ballot_evidence(motion('CARRIED UNANIMOUSLY'),[],context)
    assert {v['person_id'] for v in choices}=={1,23,24,25,26}
    assert metadata['ballot_reconstruction']['basis']=='explicit_unanimity_with_per_vote_roster'
    assert set(metadata['ballot_reconstruction']['choice_provenance'].values())=={'inferred_explicit_unanimity'}



def test_context_refreshes_official_policy_and_builds_ballot_without_human_step(tmp_path,monkeypatch):
    import json
    from datetime import datetime,timezone
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from pipeline.ingestion.meeting_ballots import prepare_ballot_context
    original=official_context(tmp_path)
    import pipeline.ingestion.meeting_ballots as owner
    rule=json.loads((Path(owner.__file__).parent/'policies/langford-voting.json').read_text())
    cache=tmp_path/'reports/vote-policy';cache.mkdir(parents=True)
    (cache/'langford.json').write_text(json.dumps({'bylaw_url':rule['bylaw_url'],'bylaw_sha256':rule['bylaw_sha256'],'etag':'verified-before'}))
    session=MagicMock()
    session.get.side_effect=[SimpleNamespace(text=f'<a href="{rule["bylaw_url"]}">Council Procedure Bylaw</a>',raise_for_status=lambda:None),SimpleNamespace(status_code=304,headers={})]
    monkeypatch.setattr('pipeline.ingestion.vote_policy.requests.Session',lambda:session)
    responses={'municipalities':{'slug':'langford'},'organizations':[{'id':1}],'people':PEOPLE,'memberships':[{'person_id':row['person_id'],'start_date':row['start_date'],'end_date':row['end_date'],'person':{'name':row['name']}} for row in MEMBERS]}
    client=MagicMock()
    def table(name):
        query=MagicMock()
        for method in ['select','eq','maybe_single','in_','order','range']:getattr(query,method).return_value=query
        query.execute.return_value.data=responses[name]
        return query
    client.table.side_effect=table
    context=prepare_ballot_context(client,municipality_id=1,meeting=original['meeting'],root=tmp_path)
    choices,metadata=merge_ballot_evidence(motion(),[],context)
    assert len(choices)==6
    assert metadata['individual_vote_coverage']=='reconstructed_complete'
    assert metadata['ballot_reconstruction']['policy_checked_as_of']==datetime.now(timezone.utc).date().isoformat()


def test_held_context_cannot_inherit_a_complete_alignment_badge():
    original={**motion(),'meta':{'individual_vote_coverage':'reconstructed_complete','vote_record':{'coverage':'reconstructed_complete'}}}
    choices,metadata=merge_ballot_evidence(original,[],{'status':'verification_unavailable_hold_inference'})
    assert choices==[]
    assert metadata['individual_vote_coverage']=='named_only'
    assert metadata['vote_record']['coverage']=='not_recorded'


def test_committee_of_whole_requires_independent_scope_and_catalog_agreement(tmp_path):
    import json
    import pipeline.ingestion.meeting_ballots as owner
    context=official_context(tmp_path,source_title='Committee of the Whole Minutes')
    context['policy']=json.loads((Path(owner.__file__).parent/'policies/langford-voting.json').read_text())
    context['policy']['policy_status']='verified_unchanged'
    choices,meta=merge_ballot_evidence(motion(),[],context)
    assert choices==[]
    assert meta['ballot_reconstruction']['status']=='source_catalog_voting_body_mismatch'
    context['meeting']['title']='Committee of the Whole'
    choices,meta=merge_ballot_evidence(motion(),[],context)
    assert len(choices)==6
    assert meta['ballot_reconstruction']['voting_body']=='committee_of_the_whole'
    assert meta['ballot_reconstruction']['source_classification']=='Committee of the Whole'
    assert meta['ballot_reconstruction']['outcome_role']=='committee_guidance_or_recommendation'
    assert meta['ballot_reconstruction']['scope_basis']['original_source_sha256']=='9cf6e70459352537be177679b558bf8ab859e677e66ecba459bedd12d8709bbb'
