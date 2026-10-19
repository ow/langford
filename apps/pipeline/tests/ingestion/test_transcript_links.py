"""Source admission boundary: real artifact bytes, no supplied admission fixtures."""
import copy
import hashlib
import json
import math
import wave
from pathlib import Path

import pytest

from pipeline.ingestion.transcript_links import admit_identity, temporal_evidence, verify_transcript_link


def artifact(path, data):
    if isinstance(data, (dict, list)):
        data = json.dumps(data).encode()
    path.write_bytes(data)
    return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest()}


@pytest.fixture
def source(tmp_path):
    # The original recording is the clip itself: offset zero has independently
    # identical PCM bytes, rather than a mocked extraction callback.
    audio = tmp_path / 'original.wav'
    import struct
    with wave.open(str(audio), 'wb') as handle:
        handle.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        handle.writeframes(b''.join(struct.pack('<h', int(5000*math.sin(i*.17))) for i in range(16000*4)))
    recording = {'path':str(audio), 'sha256':hashlib.sha256(audio.read_bytes()).hexdigest()}
    segment = {'start':0., 'end':4., 'text':"I'm Avery Stone. I support the proposal."}
    transcript = artifact(tmp_path/'transcript.json', {'segments':[segment]})
    diarization = artifact(tmp_path/'turns.json', {'clip_sha256':recording['sha256'], 'model':'synthetic-boundary-fixture',
        'result':{'raw_speakers_detected':1, 'speaker_centroids':{'A':[1.]+[0.]*191},
                  'raw_segments':[{'start':0., 'end':4., 'speaker':'A'}]}})
    asr = artifact(tmp_path/'asr.json', {'clip_sha256':recording['sha256'], 'model':'synthetic-boundary-fixture',
        'prompt':None, 'known_speaker_references':None, 'response':{'text':segment['text']}})
    official = artifact(tmp_path/'minutes.html', b'<p>Public participation: A. Stone</p>')
    run = {'meeting_id':7, 'recording_id':'vimeo:123456789', 'recording_sha256':recording['sha256'],
           'transcript_sha256':transcript['sha256'], 'diarization_run_sha256':diarization['sha256']}
    request = {'person_id':10, 'person_name':'Avery Stone', 'mode':'direct_source_self_introduction',
        'recording':recording, 'recording_url':'https://vimeo.com/123456789', 'recording_id':run['recording_id'],
        'clip':recording, 'clip_start':0., 'clip_end':4., 'transcript':transcript,
        'diarization':diarization, 'independent_asr':asr, 'official_name_source':official,
        'official_format':'html', 'source_run':run, 'target_speaker_label':'A'}
    row = {'id':99, 'meeting_id':7, 'start_time':0., 'end_time':4., 'text_content':segment['text'],
           'person_id':None, 'speaker_name':None, 'is_verified':False, 'topic':'preserve me', 'text_search':"'averi':2"}
    return request, [{'id':10, 'name':'Avery Stone'}], row, segment


def test_direct_admission_plans_full_row_cas_without_mutating_content(source):
    request, people, row, segment = source
    before = copy.deepcopy(row)
    admission = admit_identity(request, people)
    assert admission['status']=='identity_admitted', admission
    candidate = verify_transcript_link(row, segment, admission, [{'start':0.,'end':4.,'speaker':'A'}], source_run=request['source_run'])
    assert candidate['status']=='link_candidate', candidate
    assert candidate['operation']=='fill_null'
    assert candidate['expected_row']==before and row==before
    encoded = candidate['input_canonical_json']
    assert hashlib.sha256(encoded.encode()).hexdigest()==candidate['input_sha256']
    assert json.loads(encoded)['expected_row']['topic']=='preserve me'


def test_duplicate_canonical_full_name_never_selects_requested_id(source):
    request, people, _, _ = source
    request['official_name_source'] = artifact(Path(request['official_name_source']['path']), b'<p>Avery Stone</p>')
    result = admit_identity(request, people+[{'id':11,'name':'Avery Stone'}])
    assert result=={'status':'identity_held','reason':'ambiguous_canonical_full_name'}


