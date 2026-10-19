"""Source inventory and identity continuity at the ordinary-ingest planner."""
from copy import deepcopy
from pathlib import Path

import pytest

from pipeline.ingestion.canonical_motions import canonical_motion_plan
from pipeline.ingestion.official_ballots import load_official_minutes
from ingestion.ballot_fixture import official_context, TEXT


@pytest.mark.parametrize('proposal', [None, 'THAT Council deny Bylaw No. 2269, 2026.'])
def test_official_motion_exists_even_when_model_omits_it_or_invents_another(tmp_path, proposal):
    context = official_context(tmp_path)
    proposals = [] if proposal is None else [{'motion_text': proposal, 'result': 'DEFEATED'}]
    items, report = canonical_motion_plan([{'title': 'Model agenda', 'item_order': '1', 'motions': proposals}], context, [])
    motions = [motion for item in items for motion in item['motions']]
    assert [(motion['motion_text'], motion['result']) for motion in motions] == [(TEXT, 'CARRIED')]
    assert report['mapped_motions'] == report['source_motions'] == 1
    assert report['held'] == []
    assert items[0]['_unverified_motion_proposals'] == proposals


@pytest.mark.parametrize('source_body_changed', [False, True])
def test_replaced_source_reuses_exact_legacy_id_or_holds_without_duplicate(tmp_path, source_body_changed):
    context = official_context(tmp_path)
    items, _ = canonical_motion_plan([], context, [])
    original = items[0]['motions'][0]
    legacy = {'id': 309, 'agenda_item_id': 99, 'text_content': TEXT, 'meta': {'canonical_source_motion': original['_canonical_source_motion']}}
    revision = deepcopy(context)
    path = tmp_path / context['source']['source_file']
    html = path.read_text()
    path.write_text(html.replace('2269', '2270') if source_body_changed else html+'<!-- publisher revision -->')
    revision['source'] = load_official_minutes(context['meeting'], root=tmp_path, people=context['people'], cache_dir=tmp_path/'cache')
    items, report = canonical_motion_plan([], revision, [legacy])
    motions = [motion for item in items for motion in item['motions']]
    if source_body_changed:
        assert motions == []
        assert report['held'][0]['reason'] == 'unmapped_legacy_records'
        assert report['unmapped_legacy_ids'] == [309]
    else:
        assert len(motions) == 1
        assert motions[0]['_existing_motion']['id'] == 309
        identity = motions[0]['_canonical_source_motion']
        assert identity['key'] != original['_canonical_source_motion']['key']
        assert identity['previous_keys'] == [original['_canonical_source_motion']['key']]
        assert report['held'] == []


def test_ordinary_committee_source_context_routes_cac_and_retains_membership_proofs(tmp_path):
    from unittest.mock import MagicMock, patch
    from ingestion.test_committee_ballots import context, PEOPLE, MEMBERS, POLICY
    from pipeline.ingestion.meeting_ballots import prepare_ballot_context, evaluate_ballot
    motion, source, meeting = context(tmp_path)
    # Actual catalog title is generic despite the original CAC heading.
    assert meeting['title'] == 'Advisory Committee'
    client = MagicMock()
    values = {'municipalities':{'slug':'langford'}, 'organizations':[{'id':10}],
              'memberships':[{**member, 'person':{'name':member['name']}} for member in MEMBERS], 'people':PEOPLE}
    tables = {}
    for name, value in values.items():
        table = MagicMock()
        for method in ('select','eq','in_','maybe_single','order','range'):
            getattr(table, method).return_value = table
        table.execute.return_value = MagicMock(data=value)
        tables[name] = table
    client.table.side_effect = tables.__getitem__
    fixtures = Path(__file__).parents[1]/'fixtures'
    http = MagicMock()
    http.get.side_effect = [MagicMock(content=(fixtures/'langford-cac-policy-2024.pdf').read_bytes()), MagicMock(content=(fixtures/'langford-cac-appointments-section.html').read_bytes())]
    with patch('pipeline.ingestion.meeting_ballots.refresh_vote_policy', return_value={**POLICY,'rule_id':'validated-cac-policy'}), patch('pipeline.ingestion.committee_ballots.requests.Session', return_value=http):
        prepared = prepare_ballot_context(client, municipality_id=2, meeting=meeting, root=tmp_path)
    assert prepared['status'] == 'available'
    items, report = canonical_motion_plan([], prepared, [])
    assert report['mapped_motions'] == 1
    assert items[0]['motions'][0]['motion_text'] == motion['text_content']
    ballot = evaluate_ballot(motion, prepared)
    assert ballot['status'] == 'reconstructable_candidate'
    proof = ballot['proof']
    assert proof['voting_body'] == 'community_advisory_committee'
    assert proof['outcome_role'] == 'committee_guidance_or_recommendation'
    assert len(proof['member_observations']) == 8
    assert proof['committee_quorum_minimum_appointees'] == 5
    assert proof['committee_chair_person_ids'] == [1,2]
    assert 'excluded_nonvoting_attendees' in proof
    assert proof['committee_policy_validation']['status']=='verified_unchanged'
    assert proof['committee_policy_validation']['identity_section_sha256']


@pytest.mark.parametrize('actor,expected', [('Colby Harder',21),('Keith Harder',None)])
def test_source_actor_needs_full_native_roster_identity_not_surname_only(tmp_path,actor,expected):
    context = official_context(tmp_path)
    path = tmp_path/context['source']['source_file']
    path.write_text(path.read_text().replace('Colby Harder</div></div><div class="SecondedBy">',actor+'</div></div><div class="SecondedBy">'))
    context['source'] = load_official_minutes(context['meeting'],root=tmp_path,people=context['people'],cache_dir=tmp_path/'cache')
    items, report = canonical_motion_plan([],context,[])
    assert report['mapped_motions']==1
    assert items[0]['motions'][0]['_canonical_actor_ids']['mover']==expected
