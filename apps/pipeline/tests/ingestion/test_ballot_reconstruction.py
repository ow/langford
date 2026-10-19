from pipeline.ingestion.ballot_reconstruction import validate_roster_entries,physical_presence_events,voters_before_vote

PEOPLE=[{'id':21,'name':'Colby Harder'},{'id':23,'name':'Kimberley Guiry'},{'id':1,'name':'Scott Goodmanson'}]


def test_every_present_roster_entry_must_resolve_including_unprefixed_names():
    people,unknown=validate_roster_entries('Mayor S. Goodmanson; Councillor C. Harder; K. Guiry',PEOPLE)
    assert {p['id'] for p in people}=={1,21,23}
    assert unknown==[]
    _,unknown=validate_roster_entries('Mayor S. Goodmanson; Colby Harder; Bob Smith',PEOPLE)
    assert set(unknown)=={'bob','smith'}


def test_bare_names_and_line_wrapped_physical_events_preserve_source_order():
    text='Colby Harder left the room at 8:10 pm.\nCouncillor K. Guiry\nreturned to the meeting at 8:12 pm.\nScott Goodmanson lost\nconnection.'
    events,held=physical_presence_events(text,PEOPLE)
    assert [(e['person_id'],e['state']) for e in events]==[(21,'absent'),(23,'present'),(1,'absent')]
    assert [e['offset'] for e in events]==sorted(e['offset'] for e in events)
    assert held==[]


def test_abstract_departures_and_unscoped_recusals_are_not_physical_events():
    text='Councillor Harder returned to discussion.\nColby Harder left the decision to staff.\nK. Guiry excused herself.\nScott Goodmanson declared a conflict of interest.'
    events,held=physical_presence_events(text,PEOPLE)
    assert events==[]
    assert len(held)==2


def test_wrong_initials_and_unknown_targets_are_held_instead_of_assigning_a_voter():
    events,held=physical_presence_events('S. Guiry stepped out.\nColby Harder departed.',PEOPLE)
    assert events==[]
    assert len(held)==2


def test_motion_withdrawal_is_not_a_departure_and_compound_return_is_not_hidden():
    text='Councillor Harder left the meeting at 7:59 pm and returned at 8:01p.m.\nCouncillor Goodmanson withdrew his motion.'
    events,held=physical_presence_events(text,PEOPLE)
    assert [(e['person_id'],e['state']) for e in events]==[(21,'absent'),(21,'present')]
    assert held==[]
    present,_=voters_before_vote({1,21,23},events,len(text))
    assert present=={1,21,23}


def test_late_arrival_listed_present_does_not_vote_before_the_join():
    text='First vote here.\nCouncillor Harder joined the meeting at 7:08 pm.\nSecond vote here.'
    events,held=physical_presence_events(text,PEOPLE)
    assert held==[]
    before,adjustments=voters_before_vote({1,21,23},events,text.index('First vote'))
    assert before=={1,23}
    assert adjustments[0]['person_id']==21
    after,_=voters_before_vote({1,21,23},events,text.index('Second vote'))
    assert after=={1,21,23}


def test_first_return_without_departure_does_not_prove_earlier_presence():
    text='First vote.\nColby Harder returned to the room at 8:01 pm.\nSecond vote.'
    events,held=physical_presence_events(text,PEOPLE)
    assert voters_before_vote({1,21,23},events,0)[0] is None
    assert voters_before_vote({1,21,23},events,len(text))[0]=={1,21,23}


def test_collective_subject_and_ocr_merged_role_cannot_drop_another_member():
    events,held=physical_presence_events('Councillors Harder and Guiry left the meeting at 8:00 pm.',PEOPLE)
    assert events==[]
    assert held[0]['reason']=='collective_presence_subject_needs_parse'
    events,held=physical_presence_events('CouncillorHarder left the meeting at 8:00 pm.',PEOPLE)
    assert events==[]
    assert held


def test_present_header_arrival_annotation_is_not_chronological_presence():
    _,held=validate_roster_entries('Mayor S. Goodmanson; Councillor C. Harder - arrived 7:08pm',PEOPLE)
    assert held
