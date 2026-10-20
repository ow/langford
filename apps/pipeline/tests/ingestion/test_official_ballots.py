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


def _mayor_role_context(tmp_path, event, *, official_label=True):
    from pipeline.ingestion.official_ballots import load_official_minutes
    context=official_context(tmp_path,event=('The public hearing continued. '*10)+'\n'+event)
    if official_label:
        path=tmp_path/'archive/meeting/Minutes/Minutes.html'
        path.write_text(path.read_text().replace('<li>Scott Goodmanson</li>','<li>Mayor S. Goodmanson</li>'))
        context['source']=load_official_minutes(context['meeting'],root=tmp_path,people=PEOPLE,cache_dir=tmp_path/'cache')
    context['memberships']=[{**m,'role':'Mayor' if m['person_id']==1 else 'Councillor'} for m in MEMBERS]
    return context


def test_source_bound_mayor_return_restores_same_voter_after_documented_exit(tmp_path):
    # Public-hearing text separates the named exit and role-only return, as in
    # the June6,2022 original. A nearby-name heuristic loses the returning voter.
    context=_mayor_role_context(tmp_path,'Mayor Goodmanson left the meeting at 7:05 pm.\n'+('The public hearing continued. '*10)+'\nThe Mayor returned to the meeting at 7:10 pm.')
    choices,meta=merge_ballot_evidence(motion(),[],context)
    assert {v['person_id'] for v in choices}=={1,21,23,24,25,26}
    proof=meta['ballot_reconstruction']
    assert [(e['person_id'],e['state']) for e in proof['presence_events']]==[(1,'absent'),(1,'present')]
    role=proof['presence_events'][-1]['role_binding']
    assert role['source_quote']=='Mayor S. Goodmanson'
    assert role['membership_role']=='Mayor'
    assert role['membership_start']=='2022-11-07'


@pytest.mark.parametrize('missing_proof',['official_label','dated_role','matching_identity','unique_official_mayor'])
def test_generic_mayor_departure_without_both_role_proofs_holds_whole_ballot(tmp_path,missing_proof):
    from pipeline.ingestion.official_ballots import load_official_minutes
    context=_mayor_role_context(tmp_path,'The Mayor left the meeting at 7:05 pm.',official_label=missing_proof!='official_label')
    if missing_proof=='dated_role':context['memberships']=[{k:v for k,v in m.items() if k!='role'} for m in context['memberships']]
    if missing_proof=='matching_identity':context['memberships']=[{**m,'role':'Mayor' if m['person_id']==21 else 'Councillor'} for m in context['memberships']]
    if missing_proof=='unique_official_mayor':
        path=tmp_path/'archive/meeting/Minutes/Minutes.html';path.write_text(path.read_text().replace('<li>Colby Harder</li>','<li>Mayor C. Harder</li>'))
        context['source']=load_official_minutes(context['meeting'],root=tmp_path,people=PEOPLE,cache_dir=tmp_path/'cache')
    choices,meta=merge_ballot_evidence(motion(),[],context)
    assert choices==[]
    assert meta['ballot_reconstruction']['status']=='unparsed_presence_event'


