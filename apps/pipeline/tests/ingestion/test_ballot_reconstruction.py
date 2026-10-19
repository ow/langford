import pytest
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


def test_coordinated_subject_cannot_drop_another_or_unknown_member():
    events,held=physical_presence_events('Councillors Harder and Guiry left the meeting at 8:00 pm.',PEOPLE)
    assert [(e['person_id'],e['state']) for e in events]==[(21,'absent'),(23,'absent')]
    assert held==[]
    events,held=physical_presence_events('Councillors Unknown and Harder left the meeting at 8:00 pm.',PEOPLE)
    assert events==[] and held
    events,held=physical_presence_events('CouncillorHarder left the meeting at 8:00 pm.',PEOPLE)
    assert events==[]
    assert held


def test_present_header_arrival_annotation_is_not_chronological_presence():
    _,held=validate_roster_entries('Mayor S. Goodmanson; Councillor C. Harder - arrived 7:08pm',PEOPLE)
    assert held


def test_declared_conflict_modifier_preserves_actual_departure_until_return():
    # March 15, 2021 native minutes: the intervening board/conflict clause must
    # not hide Seaton's physical exit or include him in the intervening vote.
    people=[{'id':135,'name':'Lanny Seaton'},{'id':137,'name':'Roger Wade'}]
    text=('Councillor Seaton, as a Member of the Seniors Low-Cost Housing Board, '
          'declared a conflict with respect to Bylaw No. 1958 and left the meeting at 7:30 pm.\n'
          'First vote.\nCouncillor Seaton returned to the meeting at 7:32 pm.\nSecond vote.')
    events,held=physical_presence_events(text,people)
    assert held==[]
    assert voters_before_vote({135,137},events,text.index('First vote'))[0]=={137}
    assert voters_before_vote({135,137},events,text.index('Second vote'))[0]=={135,137}
    # Reporting an absent third person's departure does not change the speaker.
    events,held=physical_presence_events('Councillor Seaton stated that the applicant left the meeting at 7:30 pm.',people)
    assert events==[] and held


PRESENCE_PEOPLE=PEOPLE+[{'id':133,'name':'Denise Blackwell'},{'id':134,'name':'Matt Sahlstrom'},{'id':135,'name':'Lanny Seaton'},{'id':136,'name':'Norma Stewart'},{'id':137,'name':'Roger Wade'},{'id':143,'name':'Stew Young'},{'id':200,'name':'Chris Foxall'},{'id':201,'name':'Robin Plomp'},{'id':202,'name':'Jacqui Whiteway'}]


