"""Source-bound speaker identity and row-link planning, separate from transcription.

Aliases are candidates, never identity evidence. This module performs no model,
network or database calls. Raw artifacts remain private; output receipts carry
bounded lineage and hashes for the service-only evidence ledger.
"""
from __future__ import annotations
import hashlib
import json
import math
import marshal
from pathlib import Path
import re
import subprocess
import wave
from urllib.parse import urlparse, parse_qs

VALIDATOR_VERSION = 'source-speaker-links-v2-direct-only'


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _artifact(reference, *, content=True):
    path = Path(reference['path'])
    hasher = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            hasher.update(block)
    if hasher.hexdigest() != reference['sha256']:
        raise ValueError('artifact_hash_changed')
    return path.read_bytes() if content else path


def _result(reference):
    data = json.loads(_artifact(reference))
    return data.get('result', data)


def _unit(values):
    if not isinstance(values, list) or len(values) != 192 or any(
        not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(x) for x in values
    ):
        raise ValueError('unvalidated_voice_vector')
    size = math.sqrt(sum(x*x for x in values))
    if not size:
        raise ValueError('empty_voice_vector')
    return [x/size for x in values]


def _union_seconds(intervals, start, end):
    clipped = sorted((max(start, a), min(end, b)) for a, b in intervals if a < end and b > start)
    total, previous = 0., start
    for left, right in clipped:
        total += max(0., right-max(left, previous))
        previous = max(previous, right)
    return total


def temporal_evidence(start, end, target_label, turns):
    """Measure the union of ALL competing voices; missing intervals cannot pass."""
    if not turns or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                            and math.isfinite(v) for v in (start, end)) or not 0 <= start < end:
        return {'status': 'missing_or_invalid_temporal_evidence'}
    target, others = [], []
    for turn in turns:
        left, right = turn.get('start'), turn.get('end')
        if (not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                    for v in (left, right)) or not 0 <= left < right or not turn.get('speaker')):
            return {'status': 'invalid_diarization_interval'}
        (target if turn['speaker'] == target_label else others).append((left, right))
    duration = end-start
    coverage = _union_seconds(target, start, end)/duration
    competing = _union_seconds(others, start, end)/duration
    return {'status': 'supported' if coverage >= .90 and competing <= .10 else 'mixed_or_insufficient_temporal_support',
            'target_coverage': coverage, 'competing_fraction': competing,
            'algorithm': 'unrounded_interval_union_all_competitors_v1'}


def _official_text(reference, format):
    raw = _artifact(reference)
    if format == 'html':
        from bs4 import BeautifulSoup
        return BeautifulSoup(raw, 'html.parser').get_text(' ', strip=True)
    if format == 'pdf':
        return subprocess.run(['pdftotext', '-layout', '-', '-'], input=raw, check=True,
                              capture_output=True, timeout=40).stdout.decode(errors='replace')
    raise ValueError('unsupported_official_name_source')


def _pcm(reference):
    path = _artifact(reference, content=False)
    with wave.open(str(path), 'rb') as audio:
        if (audio.getnchannels(), audio.getframerate(), audio.getsampwidth()) != (1, 16000, 2):
            raise ValueError('reference_clip_must_be_16k_mono_pcm')
        return audio.readframes(audio.getnframes())


def _verify_clip(anchor):
    source = _artifact(anchor['recording'], content=False)
    actual = _pcm(anchor['clip'])
    seconds = anchor['clip_end']-anchor['clip_start']
    if not 0 < seconds <= 30 or anchor['clip_start'] < 0:
        raise ValueError('unbounded_reference_clip')
    expected = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-ss', str(anchor['clip_start']),
        '-i', str(source), '-t', str(seconds), '-ac', '1', '-ar', '16000', '-f', 's16le', 'pipe:1'],
        check=True, capture_output=True, timeout=60).stdout
    if actual != expected:
        raise ValueError('reference_clip_not_bound_to_original_offset')