@pytest.mark.parametrize('case', ['dissent_before_outcome', 'complete_recital_body', 'counted_rollcall', 'count_mismatch', 'repeated_role_rollcall', 'unknown_repeated_role', 'inline_amendment_mover', 'punctuation_mover', 'joined_that_council'])
def test_native_pdf_ballot_keeps_formal_body_and_pre_outcome_dissent(tmp_path, case):
    """Native layout must not turn a named No into an inferred Yes or lose recitals."""
    import fitz
    from pipeline.ingestion.official_ballots import load_official_minutes
    context = official_context(tmp_path)
    body = 'WHEREAS Council values trees that provide shade;\nTHAT Council adopt Tree Protection Bylaw No. 2269, 2026 as presented.' if case == 'complete_recital_body' else TEXT
    if case == 'joined_that_council':
        body = TEXT.replace('THAT Council', 'THATCouncil')
    before = '\nOPPOSED: Mayor Goodmanson\n' if case == 'dissent_before_outcome' else '\n'
    if case in ('counted_rollcall', 'count_mismatch'):
        before = f'\nFor ({5 if case == "count_mismatch" else 4}): HARDER, GUIRY, WAGNER, YACUCHA\nAgainst (2): GOODMANSON, MORLEY\n'
    continuation = ''
    if case in ('repeated_role_rollcall', 'unknown_repeated_role'):
        before = ('\nIn Favour: Councillor Harder\nCouncillor Guiry\nCouncillor Wagner\n'
            + ('Councillor Yacuchaa' if case == 'unknown_repeated_role' else 'Councillor Yacucha')
            + '\n\nOpposed: Mayor Goodmanson\nCouncillor Morley\n')
        continuation = '\nAND THAT Council request a follow-up report.\n'
        body += continuation
    mover_prefix = 'Amendment:' if case == 'inline_amendment_mover' else '. ' if case == 'punctuation_mover' else ''
    text = ('Council Minutes - January 8, 2026\nPRESENT:\n' + '\n'.join(p['name'] for p in PEOPLE)
        + '\nATTENDING: Staff\n1. CALL TO ORDER\n' + mover_prefix + 'MOVED BY: Colby Harder\nSECONDED: Kimberley Guiry\n'
        + (TEXT if continuation else body) + before + continuation + 'Motion CARRIED.\n')
    path = tmp_path/'archive/meeting/Minutes/Minutes.pdf'
    document = fitz.open()
    page = document.new_page()
    page.insert_text((40, 40), text, fontsize=9)
    document.save(path)
    document.close()
    Path(str(path)+'.url').write_text('https://langford.ca/official-minutes.pdf')
    context['source'] = load_official_minutes(context['meeting'], root=tmp_path, people=PEOPLE, cache_dir=tmp_path/'pdf-cache')
    choices, meta = merge_ballot_evidence({**motion(), 'text_content':TEXT if case == 'joined_that_council' else body}, [], context)
    if case in ('count_mismatch', 'unknown_repeated_role'):
        assert choices == []
        assert meta['ballot_reconstruction']['status'] == ('explicit_rollcall_count_mismatch' if case == 'count_mismatch' else 'unresolved_dissent_names')
        return
    assert meta['individual_vote_coverage'] == 'reconstructed_complete'
    no_ids = {1,26} if case in ('counted_rollcall','repeated_role_rollcall') else {1} if case == 'dissent_before_outcome' else set()
    assert {v['person_id']:v['vote'] for v in choices} == {p['id']:('No' if p['id'] in no_ids else 'Yes') for p in PEOPLE}
    assert 'OPPOSED' not in meta['ballot_reconstruction']['source_motion_text']
    if case == 'complete_recital_body':
        assert meta['ballot_reconstruction']['source_motion_text'].startswith('WHEREAS Council values trees that provide shade;')
    elif case == 'dissent_before_outcome':
        assert meta['ballot_reconstruction']['choice_provenance']['person_1'] == 'explicit_named'
    elif case in ('counted_rollcall', 'repeated_role_rollcall'):
        assert set(meta['ballot_reconstruction']['choice_provenance'].values()) == {'explicit_named'}
    if mover_prefix:
        from pipeline.ingestion.canonical_motions import canonical_motion_plan
        items, _ = canonical_motion_plan([], context, [])
        source_motion = next(m for item in items for m in item['motions'])
        assert source_motion['_canonical_actor_ids'] == {'mover':21, 'seconder':23}
    if case == 'joined_that_council':
        assert meta['ballot_reconstruction']['source_motion_text'] == body


