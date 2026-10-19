"""Bounded producer lifecycle; identity rules belong to transcript_links tests."""
import json
import wave
from unittest.mock import patch

from pipeline.ingestion.transcript_identity_producer import DirectIntroductionProducer


def test_later_introductions_continue_and_successful_paid_responses_are_reused(tmp_path):
    recording = tmp_path / 'recording.wav'
    with wave.open(str(recording), 'wb') as audio:
        audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        audio.writeframes(b''.join((i+1).to_bytes(2, 'little', signed=True) * 16000 for i in range(15)))
    transcript = tmp_path / 'recording.json'
    transcript.write_text(json.dumps({'segments': [
        {'start': i*2, 'end': i*2+1, 'text': 'My name is Alex Example.'} for i in range(5)]}))
    official = tmp_path / 'minutes.html'
    official.write_text('<html><body>Alex Example spoke to Council.</body></html>')
    producer = DirectIntroductionProducer()
    args = dict(folder=tmp_path, meeting={'id': 7, 'video_url': 'https://vimeo.com/123'},
                people=[{'id': 9, 'name': 'Alex Example'}], transcript=transcript,
                recording=recording, official_source={'path': official, 'format': 'html'},
                recording_id='vimeo:123')
    with patch.object(producer, '_lineage', return_value={'test_model_asset_sha256': 'a'*64}), \
         patch.object(producer, '_transcribe', return_value={
             'model': 'test-independent', 'prompt': None, 'known_speaker_references': None,
             'response': {'text': 'My name is Alex Example.'}}) as asr, \
         patch.object(producer, '_diarize', return_value={
             'raw_speakers_detected': 1, 'speaker_centroids': {'SPEAKER_00': [1.]*192},
             'raw_segments': [{'start': 0, 'end': 1, 'speaker': 'SPEAKER_00'}]}) as diarizer:
        first = producer.produce(**args)
        assert (len(first['requests']), first['pending'], first['clips_processed']) == (4, 1, 4)
        second = producer.produce(**args)
        assert (len(second['requests']), second['pending'], second['clips_processed']) == (5, 0, 1)
        third = producer.produce(**args)
        assert (len(third['requests']), third['pending'], third['clips_processed']) == (5, 0, 0)
        assert asr.call_count == diarizer.call_count == 5


