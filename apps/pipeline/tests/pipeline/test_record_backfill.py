"""Contracts for source-backed backfill; unidentified or ambiguous evidence stays unknown."""
from pipeline.backfill.records import explicit_vote_blocks, match_motion, named_people, voice_consensus


def test_named_dissent_binds_to_the_preceding_motion_not_next_item():
    minutes = '''**MOVED BY: WAGNER**
**SECONDED: HARDER**
> *THAT Council give Animal Responsibility Bylaw 2239 first, second and third readings.*
**Motion CARRIED.**
OPPOSED: Councillor Yacucha 9.3 BYLAW NO. 2248
**MOVED BY: HARDER**
**SECONDED: WAGNER**
> *THAT Council approve the following very different zoning application.*
**Motion CARRIED.**
'''
    blocks = list(explicit_vote_blocks(minutes))
    assert len(blocks) == 1
    assert blocks[0]['choices'][0][:2] == ('Councillor Yacucha', 'No')
    assert match_motion(blocks[0]['text'], [
        {'id': 10, 'text_content': 'THAT Council give Animal Responsibility Bylaw 2239 first, second and third readings.'},
        {'id': 11, 'text_content': 'THAT Council approve the following very different zoning application.'},
    ]) == 10
    assert named_people(blocks[0]['choices'][0][0], [{'id': 34, 'name': 'Keith Yacucha'}]) == [34]


def test_carried_does_not_manufacture_individual_yes_votes():
    assert list(explicit_vote_blocks('**MOVED BY: HARDER**\n**SECONDED: WAGNER**\nTHAT Council approve the agenda.\n**Motion CARRIED.**')) == []


def test_ambiguous_motion_or_person_is_not_assigned():
    text = 'THAT Council approve the revised application as presented to Council.'
    assert match_motion(text, [{'id': 1, 'text_content': text}, {'id': 2, 'text_content': text}]) is None
    assert named_people('Councillor Smith', [{'id': 1, 'name': 'Jane Smith'}, {'id': 2, 'name': 'John Smith'}]) == []
    assert named_people('Councillors Yacucha and Unknown', [{'id': 34, 'name': 'Keith Yacucha'}]) == []


def test_voice_identity_requires_distinct_recordings_and_excludes_the_target():
    vector = [1.] + [0.] * 191
    other = [0., 1.] + [0.] * 190
    same_recording = [{'person_id': 21, 'recording': 'one', 'vector': vector} for _ in range(10)]
    assert voice_consensus(vector, same_recording) is None
    anchors = [{'person_id': 21, 'recording': name, 'vector': vector} for name in ['one', 'two', 'three']]
    anchors += [{'person_id': 1, 'recording': 'other', 'vector': other}]
    assert voice_consensus(vector, anchors)['person_id'] == 21
    assert voice_consensus(vector, anchors, exclude_recording='one') is None


def test_competing_identity_prevents_voice_attribution():
    vector = [1.] + [0.] * 191
    anchors = [{'person_id': 21, 'recording': str(i), 'vector': vector} for i in range(3)]
    anchors += [{'person_id': 23, 'recording': 'competing', 'vector': vector}]
    assert voice_consensus(vector, anchors) is None