@pytest.mark.parametrize('text,expected', [
    ('\n\n\nCouncillors Harder and Guiry left the meeting at 8:00 pm.', [(21,'absent'),(23,'absent')]),
    ('Mayor Goodmanson declared a conflict\nof interest due to family ownership and left the meeting at 7:08 pm.', [(1,'absent')]),
    ('5:34 pm Councillor Stewart left the meeting after declaring a conflict of interest as the properties discussed\nin 7a) and 7b) are in proximity to her own property.', [(136,'absent')]),
    ('Councillor Guiry left the meeting at 8:18 pm citing a possible pecuniary conflict of\ninterest.', [(23,'absent')]),
    ('Committee Member Whiteway remained out of the room due to a perceived conflict of\ninterest regarding Reimagine West Shore.', [(202,'absent')]),
    ('At 5:40 pm Councillor Seaton left the meeting due to a conflict of interest.', [(135,'absent')]),
    ('Councillor Guiry left the meeting at 8:18 pm citing a possible pecuniary conflict of interest.', [(23,'absent')]),
    ('Mayor Goodmanson declared a perceived pecuniary conflict of interest as a result of family ownership of an adjacent property and left the meeting at 7:08 pm.', [(1,'absent')]),
    ('Councillor Harder excused herself due to a previously declared perceived conflict of interest pertaining to the application at 2795 and 2799 Scafe Road due to the proximity to her personal residence, and her involvement on her strata board and left the meeting at 8:10 pm.', [(21,'absent')]),
    ('Councillor Wade declared a conflict of interest (he works for the company) and left the meeting at this point.', [(137,'absent')]),
    ('Councillor Harder at 8:01 p.m. left the meeting due to a perceived conflict of interest with item 11.1.', [(21,'absent')]),
    ('Councillor Stewart and Councillor Wade left the meeting at 5:41 pm due to conflicts of interest.', [(136,'absent'),(137,'absent')]),
    ('CouncillorSzpak and CouncillorSahlstrom left the meeting at 6:45 pm. due to a perceived conflict with Item 8.1.1.', [(35,'absent'),(134,'absent')]),
    ('At 5:05pm Mayor Young and Councillor Blackwell arrived at the meeting.', [(143,'present'),(133,'present')]),
    ('Committee members Foxall, Plomp, and Whiteway left the meeting at 9:53pm', [(200,'absent'),(201,'absent'),(202,'absent')]),
    ('Committee Member Plomp excused himself due to a previously declared conflict of interest pertaining to Open Gate Church and left the meeting at 9:39 pm.', [(201,'absent')]),
    ('Committee Member Whiteway remained out of the room due to a perceived conflict of interest regarding Reimagine West Shore.', [(202,'absent')]),
    ('OPPOSED: Councillor Yacucha\n\nCouncillor Harder returned to the meeting at 8:55 pm.', [(21,'present')]),
    ('The Chair returned to questions and comments from the Committee.', []),
    ('MOVED BY: WADE\nSECONDED: SAHLSTROM\nThat Council fund the Millstream Interchange Dual Left Turnlane project.', []),
    ('Councillor Sahlstrom asked what prevents us from having a left-hand turn into the development.', []),
    ('Mayor Young called for presentations.\n\nA resident asked for a left off of Millstream Road.', []),
    ('PRESENT: Councillor K. Guiry\n\nATTENDING: D. Kiedyk, Chief Administrative Officer - Departed at 7:18 pm\n1. CALL TO ORDER', []),
])
def test_native_presence_episodes_change_only_the_documented_voters(text,expected):
    # Actual clauses from the 27-source/63-held-event audit exercise the public
    # attendance replay owner; expectations come from original minutes.
    people=PRESENCE_PEOPLE+[{'id':35,'name':'Lillian Szpak'},{'id':34,'name':'Keith Yacucha'}]
    events,held=physical_presence_events(text,people)
    assert [(e['person_id'],e['state'])for e in events]==expected
    assert held==[]


@pytest.mark.parametrize('text', [
    'Councillor Harder declared a conflict of interest.',
    'Councillor Harder excused herself due to a conflict of interest.',
    'Mayor Goodmanson stated that the applicant left the meeting.',
    'Councillor Harder stated that Mayor Goodmanson left the meeting.',
    'Councillor Unknown and Councillor Harder left the meeting at 8:00 pm.',
    'Councillor Harder and Councillor Unknown returned to the meeting at 8:01 pm.',
    'Councillor Harder declared a conflict of interest and reported that an applicant left the meeting.',
    'Councillor Harder declared a conflict of interest with Councillor Unknown and left the meeting.',
    'Councillor Z. Harder left the room at 8:01 pm.',
])
def test_unsupported_subject_or_excusal_cannot_manufacture_a_physical_event(text):
    events,held=physical_presence_events(text,PRESENCE_PEOPLE)
    assert events==[] and held


def test_first_remained_out_observation_does_not_invent_earlier_presence_or_exit():
    text='Earlier vote.\nCommittee Member Whiteway remained out of the room due to a perceived conflict of interest.\nLater vote.'
    events,held=physical_presence_events(text,PRESENCE_PEOPLE)
    assert held==[] and len(events)==1
    initial={21,202}
    assert voters_before_vote(initial,events,0)[0] is None
    assert voters_before_vote(initial,events,events[0]['offset'])[0]=={21}
    assert voters_before_vote(initial,events,len(text))[0]=={21}
    prior='Committee Member Whiteway left the room at 8:00 pm.\n'+text
    events,held=physical_presence_events(prior,PRESENCE_PEOPLE)
    assert not held
    assert voters_before_vote(initial,events,0)[0]==initial
    assert voters_before_vote(initial,events,len(prior))[0]=={21}


@pytest.mark.parametrize('later', [
    '\n\nCouncillor Guiry declared a conflict of interest.',
    ' Councillor Guiry declared a conflict of interest.',
    ' Kimberley Guiry declared a conflict of interest.',
    ' Councillor Unknown declared a conflict of interest.',
])
def test_own_exit_reason_does_not_consume_a_later_declaration(later):
    text='Councillor Harder left the meeting due to a conflict of\ninterest.'+later
    events,held=physical_presence_events(text,PRESENCE_PEOPLE)
    assert [(e['person_id'],e['state'])for e in events]==[(21,'absent')]
    assert held and all(h['offset']>text.index(later.strip())for h in held)