def test_reconcile_real_generated_request_uses_full_row_rpc_and_holds_missing_raw_segments(tmp_path):
    from unittest.mock import MagicMock
    from pipeline.ingestion.ingester import MeetingIngester
    from pipeline.ingestion import transcript_links as verifier
    folder = tmp_path / 'archive' / 'langford' / 'meeting'
    (folder / 'Audio').mkdir(parents=True)
    recording = folder / 'Audio' / 'recording.wav'
    with wave.open(str(recording), 'wb') as audio:
        audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        audio.writeframes(b'\0\0' * 16000)
    transcript = recording.with_suffix('.json')
    transcript.write_text(json.dumps({'segments': [{'start': 0, 'end': 1, 'text': 'My name is Alex Example.'}]}))
    official = folder / 'minutes.html'
    official.write_text('<html><body>Langford Council. Alex Example addressed Council.</body></html>')
    person = {'id': 9, 'name': 'Alex Example'}
    meeting = {'id': 7, 'archive_path': 'archive/langford/meeting', 'meeting_date': '2026-10-18',
               'video_url': 'https://vimeo.com/123'}
    row = {'id': 1, 'meeting_id': 7, 'person_id': None, 'speaker_name': 'SPEAKER_00',
           'start_time': 0, 'end_time': 1, 'text_content': 'My name is Alex Example.',
           'is_verified': False, 'updated_at': '2026-10-18T00:00:00+00:00', 'speaker_role': None,
           'agenda_item_id': None, 'motion_id': None, 'is_procedural': False,
           'attribution_source': 'UNIDENTIFIED_DIARIZATION', 'sentiment_score': None,
           'text_search': None, 'created_at': '2026-10-18T00:00:00+00:00'}
    client = MagicMock()
    tables = {}
    for name, data in [('meetings', [meeting]), ('people', [person]), ('transcript_segments', [row])]:
        table = MagicMock()
        for operation in ['select', 'eq', 'order', 'range']:
            getattr(table, operation).return_value = table
        table.execute.return_value.data = data
        tables[name] = table
    client.table.side_effect = tables.__getitem__
    client.rpc.return_value.execute.return_value.data = {'status': 'applied', 'evidence_id': 'private-id'}
    ingester = MeetingIngester.__new__(MeetingIngester)
    ingester.supabase, ingester.municipality_id = client, 1
    source = {'source_file': str(official.relative_to(tmp_path)), 'source_format': 'official_html',
              'source_url': 'https://pub-langford.escribemeetings.com/minutes', 'source_header': 'Langford Council',
              'local_date': '2026-10-18', 'source_sha256': 'a'*64}
    with patch('pipeline.ingestion.ingester.BASE_DIR', tmp_path), \
         patch('pipeline.ingestion.official_ballots.load_official_minutes', return_value=source), \
         patch.object(DirectIntroductionProducer, '_lineage', return_value={'model': 'test'}), \
         patch.object(DirectIntroductionProducer, '_transcribe', return_value={
             'model': 'test-independent', 'prompt': None, 'known_speaker_references': None,
             'response': {'text': 'My name is Alex Example.'}}), \
         patch.object(DirectIntroductionProducer, '_diarize', return_value={
             'raw_speakers_detected': 1, 'speaker_centroids': {'SPEAKER_00': [1.]*192},
             'raw_segments': [{'start': 0, 'end': 1, 'speaker': 'SPEAKER_00'}]}):
        result = ingester.reconcile_transcript_identities(str(folder), 7)
        assert result['applied'] == 1 and result['pending'] == 0
        name, payload = client.rpc.call_args.args
        assert name == 'apply_transcript_identity_evidence'
        assert payload['p_expected'] == row
        assert payload['p_person_id'] == 9
        assert payload['p_validator_sha256'] == verifier.VALIDATOR_SHA256
        assert json.loads(payload['p_input_canonical_json'])['expected_row'] == row
        assert not tables['transcript_segments'].delete.called
        assert not tables['transcript_segments'].insert.called
        client.rpc.reset_mock()
        source['source_url'] = 'http://pub-langford.escribemeetings.com/minutes'
        held = ingester.reconcile_transcript_identities(str(folder), 7)
        assert held['status'] == 'held' and held['reason'] == 'official_source_url_not_validated'
        assert not client.rpc.called
        source['source_url'] = 'https://pub-langford.escribemeetings.com/minutes'
        transcript.write_text('{}')
        client.rpc.reset_mock()
        held = ingester.reconcile_transcript_identities(str(folder), 7)
        assert held['status'] == 'held' and held['reason'] == 'raw_segment_source_required'
        assert not client.rpc.called


def test_resolving_official_initial_name_ambiguity_reuses_independent_audio_work(tmp_path):
    recording = tmp_path / 'recording.wav'
    with wave.open(str(recording), 'wb') as audio:
        audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        audio.writeframes(b'\0\0' * 16000)
    transcript = tmp_path / 'recording.json'
    transcript.write_text(json.dumps({'segments': [
        {'start': 0, 'end': 1, 'text': 'My name is Alex Example.'}]}))
    official = tmp_path / 'minutes.html'
    official.write_text('<html><body>A. Example spoke to Council.</body></html>')
    producer = DirectIntroductionProducer()
    args = dict(folder=tmp_path, meeting={'id': 7, 'video_url': 'https://vimeo.com/123'},
                transcript=transcript, recording=recording,
                official_source={'path': official, 'format': 'html'}, recording_id='vimeo:123')
    alex, aria = {'id': 9, 'name': 'Alex Example'}, {'id': 10, 'name': 'Aria Example'}
    with patch.object(producer, '_lineage', return_value={'asr_model': 'test', 'senko_asset_sha256': 'a'*64}), \
         patch.object(producer, '_transcribe', return_value={
             'model': 'test-independent', 'prompt': None, 'known_speaker_references': None,
             'response': {'text': 'My name is Alex Example.'}}) as asr, \
         patch.object(producer, '_diarize', return_value={
             'raw_speakers_detected': 1, 'speaker_centroids': {'SPEAKER_00': [1.]*192},
             'raw_segments': [{'start': 0, 'end': 1, 'speaker': 'SPEAKER_00'}]}) as diarizer:
        held = producer.produce(**args, people=[alex, aria])
        assert len(held['requests']) == 0 and held['held'] == 1
        admitted = producer.produce(**args, people=[alex])
        assert admitted['input_key'] != held['input_key']
        assert len(admitted['requests']) == 1 and admitted['held'] == 0
        assert asr.call_count == diarizer.call_count == 1