@pytest.mark.parametrize('moved_label', ['MOVED BY:', 'Moved:'])
def test_native_resumed_main_motion_keeps_its_own_wrapped_dissent(tmp_path, moved_label):
    """Archive pattern: an amendment and its resumed main motion have separate ballots."""
    import fitz
    from pipeline.ingestion.official_ballots import load_official_minutes
    context = official_context(tmp_path)
    people = PEOPLE + [{'id':27,'name':'Lillian Szpak'}]
    members = MEMBERS + [{'person_id':27,'name':'Lillian Szpak','start_date':'2022-11-07','end_date':None,'classification':'Council'}]
    text = ('Council Minutes - January 8, 2026\nPRESENT:\n'+'\n'.join(p['name'] for p in people)
        +f'\nATTENDING: Staff\n1. CALL TO ORDER\n{moved_label} Colby Harder\nSeconded: Kimberley Guiry\n'
        +'THAT Council amend the report to include a tree survey.\nMotion CARRIED.\nMayor Goodmanson opposed.\n'
        +'On the Main Motion as amended:\n'+TEXT+'\nMotion CARRIED.\n'+'\n'*18
        +'Councillors Guiry, Harder and\nSzpak opposed.\n')
    path = tmp_path/'archive/meeting/Minutes/Minutes.pdf'
    document = fitz.open()
    document.new_page().insert_text((40,40),text,fontsize=9)
    document.save(path)
    document.close()
    Path(str(path)+'.url').write_text('https://langford.ca/official-minutes.pdf')
    context.update({'people':people,'memberships':members})
    context['source'] = load_official_minutes(context['meeting'],root=tmp_path,people=people,cache_dir=tmp_path/'pdf-cache')
    choices,meta = merge_ballot_evidence(motion(),[],context)
    assert meta['individual_vote_coverage'] == 'reconstructed_complete'
    assert {v['person_id']:v['vote'] for v in choices} == {p['id']:('No' if p['id'] in {21,23,27} else 'Yes') for p in people}
    assert meta['ballot_reconstruction']['choice_provenance']['person_1'] == 'inferred_official_dissent_recording_rule'
    assert all(meta['ballot_reconstruction']['choice_provenance'][f'person_{pid}']=='explicit_named' for pid in (21,23,27))


@pytest.mark.parametrize('complete',[True,False])
def test_historical_fully_named_rollcall_does_not_need_later_dissent_recording_rule(tmp_path,complete):
    """Old explicit 4–2 is evidence; an unnamed sixth voter remains unknown."""
    from pipeline.ingestion.official_ballots import load_official_minutes
    yes='Scott Goodmanson, Colby Harder, Kimberley Guiry'+(', Mary Wagner' if complete else '')
    context=official_context(tmp_path,source_date='June 8, 2020',opposition=f'For ({4 if complete else 3}): {yes}\nAgainst (2): Keith Yacucha, Mark Morley')
    context['memberships']=[{**m,'start_date':'2018-11-05'} for m in MEMBERS]
    path=tmp_path/'archive/meeting/Minutes/Minutes.html'
    historical_text='THAT Council give Bylaw No. 1915 second and third readings.'
    path.write_text(path.read_text().replace(TEXT,historical_text))
    context['source']=load_official_minutes(context['meeting'],root=tmp_path,people=PEOPLE,cache_dir=tmp_path/'cache')
    choices,metadata=merge_ballot_evidence({**motion(),'text_content':historical_text},[],context)
    if complete:
        assert {v['person_id']:v['vote'] for v in choices}=={1:'Yes',21:'Yes',23:'Yes',24:'Yes',25:'No',26:'No'}
        proof=metadata['ballot_reconstruction']
        assert proof['basis']=='every_present_voter_explicitly_named'
        assert set(proof['choice_provenance'].values())=={'explicit_named'}
    else:
        assert choices==[]
        assert metadata.get('individual_vote_coverage')!='reconstructed_complete'