@pytest.mark.parametrize('text,reason', [('Avery Stone. Please begin.', 'literal_first_person_self_introduction_required')])
def test_chair_name_call_is_not_self_identification(source, text, reason):
    request, people, _, _ = source
    path = Path(request['independent_asr']['path'])
    value = json.loads(path.read_bytes()); value['response']['text']=text
    request['independent_asr']=artifact(path,value)
    assert admit_identity(request,people)['reason']==reason


def test_multiple_competitor_voices_are_unioned_without_rounding():
    turns=[{'start':0.,'end':10.,'speaker':'A'}, {'start':0.,'end':.6,'speaker':'B'},
           {'start':.6,'end':1.2,'speaker':'C'}, {'start':0.,'end':.6,'speaker':'B'}]
    assert temporal_evidence(0.,10.,'A',turns)['status']=='mixed_or_insufficient_temporal_support'
    assert temporal_evidence(0.,10.,'A',turns)['competing_fraction']==pytest.approx(.12)


def test_caller_tuple_and_turns_cannot_override_hashed_original(source):
    request, people, row, segment = source
    admission=admit_identity(request,people)
    assert admission['status']=='identity_admitted', admission
    row['text_content']='invented'; segment['text']='invented'
    result=verify_transcript_link(row,segment,admission,[{'start':0.,'end':4.,'speaker':'A'}],source_run=request['source_run'])
    assert result['reason']=='original_transcript_occurrence_not_unique_or_missing'


def test_polite_greeting_still_requires_explicit_first_person(source):
    request, people, _, _ = source
    path=Path(request['independent_asr']['path'])
    value=json.loads(path.read_bytes());value['response']['text']='Hi there, my name is Avery Stone.'
    request['independent_asr']=artifact(path,value)
    assert admit_identity(request,people)['status']=='identity_admitted'


@pytest.mark.parametrize('change,reason', [
    ('verified','verified_row_preserved'),
    ('other_person','existing_other_person_requires_independent_correction_review'),
    ('turns','measured_diarization_intervals_changed'),
    ('run','source_recording_run_or_meeting_changed'),
])
def test_admitted_identity_does_not_bypass_row_and_measured_run_protections(source,change,reason):
    request,people,row,segment=source
    admission=admit_identity(request,people)
    assert admission['status']=='identity_admitted',admission
    turns=[{'start':0.,'end':4.,'speaker':'A'}]
    run=copy.deepcopy(request['source_run'])
    if change=='verified':row['is_verified']=True
    if change=='other_person':row['person_id']=11
    if change=='turns':turns.append({'start':0.,'end':4.,'speaker':'B'})
    if change=='run':run['meeting_id']=8
    assert verify_transcript_link(row,segment,admission,turns,source_run=run)['reason']==reason


def test_direct_source_player_identity_must_match_immutable_url(source):
    request,people,_,_=source
    request['recording_id']='vimeo:987654321'
    request['source_run']['recording_id']='vimeo:987654321'
    assert admit_identity(request,people)['reason']=='canonical_recording_provenance_mismatch'


def test_cross_recording_scores_cannot_replace_missing_model_calibration(source):
    request,people,_,_=source
    anchors=[]
    for index in range(3):
        anchor=copy.deepcopy(request)
        original=Path(anchor['recording']['path'])
        anchor['recording']=artifact(original.with_name(f'reference{index}.wav'),original.read_bytes()+b'JUNK'+bytes([index]))
        anchor['recording_id']=f'vimeo:{223456789+index}'
        anchor['recording_url']=f'https://vimeo.com/{223456789+index}'
        anchors.append(anchor)
    request['mode']='independent_recording_voice_propagation'
    request['anchors']=anchors
    # Even perfect fresh scores/three distinct player receipts are not a
    # calibrated positive/negative validation of cross-recording attribution.
    result=admit_identity(request,people)
    assert result=={'status':'identity_held','reason':'cross_recording_calibration_not_validated'}