def _recording_identity(request):
    # A content hash proves bytes, not independence: MP3 and M4A encodings of
    # the same Vimeo recording must retain one immutable player identity.
    parsed = urlparse(request['recording_url'])
    if parsed.hostname in ('vimeo.com', 'www.vimeo.com', 'player.vimeo.com'):
        matches = re.findall(r'(?:^|/)([0-9]+)(?:/|$)', parsed.path)
        if len(matches) != 1:
            raise ValueError('ambiguous_canonical_recording_provenance')
        identity = 'vimeo:'+matches[0]
    elif (parsed.hostname == 'pub-langford.escribemeetings.com'
          and parsed.path.casefold() == '/players/isistandaloneplayer.aspx'):
        ids = parse_qs(parsed.query).get('Id', [])
        if len(ids) != 1 or not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', ids[0]):
            raise ValueError('ambiguous_canonical_recording_provenance')
        identity = 'escribe:langford:'+ids[0].lower()
    else:
        raise ValueError('unsupported_canonical_recording_provenance')
    if request.get('recording_id') != identity:
        raise ValueError('canonical_recording_provenance_mismatch')
    return identity


def _name_anchor(anchor, canonical_people, person_id, name):
    recording_id = _recording_identity(anchor)
    _verify_clip(anchor)
    asr = json.loads(_artifact(anchor['independent_asr']))
    if (not {'prompt', 'known_speaker_references'} <= asr.keys()
            or asr['prompt'] is not None or asr['known_speaker_references'] is not None):
        raise ValueError('unprompted_asr_provenance_required')
    if asr.get('clip_sha256') != anchor['clip']['sha256']:
        raise ValueError('asr_clip_mismatch')
    quote = asr.get('response', {}).get('text', '')
    introduction = (r"^\s*(?:(?:hi(?: there)?|hello|um|uh|good evening)[, .]+)?"
                    r"(?:my name is|i['’]m|i am)\s+"+re.escape(name)+r'\b')
    if not re.search(introduction, quote, re.I):
        raise ValueError('literal_first_person_self_introduction_required')
    official = _official_text(anchor['official_name_source'], anchor['official_format'])
    parts = name.split(); initial, surname = parts[0][0], parts[-1]
    full = re.search(r'\b'+re.escape(name)+r'\b', official, re.I)
    short = re.search(r'\b'+re.escape(initial)+r'\s*\.\s*'+re.escape(surname)+r'\b', official, re.I)
    matches = [p for p in canonical_people if p['name'].split()[0][0].casefold()==initial.casefold()
               and p['name'].split()[-1].casefold()==surname.casefold()]
    if not full and not (short and len(matches)==1):
        raise ValueError('official_name_corroboration_missing_or_ambiguous')
    wrapper = json.loads(_artifact(anchor['diarization']))
    if wrapper.get('clip_sha256') != anchor['clip']['sha256']:
        raise ValueError('diarization_clip_mismatch')
    fresh = wrapper.get('result') or {}
    if fresh.get('raw_speakers_detected') != 1 or len(fresh.get('speaker_centroids', {})) != 1:
        raise ValueError('reference_intro_not_single_voice')
    label, vector = next(iter(fresh['speaker_centroids'].items()))
    timing = temporal_evidence(0., anchor['clip_end']-anchor['clip_start'], label, fresh.get('raw_segments'))
    if timing['status'] != 'supported':
        raise ValueError('reference_intro_purity_held')
    return _unit(vector), {'person_id':person_id,'person_name':name,
        'recording_id':recording_id,'recording_sha256':anchor['recording']['sha256'],'clip_sha256':anchor['clip']['sha256'],
        'clip_start':anchor['clip_start'],'clip_end':anchor['clip_end'],
        'asr_sha256':anchor['independent_asr']['sha256'],'spoken_quote':quote,
        'asr_model':asr.get('model'),'official_sha256':anchor['official_name_source']['sha256'],
        'official_name_quote':(full or short)[0],'diarization_sha256':anchor['diarization']['sha256'],
        'diarization_model':wrapper.get('model'),'temporal_evidence':timing}


