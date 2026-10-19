"""Private word/turn proposals. No identity admission, I/O or publication."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re

from .transcript_links import temporal_evidence

ALIGNMENT_VERSION = 'measured-word-turn-candidates-v1'
LOADED_CODE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
_REQUIRED_HASHES = ('recording_sha256', 'transcript_sha256', 'token_source_sha256',
                    'diarization_sha256', 'tokenizer_sha256')


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def align_word_turns(parent, tokens, turns, *, provenance,
                     token_offset_seconds=0., diarization_offset_seconds=0.):
    """Conserve measured tokens and propose anonymous utterances, never names.

    Text disagreement holds the OLD paragraph; anonymous new-version proposals
    remain inspectable. Supplied hashes describe inputs, not an identity proof.
    A caller must verify original artifact bytes before any later publication.
    """
    original = deepcopy(parent)
    inputs = {'parent': original, 'tokens': tokens, 'turns': turns,
              'provenance': provenance, 'token_offset_seconds': token_offset_seconds,
              'diarization_offset_seconds': diarization_offset_seconds,
              'alignment_version': ALIGNMENT_VERSION, 'code_sha256': LOADED_CODE_SHA256}
    result = {'status': 'held_invalid_input', 'parent': original,
              'publication_eligible': False, 'identity_status': 'anonymous_only',
              'utterances': [], 'held_words': [], 'provenance': deepcopy(provenance),
              'alignment_version': ALIGNMENT_VERSION, 'code_sha256': LOADED_CODE_SHA256}
    try:
        encoded = json.dumps(inputs, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
        result['input_sha256'] = hashlib.sha256(encoded.encode()).hexdigest()
        if not all(isinstance(provenance.get(k), str) and re.fullmatch('[0-9a-f]{64}', provenance[k]) for k in _REQUIRED_HASHES):
            raise ValueError('missing_source_artifact_hash')
        start, end = parent['start'], parent['end']
        if not (_finite(start) and _finite(end) and 0 <= start < end and isinstance(parent['text'], str)
                and _finite(token_offset_seconds) and _finite(diarization_offset_seconds)):
            raise ValueError('invalid_parent_or_time_transform')
        if not tokens or not isinstance(tokens, list) or not isinstance(turns, list):
            raise ValueError('measured_tokens_and_turns_required')
        measured = []
        for t in turns:
            if not (_finite(t.get('start')) and _finite(t.get('end')) and 0 <= t['start'] < t['end']
                    and isinstance(t.get('speaker'), str) and t['speaker']):
                raise ValueError('invalid_raw_turn')
            left, right = t['start']+diarization_offset_seconds, t['end']+diarization_offset_seconds
            if right > 0:
                measured.append({'start': max(0., left), 'end': right, 'speaker': t['speaker']})
        words, previous_start = [], float('-inf')
        for index, token in enumerate(tokens):
            text = token.get('text')
            if not (isinstance(text, str) and text and _finite(token.get('start')) and _finite(token.get('end'))):
                raise ValueError('invalid_token')
            left, right = token['start']+token_offset_seconds, token['end']+token_offset_seconds
            if not start <= left <= right <= end or left < previous_start:
                raise ValueError('token_outside_parent_or_nonmonotonic')
            previous_start = left
            # Never split one timestamped token internally. Whitespace starts
            # a new lexical unit; continuation subwords remain inseparable.
            if not words or text[0].isspace():
                words.append({'raw_text': '', 'start': left, 'end': right, 'token_indices': [],
                              'unmeasured_lexical': False, 'source_hold_reasons': []})
            word = words[-1]
            word['raw_text'] += text
            word['start'], word['end'] = min(word['start'], left), max(word['end'], right)
            word['token_indices'].append(index)
            # A caller can restrict a source unit after checking its native
            # artifact; this only adds holds and can never approve identity.
            if token.get('source_hold_reason'):
                if not isinstance(token['source_hold_reason'], str):
                    raise ValueError('invalid_source_hold_reason')
                word['source_hold_reasons'].append(token['source_hold_reason'])
            if left == right and any(c.isalnum() for c in text):
                word['unmeasured_lexical'] = True
    except (KeyError, TypeError, ValueError) as error:
        result['reason'] = str(error)
        return result

    new_text = ''.join(t['text'] for t in tokens)
    exact = new_text.strip() == parent['text'].strip()
    utterances, held = result['utterances'], result['held_words']
    current = None

    def finish():
        nonlocal current
        if current is not None:
            current['text'] = current['raw_text'].strip()
            current['identity_status'] = 'anonymous_only'
            utterances.append(current)
            current = None

    for word in words:
        nearby = [t for t in measured if t['start'] < word['end'] and t['end'] > word['start']]
        evidence = [(temporal_evidence(word['start'], word['end'], label, nearby), label)
                    for label in sorted({t['speaker'] for t in nearby})]
        supported = [(e, label) for e, label in evidence if e['status'] == 'supported']
        # A measured lexical unit cannot be cut or assigned across a voice
        # boundary, even if a small competing sliver passes utterance gates.
        crosses_voice = (len(supported) == 1 and any(
            t['speaker'] != supported[0][1] and
            min(t['end'], word['end']) > max(t['start'], word['start'])
            for t in nearby))
        reason = (word['source_hold_reasons'][0] if word['source_hold_reasons'] else
                  'unmeasured_lexical_token' if word['unmeasured_lexical'] else
                  'missing_measured_word_duration' if word['end'] <= word['start'] else
                  'word_crosses_measured_voice_boundary' if crosses_voice else
                  'mixed_or_insufficient_temporal_support' if len(supported) != 1 else None)
        if reason:
            finish()
            held.append({**word, 'reason': reason, 'candidate_temporal_evidence': evidence})
            continue
        timing, label = supported[0]
        if current is not None:
            combined = temporal_evidence(current['start'], word['end'], label, measured)
            if current['speaker_label'] != label or combined['status'] != 'supported':
                finish()
            else:
                current['end'] = word['end']
                current['raw_text'] += word['raw_text']
                current['token_indices'].extend(word['token_indices'])
                current['temporal_evidence'] = combined
                continue
        current = {**word, 'speaker_label': label, 'temporal_evidence': timing}
        current.pop('unmeasured_lexical', None)
        current.pop('source_hold_reasons', None)
    finish()
    supported_indices = [i for u in utterances for i in u['token_indices']]
    held_indices = [i for w in held for i in w['token_indices']]
    conserved = sorted(supported_indices+held_indices) == list(range(len(tokens)))
    if not conserved:
        raise RuntimeError('token_conservation_failed')
    result.update(status='alignment_candidate' if exact else 'held_original_text_mismatch',
                  original_text_match=exact, utterance_text_basis='original_token_evidence' if exact else 'new_version_token_evidence',
                  token_text=new_text, token_accounting={'input': len(tokens), 'supported': len(supported_indices),
                                                        'held': len(held_indices), 'conserved': conserved})
    return result