@pytest.mark.parametrize('body,expected', [
    ('THAT Council advise the property owner that the period for request of reconsideration is shortened to noon.', 'reconstructed_complete'),
    ('THAT Council impose a remedial order and notify the owner they may request reconsideration by Council.', 'reconstructed_complete'),
    ('THAT Council direct staff to review the need for unanimous consent to extend public participation or a meeting adjournment time.', 'reconstructed_complete'),
    ('THAT Council at 9:55 pm extend the meeting until 11:00 pm.', 'special_voting_threshold_needs_validation'),
    ('THAT Council at 9:53 pm, extend the meeting until 11:00 pm.', 'special_voting_threshold_needs_validation'),
    ("THAT Council receive the owner's letter; AND THAT Council request reconsideration of the permit.", 'special_voting_threshold_needs_validation'),
    ('THAT Council reconsider the decision on the permit.', 'special_voting_threshold_needs_validation'),
    ('THAT Council sustain the ruling of the Chair.', 'special_voting_threshold_needs_validation'),
])
def test_special_threshold_follows_the_resolution_action(tmp_path, body, expected):
    from pipeline.ingestion.official_ballots import load_official_minutes
    context = official_context(tmp_path)
    path = tmp_path/'archive/meeting/Minutes/Minutes.html'
    path.write_text(path.read_text().replace(TEXT, body))
    context['source'] = load_official_minutes(context['meeting'], root=tmp_path, people=PEOPLE, cache_dir=tmp_path/'cache')
    choices, meta = merge_ballot_evidence({**motion(), 'text_content':body}, [], context)
    if expected == 'reconstructed_complete':
        assert meta['individual_vote_coverage'] == expected
        assert {v['person_id'] for v in choices} == {1,21,23,24,25,26}
    else:
        assert choices == []
        assert meta['ballot_reconstruction']['status'] == expected


@pytest.mark.parametrize('has_prior_choice', [False, True])
@pytest.mark.parametrize('source_kind', ['withdrawn', 'documentary_adjournment', 'tabled'])
def test_non_ballot_source_is_not_missing_votes_and_never_erases_a_choice(tmp_path, has_prior_choice, source_kind):
    result = 'TABLED' if source_kind == 'tabled' else 'WITHDRAWN'
    context = official_context(tmp_path, result=result)
    row = motion(result)
    expected = 'not_a_yes_no_decision'
    if source_kind == 'documentary_adjournment':
        import fitz
        from pipeline.ingestion.official_ballots import load_official_minutes
        body = 'The Chair adjourned the meeting at 8:05 pm.'
        text = ('Council Minutes - January 8, 2026\nPRESENT:\n'+'\n'.join(p['name'] for p in PEOPLE)
                +'\nATTENDING: Staff\n1. ADJOURNMENT\nMOVED BY: GUIRY\nSECONDED: HARDER\n'
                +body+'\nMotion CARRIED.\n')
        path = tmp_path/'archive/meeting/Minutes/Minutes.pdf'
        document = fitz.open()
        document.new_page().insert_text((40,40), text, fontsize=9)
        document.save(path)
        document.close()
        context['source'] = load_official_minutes(context['meeting'], root=tmp_path, people=PEOPLE, cache_dir=tmp_path/'pdf-cache')
        row = {**motion(), 'text_content':body}
        expected = 'source_documentary_event_not_resolution'
    prior = {'votes':[{'person_id':21,'vote':'No'}]} if has_prior_choice else None
    choices, meta = merge_ballot_evidence(row, [], context, prior)
    if has_prior_choice:
        assert [(v['person_id'], v['vote']) for v in choices] == [(21, 'No')]
        assert meta['individual_vote_coverage'] == 'named_only'
    elif source_kind == 'tabled':
        assert choices == []
        assert meta['individual_vote_coverage'] == 'named_only'
    else:
        assert choices == []
        assert meta['individual_vote_coverage'] == 'not_applicable'
        assert meta['vote_record']['coverage'] == 'not_applicable'
    assert meta['ballot_reconstruction']['status'] == expected