def admit_identity(request, canonical_people):
    """Admit direct bounded introductions or independently enrolled propagation.

    Direct introduction proves only its actual clip. Cross-recording propagation
    remains held until independent model calibration is validated.
    Neither mode admits an alias or a supplied verified/confidence flag.
    """
    try:
        person_id, name = request['person_id'], request['person_name']
        if [p['name'] for p in canonical_people if p['id'] == person_id] != [name]:
            raise ValueError('canonical_person_mismatch')
        normalized_name = ' '.join(name.casefold().split())
        if len([p for p in canonical_people if ' '.join(p['name'].casefold().split()) == normalized_name]) != 1:
            raise ValueError('ambiguous_canonical_full_name')
        source_run = request['source_run']
        if source_run['recording_id'] != _recording_identity(request):
            raise ValueError('canonical_recording_provenance_mismatch')
        for ref, key in (('recording','recording_sha256'),('transcript','transcript_sha256'),('diarization','diarization_run_sha256')):
            if request[ref]['sha256'] != source_run[key]:
                raise ValueError('target_'+ref+'_mismatch')
            _artifact(request[ref], content=False)
        _verify_clip(request)
        wrapper = json.loads(_artifact(request['diarization']))
        if wrapper.get('clip_sha256') != request['clip']['sha256']:
            raise ValueError('target_diarization_clip_mismatch')
        target = wrapper.get('result') or {}
        vectors = {key:_unit(value) for key,value in target.get('speaker_centroids', {}).items()}
        label = request['target_speaker_label']; vector = vectors[label]
        mode = request.get('mode')
        if mode == 'direct_source_self_introduction':
            if request['clip_end']-request['clip_start'] > 12:
                raise ValueError('direct_introduction_clip_exceeds_bounded_utterance_limit')
            _, anchor = _name_anchor(request, canonical_people, person_id, name)
            anchors = [anchor]; voice = {'basis':'actual_named_single_voice_clip_only'}
        elif mode == 'independent_recording_voice_propagation':
            raise ValueError('cross_recording_calibration_not_validated')
        else:
            raise ValueError('supported_identity_mode_required')
        offset = request['clip_start']
        turns = [{**turn,'start':turn['start']+offset,'end':turn['end']+offset}for turn in target.get('raw_segments',[])]
        proof = {**source_run,'person_id':person_id,'person_name':name,'validator_version':VALIDATOR_VERSION,'validator_sha256':VALIDATOR_SHA256,
                 'mode':mode,'anchors':anchors,'voice':voice,'target_speaker_label':label,
                 'clip_start':request['clip_start'],'clip_end':request['clip_end'],
                 'diarization_intervals_sha256':digest(turns),'artifact_refs':{
                     key:request[key]for key in ('recording','transcript','diarization','clip')}}
        return {'status':'identity_admitted',**source_run,'validator_version':VALIDATOR_VERSION,'validator_sha256':VALIDATOR_SHA256,
                'person_id':person_id,'person_name':name,'target_speaker_label':label,
                'proof':proof,'identity_evidence_sha256':digest(proof)}
    except (KeyError,ValueError,TypeError,OSError,subprocess.SubprocessError) as error:
        return {'status':'identity_held','reason':str(error)}


