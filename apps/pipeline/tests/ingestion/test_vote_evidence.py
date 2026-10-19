"""Official minutes outcomes must remain attached to their own formal motion."""
from pipeline.ingestion.vote_evidence import match_minutes_motion, named_votes

MINUTES = '''
**MOVED BY: HARDER**
**SECONDED: GUIRY**
> *THAT Council receive the Judicial Review Coalition Update correspondence dated March*
18, 2026, for information.
**Motion CARRIED.**
Mayor Goodmanson opposed.
**MOVED BY: WAGNER**
**SECONDED: GOODMANSON**
> *THAT Council direct staff to write a letter indicating the City's intent to join the Judicial*
Review Coalition.
**Motion DEFEATED.**
Councillors Yacucha, Guiry, Szpak, Morley and Harder.
'''


def test_opposition_only_does_not_change_carried_outcome():
    source = match_minutes_motion('THAT Council receive the Judicial Review Coalition Update correspondence dated March 18, 2026, for information.', MINUTES)
    assert source['result'] == 'CARRIED'
    assert 'Mayor Goodmanson opposed' in source['after_outcome']
    assert 'DEFEATED' not in source['source_block']


def test_next_motion_does_not_supply_result_for_notice_or_missing_outcome():
    assert match_minutes_motion("THAT Council direct staff to plant more trees.", '''
**MOVED BY: HARDER**
**SECONDED: GUIRY**
THAT Council direct staff to plant more trees.
**MOVED BY: WAGNER**
**SECONDED: GUIRY**
THAT Council approve the 2026 financial plan.
**Motion CARRIED.**
''') is None
    assert match_minutes_motion("Mayor called the meeting to order.", MINUTES) is None


def test_duplicated_export_is_deduplicated_but_conflicting_outcomes_are_held():
    motion='THAT Council approve the agenda as presented.'
    source=f'**MOVED BY: GUIRY**\n**SECONDED: HARDER**\n{motion}\n**Motion CARRIED.**\n'
    assert match_minutes_motion(motion, source+source)['result']=='CARRIED'
    assert match_minutes_motion(motion, source+source.replace('CARRIED','DEFEATED')) is None


def test_named_votes_recovers_choices_without_attendance_inference_or_following_events():
    block = match_minutes_motion('THAT Council receive the Judicial Review Coalition Update correspondence dated March 18, 2026, for information.', MINUTES)
    block['after_outcome'] = 'Mayor Goodmanson opposed. Councillor Harder returned to the meeting.'
    block['source_block'] += '\n'+block['after_outcome']
    names=['Scott Goodmanson','Colby Harder','Motion','B.J.']
    assert named_votes(block,names) == [{'person_name':'Scott Goodmanson','vote':'No','source_quote':'Mayor Goodmanson opposed'}]
    block['after_outcome'] = 'OPPOSED: Councillors Yacucha and Harder On the Main Motion as Amended:'
    block['source_block'] += '\n'+block['after_outcome']
    names=['Keith Yacucha','Colby Harder','Motion']
    assert {v['person_name'] for v in named_votes(block,names)} == {'Keith Yacucha','Colby Harder'}
    # An ambiguous surname cannot create a person or assign the wrong identity.
    assert named_votes(block,['Colby Harder','Someone Harder']) == []
    block['after_outcome']='Motion CARRIED. All members were present.'
    assert named_votes(block,names) == []


def test_only_explicit_source_choices_survive_not_model_attendance_or_unanimity():
    block={'after_outcome':'IN FAVOUR: Councillor Harder\nOPPOSED: Mayor Goodmanson\nABSTAINED: Councillor Yacucha','source_block':'IN FAVOUR: Councillor Harder\nOPPOSED: Mayor Goodmanson\nABSTAINED: Councillor Yacucha'}
    names=['Colby Harder','Scott Goodmanson','Keith Yacucha','Kimberley Guiry']
    assert {(v['person_name'],v['vote']) for v in named_votes(block,names)} == {('Colby Harder','Yes'),('Scott Goodmanson','No'),('Keith Yacucha','Abstain')}
    block['source_block']='CARRIED UNANIMOUSLY. All members present.'
    assert named_votes(block,names)==[]
    assert named_votes(None,names)==[]


def test_next_agenda_item_discussion_cannot_supply_a_vote():
    text='9.2 Other business\nCouncillor Harder opposed this suggestion.'
    assert named_votes({'after_outcome':text,'source_block':text},['Colby Harder'])==[]


def test_identical_repeated_motions_with_different_dissent_are_ambiguous():
    text='THAT Council receive the report for information.'
    template='**MOVED BY: GUIRY**\n**SECONDED: HARDER**\n'+text+'\n**Motion CARRIED.**\n'
    minutes=template+'Mayor Goodmanson opposed.\n'+template+'Councillor Harder opposed.\n'
    assert match_minutes_motion(text,minutes) is None


def test_compatible_outcome_families_retain_precise_official_wording():
    from pipeline.ingestion.vote_evidence import outcome_family
    assert outcome_family('CARRIED')==outcome_family('CARRIED UNANIMOUSLY')
    assert outcome_family('DEFEATED')==outcome_family('NOT CARRIED')
    assert outcome_family('CARRIED')!=outcome_family('DEFEATED')


def test_a_different_bylaw_number_or_negation_is_not_source_proof():
    source='**MOVED BY: GUIRY**\n**SECONDED: HARDER**\nTHAT Council adopt Bylaw No. 2270.\n**Motion CARRIED.**\nMayor Goodmanson opposed.'
    assert match_minutes_motion('THAT Council adopt Bylaw No. 2275.',source) is None
    assert match_minutes_motion('THAT Council not adopt Bylaw No. 2270.',source) is None


def test_indented_pdf_motion_headers_do_not_match_their_own_start_twice():
    text='              MOVED BY YACUCHA\n             SECONDED: GUIRY\n             THAT Council adopt Bylaw No. 2170.\n                         Motion CARRIED.\n             OPPOSED: Councillor Morley\n'
    match=match_minutes_motion('THAT Council adopt Bylaw No. 2170.',text)
    assert match['result']=='CARRIED'
    assert named_votes(match,['Mark Morley'])==[{'person_name':'Mark Morley','vote':'No','source_quote':'OPPOSED: Councillor Morley'}]


def test_verbatim_quote_can_anchor_supported_shortening_but_not_changed_identity():
    from pipeline.ingestion.vote_evidence import match_motion_record
    body='THAT Council receive the detailed annual financial report for information.'
    source='MOVED BY: GUIRY\nSECONDED: HARDER\n'+body+'\nMotion CARRIED.'
    record={'motion_text':'THAT Council receive the annual financial report for information.','motion_source_quote':body}
    assert match_motion_record(record,source)['anchor_method']=='verbatim_quote_exact_identity'
    record['motion_text']='THAT Council not receive the annual financial report for information.'
    assert match_motion_record(record,source) is None
    record={'motion_text':'THAT Council adopt Bylaw No. 2275.','motion_source_quote':'THAT Council adopt Bylaw No. 2270.'}
    assert match_motion_record(record,'MOVED BY: GUIRY\nSECONDED: HARDER\nTHAT Council adopt Bylaw No. 2270.\nMotion CARRIED.') is None
