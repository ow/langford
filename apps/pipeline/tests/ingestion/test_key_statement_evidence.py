"""Original-source content and private identity receipts have separate authority."""
from copy import deepcopy
import hashlib
import json
from unittest.mock import MagicMock

import pytest

from pipeline.ingestion.key_statement_evidence import (
    bind_key_statement, format_refinement_transcript, publish_key_statement,
)


@pytest.fixture
def speech(tmp_path):
    segments = [
        {'speaker': 'SPEAKER_09', 'start': 0., 'end': 5., 'text': 'I support the proposal.'},
        {'speaker': 'SPEAKER_09', 'start': 5., 'end': 10., 'text': 'The park needs more trees.'},
    ]
    path = tmp_path / 'transcript.json'
    path.write_text(json.dumps(segments))
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    # The persisted consolidated row has a real ID unrelated to source indexes.
    row = {'id': 900, 'meeting_id': 10, 'person_id': 9, 'speaker_name': 'Named Person',
           'start_time': 0., 'end_time': 10.,
           'text_content': 'I support the proposal. The park needs more trees.'}
    context = {'status': 'available', 'meeting_id': 10, 'source_sha256': source_hash,
               'segments': segments, 'stored_segments': [row],
               'people': [{'id': 9, 'name': 'Named Person'}], 'identity_receipts': [],
               '_transcript_path': str(path)}
    statement = {'speaker': 'A Model Guess', 'statement_type': 'proposal',
                 'evidence_kind': 'transcript', 'transcript_source_sha256': source_hash,
                 'source_segment_indexes': [1], 'source_quote': 'The park needs more trees.',
                 'statement_text': 'The model embellished this summary.'}
    return statement, context


@pytest.mark.parametrize('raw_label,public_label', [
    ('SPEAKER_09', 'SPEAKER_09'), ('Named Person', 'Unidentified speaker'),
    ('Mayor Named Person', 'Unidentified speaker'), ('Chair', 'Unidentified speaker'),
])
def test_original_index_maps_to_consolidated_row_without_promoting_legacy_name(speech, raw_label, public_label):
    statement, context = speech
    for segment in context['segments']:
        segment['speaker'] = raw_label
    supported = bind_key_statement(statement, context)
    assert supported['status'] == 'source_supported'
    assert supported['data'] == {
        'person_id': None, 'speaker_name': public_label, 'statement_type': 'proposal',
        'statement_text': 'The park needs more trees.', 'context': None,
        'source_segment_ids': [900], 'start_time': 5.,
    }
    assert supported['evidence']['transcript_source_sha256'] == context['source_sha256']
    assert supported['evidence']['source_segment_indexes'] == [1]
    assert supported['source_binding']['raw_segments'][0]['speaker'] == raw_label


@pytest.mark.parametrize('change', ['other_source', 'reverted', 'changed_row', 'duplicate_name', 'valid'])
def test_named_statement_requires_current_source_and_row_bound_private_admission(speech, change):
    statement, context = speech
    row = context['stored_segments'][0]
    receipt = {'id': 'receipt-1', 'status': 'applied', 'reverted_at': None,
               'segment_id': 900, 'meeting_id': 10, 'person_id': 9,
               'source_run': {'meeting_id': 10, 'transcript_sha256': context['source_sha256']},
               'after_row': deepcopy(row), 'validator_sha256': 'a'*64, 'input_sha256': 'b'*64}
    context['identity_receipts'] = [receipt]
    if change == 'other_source': receipt['source_run']['transcript_sha256'] = 'c'*64
    if change == 'reverted': receipt.update(status='reverted', reverted_at='2026-10-19')
    if change == 'changed_row': row['end_time'] = 11.
    if change == 'duplicate_name': context['people'].append({'id': 99, 'name': 'Named Person'})
    result = bind_key_statement(statement, context)
    assert result['status'] == 'source_supported'
    assert result['data']['person_id'] == (9 if change == 'valid' else None)
    assert result['evidence']['identity_receipt_sha256s'] if change == 'valid' else not result['evidence']['identity_receipt_sha256s']


@pytest.mark.parametrize('change', ['wrong_hash', 'unsupported_quote', 'truncated_word', 'wrong_index', 'ambiguous_db_tuple', 'altered_persisted_text'])
def test_changed_or_ambiguous_source_cannot_publish_a_statement(speech, change):
    statement, context = speech
    if change == 'wrong_hash': statement['transcript_source_sha256'] = 'd'*64
    if change == 'unsupported_quote': statement['source_quote'] = 'The taxes should be abolished.'
    if change == 'truncated_word': statement['source_quote'] = 'The park needs more tree'
    if change == 'wrong_index': statement['source_segment_indexes'] = [0]
    if change == 'ambiguous_db_tuple': context['stored_segments'].append({**context['stored_segments'][0], 'id': 901})
    if change == 'altered_persisted_text': context['stored_segments'][0]['text_content'] = 'A completely different speech.'
    assert bind_key_statement(statement, context)['status'] == 'held'


def test_prompt_retains_original_indexes_measured_times_and_source_hash(speech):
    _, context = speech
    prompt = format_refinement_transcript(context['segments'], context['source_sha256'])
    assert f"TRANSCRIPT_SOURCE_SHA256={context['source_sha256']}" in prompt
    assert '[source_index=1; start=5.0; end=10.0] SPEAKER_09: The park needs more trees.' in prompt
    context['segments'][1].pop('start')
    assert 'source_index=1; start=unknown; end=unknown' in format_refinement_transcript(context['segments'], context['source_sha256'])



def test_publication_binds_source_tuples_and_runtime_in_one_atomic_rpc(speech):
    statement, context = speech
    supported = bind_key_statement(statement, context)
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = {
        'status': 'published', 'statement_id': 12, 'proof_digest': 'c'*64,
    }
    assert publish_key_statement(client, 10, 20, supported, context)['statement_id'] == 12
    function, args = client.rpc.call_args.args
    assert function == 'publish_source_bound_key_statement'
    encoded = args['p_input_canonical_json']
    assert args['p_input_sha256'] == hashlib.sha256(encoded.encode()).hexdigest()
    payload = json.loads(encoded)
    assert payload['raw_segments'] == [{'source_index': 1, 'segment_id': 900,
                                      'start': 5., 'end': 10., 'speaker': 'SPEAKER_09',
                                      'text': 'The park needs more trees.'}]
    assert payload['expected_segments'] == context['stored_segments']
    assert len(payload['validator_sha256']) == 64
    assert not client.table.called
    client.rpc.return_value.execute.return_value.data = {'status': 'conflict'}
    with pytest.raises(RuntimeError, match='publication held'):
        publish_key_statement(client, 10, 20, supported, context)