def verify_transcript_link(row, original_segment, admission, diarization_turns, *, source_run):
    """Plan a same-ID repair from actual hashed artifacts, never caller-only tuples."""
    def hold(reason):
        return {'status':'held','operation':'hold','segment_id':row.get('id'),'reason':reason}
    proof = admission.get('proof') or {}
    if admission.get('status')!='identity_admitted' or digest(proof)!=admission.get('identity_evidence_sha256'):
        return hold('independent_identity_admission_required')
    if (admission.get('validator_version')!=VALIDATOR_VERSION or proof.get('validator_version')!=VALIDATOR_VERSION
            or admission.get('validator_sha256')!=VALIDATOR_SHA256 or proof.get('validator_sha256')!=VALIDATOR_SHA256):
        return hold('identity_validator_changed')
    keys=('meeting_id','recording_id','recording_sha256','transcript_sha256','diarization_run_sha256')
    if (any(admission.get(key)!=source_run.get(key) or proof.get(key)!=source_run.get(key)for key in keys)
            or row.get('meeting_id')!=source_run.get('meeting_id')):
        return hold('source_recording_run_or_meeting_changed')
    if any(admission.get(key)!=proof.get(key)for key in ('person_id','person_name','target_speaker_label')):
        return hold('identity_envelope_changed')
    if row.get('is_verified'):
        return hold('verified_row_preserved')
    if row.get('person_id') not in (None,admission['person_id']):
        return hold('existing_other_person_requires_independent_correction_review')
    if (row.get('start_time'),row.get('end_time'),row.get('text_content'))!=(
        original_segment.get('start'),original_segment.get('end'),original_segment.get('text')):
        return hold('original_time_text_binding_mismatch')
    try:
        refs = proof['artifact_refs']
        _artifact(refs['recording'],content=False)
        transcript = json.loads(_artifact(refs['transcript']))
        source_segments = transcript.get('segments',transcript.get('chunks',[])) if isinstance(transcript,dict)else transcript
        exact = [s for s in source_segments if (s.get('start',s.get('start_time')),s.get('end',s.get('end_time')),s.get('text'))==(
            row['start_time'],row['end_time'],row['text_content'])]
        if len(exact)!=1:
            return hold('original_transcript_occurrence_not_unique_or_missing')
        wrapper = json.loads(_artifact(refs['diarization']))
        raw = (wrapper.get('result')or{}).get('raw_segments',[]);offset = proof['clip_start']
        measured = [{**turn,'start':turn['start']+offset,'end':turn['end']+offset}for turn in raw]
        if digest(measured)!=proof['diarization_intervals_sha256'] or digest(diarization_turns)!=digest(measured):
            return hold('measured_diarization_intervals_changed')
        if not proof['clip_start']<=row['start_time']<row['end_time']<=proof['clip_end']:
            return hold('outside_proven_source_clip')
    except (OSError,KeyError,ValueError,TypeError) as error:
        return hold(str(error))
    timing = temporal_evidence(row['start_time'],row['end_time'],admission['target_speaker_label'],measured)
    if timing['status']!='supported':
        return hold(timing['status'])
    evidence = {'identity_evidence_sha256':admission['identity_evidence_sha256'],'temporal_evidence':timing,
                'diarization_intervals_sha256':digest(measured)}
    operation = 'fill_null' if row.get('person_id')is None else'retain_supported'
    envelope = {**{key:source_run[key]for key in keys},'validator_version':VALIDATOR_VERSION,'validator_sha256':VALIDATOR_SHA256,
                'identity_evidence_sha256':admission['identity_evidence_sha256']}
    inputs = {'source_run':source_run,'envelope':envelope,'expected_row':row,
              'person_id':admission['person_id'],'speaker_name':admission['person_name'],
              'operation':operation,'evidence':evidence}
    encoded = canonical_json(inputs)
    return {'status':'link_candidate',**envelope,'segment_id':row['id'],
            'person_id':admission['person_id'],'speaker_name':admission['person_name'],
            'operation':operation,'expected_row':row,'evidence':evidence,
            'input_canonical_json':encoded,'input_sha256':hashlib.sha256(encoded.encode()).hexdigest()}


# Fingerprint the code objects actually loaded into this process. Reading this
# file later could falsely advertise new disk code in a long-running old worker.
VALIDATOR_SHA256 = hashlib.sha256(
    VALIDATOR_VERSION.encode()+b''.join(marshal.dumps(value.__code__)+canonical_json({'defaults':value.__defaults__,
            'kwdefaults':value.__kwdefaults__}).encode() for name,value in sorted(globals().items())
        if callable(value) and getattr(value, '__module__', None)==__name__ and hasattr(value,'__code__'))
).hexdigest()
