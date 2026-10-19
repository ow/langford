"""Measured word/turn proposals must conserve text without inventing names."""
from copy import deepcopy
import pytest

from pipeline.ingestion.word_turn_alignment import align_word_turns


PROVENANCE = {k: 'a'*64 for k in ('recording_sha256', 'transcript_sha256', 'token_source_sha256', 'diarization_sha256', 'tokenizer_sha256')}


def test_split_measured_words_preserves_source_and_applies_offsets_once():
    parent = {'id': 7, 'start': 100., 'end': 104., 'text': 'Hello there. Goodbye now.'}
    before = deepcopy(parent)
    tokens = [{'text': text, 'start': i+2., 'end': i+3.} for i,text in enumerate(['Hello', ' there.', ' Goodbye', ' now.'])]
    turns = [{'start':140.,'end':142.,'speaker':'A'}, {'start':142.,'end':144.,'speaker':'B'}]
    result = align_word_turns(parent,tokens,turns,provenance=PROVENANCE,token_offset_seconds=98.,diarization_offset_seconds=-40.)
    assert result['status']=='alignment_candidate'
    assert [(u['start'],u['end'],u['text'],u['speaker_label']) for u in result['utterances']]==[
        (100.,102.,'Hello there.','A'),(102.,104.,'Goodbye now.','B')]
    assert result['token_accounting']=={'input':4,'supported':4,'held':0,'conserved':True}
    assert parent==before and result['parent']==before
    assert all(u['identity_status']=='anonymous_only'for u in result['utterances'])


@pytest.mark.parametrize('first_voice_end', [.5, .95])
def test_subword_crossing_voice_change_is_held_as_whole_word(first_voice_end):
    tokens=[{'text':'Hel','start':0.,'end':.5},{'text':'lo','start':.5,'end':1.}, {'text':' there','start':2.,'end':3.}]
    result=align_word_turns({'start':0.,'end':3.,'text':'Hello there'},tokens,
        [{'start':0.,'end':first_voice_end,'speaker':'A'},{'start':first_voice_end,'end':3.,'speaker':'B'}],provenance=PROVENANCE)
    assert [u['token_indices']for u in result['utterances']]==[[2]]
    assert [h['token_indices']for h in result['held_words']]==[[0,1]]
    assert result['token_accounting']=={'input':3,'supported':1,'held':2,'conserved':True}


def test_word_with_three_competitors_does_not_use_only_runner_up():
    turns=[{'start':0.,'end':10.,'speaker':'A'}, {'start':0.,'end':.6,'speaker':'B'},
           {'start':.6,'end':1.2,'speaker':'C'}, {'start':1.2,'end':1.8,'speaker':'D'}]
    result=align_word_turns({'start':0.,'end':10.,'text':'hello'},[{'text':'hello','start':0.,'end':10.}],turns,provenance=PROVENANCE)
    assert result['utterances']==[]
    assert result['held_words'][0]['reason']=='mixed_or_insufficient_temporal_support'
    assert result['token_accounting']['held']==1


def test_changed_asr_is_new_version_proposal_never_an_old_text_split():
    parent={'id':8,'start':0.,'end':1.,'text':'Approve the old proposal.'}
    result=align_word_turns(parent,[{'text':'Reject the new proposal.','start':0.,'end':1.}],
        [{'start':0.,'end':1.,'speaker':'A'}],provenance=PROVENANCE)
    assert result['status']=='held_original_text_mismatch'
    assert result['parent']==parent and result['publication_eligible']is False
    assert result['token_accounting']['conserved']is True
    assert result['utterances'][0]['text']=='Reject the new proposal.'
    assert result['utterance_text_basis']=='new_version_token_evidence'


def test_source_text_binding_hold_cannot_be_merged_into_supported_utterance():
    tokens=[{'text':'one','start':0.,'end':1.},
            {'text':' two','start':1.,'end':2.,'source_hold_reason':'native_sentence_token_text_mismatch'},
            {'text':' three','start':2.,'end':3.}]
    result=align_word_turns({'start':0.,'end':3.,'text':'one two three'},tokens,
        [{'start':0.,'end':3.,'speaker':'A'}],provenance=PROVENANCE)
    assert [u['token_indices']for u in result['utterances']]==[[0],[2]]
    assert result['held_words'][0]['reason']=='native_sentence_token_text_mismatch'
    assert result['token_accounting']=={'input':3,'supported':2,'held':1,'conserved':True}