@pytest.mark.parametrize('case,admitted', [
    ('own_agenda', True),
    ('closed_target_then_later_vote', True),
    ('different_member_and_item', True),
    ('target_vote', False),
    ('missing_return', False),
    ('earlier_episode_only', False),
    ('return_after_peer', False),
    ('unclosed_main', False),
    ('duplicate_target', False),
    ('exit_before_heading', False),
    ('unknown_chair', False),
    ('unknown_member', False),
    ('movement_in_bullet', False),
    ('standalone_declaration', False),
])
def test_documentary_agenda_reference_requires_its_own_closed_target_episode(tmp_path, case, admitted):
    """An agenda notice cannot backdate absence or discharge another item's conflict."""
    import fitz
    from pipeline.ingestion.official_ballots import load_official_minutes
    context = official_context(tmp_path)
    person = 'Councillor Wagner' if case == 'different_member_and_item' else 'Mayor Goodmanson'
    person_id = 24 if case == 'different_member_and_item' else 1
    label = '7.2.3' if case == 'different_member_and_item' else '8.1.2'
    subject = 'Mayor Goodmanson and Mystery' if case == 'unknown_member' else person
    agenda = ('THAT Council approve the amended agenda as follows and that the agenda be renumbered accordingly:\n'
              f"- Separate item 5 \"Public Participation\" in two to accommodate {subject}'s\n"
              f'  perceived pecuniary conflict of interest pertaining to agenda item {label} - Tree policy.')
    if case == 'movement_in_bullet':
        agenda += f' {person} left the meeting at 7:01 pm.'
    if case == 'standalone_declaration':
        agenda = 'THAT Council approve the agenda as presented.'
    pair = 'MOVED BY: GUIRY\nSECONDED: HARDER\n'
    earlier = f'{person} left the meeting at 7:08 pm.\n\n{person} returned to the meeting at 7:10 pm.\n\n'
    introduction = (f'{person} declared a perceived pecuniary conflict of interest and left\n'
                    'the meeting at 7:36 pm\n\nCouncillor Harder assumed the role of the Chair.\n\n')
    returned = f'{person} returned to the meeting at 7:45 pm and assumed the role of the Chair.\n\n'
    if case == 'earlier_episode_only':
        introduction = returned = ''
    if case == 'missing_return':
        returned = ''
    extra = 'MOVED BY: MORLEY\nTHAT Council first consider a different pending motion.\n\n' if case == 'unclosed_main' else ''
    standalone = f'{person} declared a perceived conflict of interest regarding the Tree policy.\n\n' if case == 'standalone_declaration' else ''
    if case == 'unknown_chair':
        introduction = introduction.replace('Councillor Harder assumed', 'Councillor Mystery assumed')
    duplicate = f'{label} Other policy\n\n' if case == 'duplicate_target' else ''
    pre_heading = introduction if case == 'exit_before_heading' else ''
    if case == 'exit_before_heading':
        introduction = ''
    text = ('Council Minutes - January 8, 2026\nPRESENT:\n'+'\n'.join(p['name'] for p in PEOPLE)
            +'\nATTENDING: Staff\n1. CALL TO ORDER\n4. APPROVAL OF THE AGENDA\n'
            +pair+agenda+'\nMotion CARRIED.\n\n'+standalone+'5. PUBLIC PARTICIPATION\n'+earlier
            +duplicate+pre_heading+f'{label} Tree policy\n\n'+introduction+extra+pair+'THAT Council approve the tree policy.\nMotion CARRIED.\n\n'
            +('' if case == 'return_after_peer' else returned)+'9. NOTICE OF INTENT\n'
            +(returned if case == 'return_after_peer' else '')+pair+TEXT+'\nMotion CARRIED.\n')
    path = tmp_path/'archive/meeting/Minutes/Minutes.pdf'
    document = fitz.open()
    assert document.new_page().insert_textbox(fitz.Rect(35,35,570,810), text, fontsize=8) >= 0
    document.save(path)
    document.close()
    Path(str(path)+'.url').write_text('https://langford.ca/official-minutes.pdf')
    context['source'] = load_official_minutes(context['meeting'], root=tmp_path, people=PEOPLE, cache_dir=tmp_path/'pdf-cache')
    body = agenda if case == 'own_agenda' else 'THAT Council approve the tree policy.' if case == 'target_vote' else TEXT
    choices, meta = merge_ballot_evidence({**motion(), 'text_content':body}, [], context)
    if admitted:
        assert meta['individual_vote_coverage'] == 'reconstructed_complete', meta['ballot_reconstruction']
        assert {v['person_id'] for v in choices} == {1,21,23,24,25,26}
        proof = meta['ballot_reconstruction']
        assert proof['documentary_presence_observations'][0]['state_effect'] == 'none'
        if case != 'own_agenda':
            assert [(e['person_id'],e['state']) for e in proof['presence_events']] == [(person_id,'absent'),(person_id,'present')]*2
    else:
        assert choices == []
        assert meta['ballot_reconstruction']['status'] == 'unparsed_presence_event'
