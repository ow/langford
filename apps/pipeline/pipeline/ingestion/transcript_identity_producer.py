"""Private, bounded evidence production for literal speaker introductions.

A raw-ASR name is only a lead. Unprompted short-clip ASR and fresh diarization
produce artifacts for the independent verifier; aliases never enter a request.
The manifest records pending work so batch limits do not lose later speakers.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
from contextlib import contextmanager
import fcntl

from . import transcript_links as validator

PRODUCER_VERSION = 'direct-introduction-producer-v1'
ASR_MODEL = 'gpt-4o-transcribe'
MAX_CLIPS = 4
MAX_SECONDS = 48


def file_sha(path):
    hasher = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            hasher.update(block)
    return hasher.hexdigest()


def reference(path):
    return {'path': str(Path(path).resolve()), 'sha256': file_sha(path)}


_LOADED_PRODUCER_SHA256 = file_sha(__file__)


def _write(path, value):
    path = Path(path)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, allow_nan=False, indent=2)
        temporary = Path(handle.name)
    temporary.replace(path)


@contextmanager
def _lock(path):
    with Path(path).open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def _native(value):
    if isinstance(value, dict):
        return {str(k): _native(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_native(v) for v in value]
    return value.tolist() if hasattr(value, 'tolist') else value.item() if hasattr(value, 'item') else value


class DirectIntroductionProducer:
    """One batch; expensive provider/model objects are loaded lazily once."""

    def __init__(self):
        self._diarizer = None
        self._model_lineage = None

    def _lineage(self):
        if self._model_lineage is None:
            import senko
            import senko.config as senko_config
            root = Path(senko.__file__).parent
            asset = Path(senko_config.EMBEDDINGS_COREML_PATH)
            files = sorted(asset.rglob('*')) if asset.is_dir() else [asset]
            assets = {str(p.relative_to(asset) if asset.is_dir() else p.name): file_sha(p)
                      for p in files if p.is_file()}
            self._model_lineage = {
                'provider': 'openai', 'asr_model': ASR_MODEL,
                'senko_diarizer_sha256': file_sha(root / 'diarizer.py'),
                'senko_camplusplus_sha256': file_sha(root / 'camplusplus.py'),
                'embedding_asset_tree_sha256': validator.digest(assets),
                'producer_sha256': _LOADED_PRODUCER_SHA256,
                'validator_sha256': validator.VALIDATOR_SHA256,
            }
        return self._model_lineage

    def _transcribe(self, clip):
        from pipeline import ai
        # One attempt: each request is recorded as evidence, so no silent re-asks.
        result = ai.transcribe(str(clip), model=ASR_MODEL, max_attempts=1, timeout=90,
                               language='en', response_format='json', include=['logprobs'])
        return {'model': ASR_MODEL, 'provider': 'openai', 'prompt': None,
                'known_speaker_references': None, 'request_id': result.request_id,
                'response': result.response}

    def _diarize(self, clip):
        if self._diarizer is None:
            import torch
            import senko
            torch.set_num_threads(4)
            self._diarizer = senko.Diarizer(device='auto', quiet=True, warmup=False)
        return _native(self._diarizer.diarize(str(clip), accurate=True))

    def produce(self, *, folder, meeting, people, transcript, recording, official_source, recording_id):
        """Persist/cache every lead; return a bounded private request inventory.

        Inputs must already have a validated original meeting source. No shared
        recording segmentation or invented parser timings are accepted here.
        """
        folder, transcript, recording = Path(folder), Path(transcript), Path(recording)
        cache = folder / '.speaker_identity'
        cache.mkdir(exist_ok=True)
        with _lock(cache / '.lock'):
            return self._produce_locked(cache, meeting, people, transcript, recording, official_source, recording_id)

    def _produce_locked(self, cache, meeting, people, transcript, recording, official_source, recording_id):
        raw = json.loads(transcript.read_text())
        segments = raw.get('segments') if isinstance(raw, dict) else raw
        if not isinstance(segments, list) or not segments or not all(isinstance(s, dict) for s in segments):
            return {'status': 'held', 'reason': 'raw_segment_source_required', 'requests': [], 'pending': 0}
        lineage = self._lineage()
        literal_people = [p for p in people if p.get('name') and any(
            re.search(r'\b'+re.escape(p['name'])+r'\b', segment.get('text', ''), re.I)
            for segment in segments if isinstance(segment.get('text'), str))]
        # The verifier also resolves official initial/surname mentions. Include
        # every competitor in those cohorts, not just the spoken full name.
        cohorts = {(p['name'].split()[0][0].casefold(), p['name'].split()[-1].casefold())
                   for p in literal_people if p['name'].split()}
        relevant_people = [p for p in people if p.get('name') and
                           (p['name'].split()[0][0].casefold(), p['name'].split()[-1].casefold()) in cohorts]
        common = {'meeting_id': meeting['id'], 'recording_id': recording_id,
                  'recording': reference(recording), 'transcript': reference(transcript),
                  'official_name_source': reference(official_source['path']),
                  'official_format': official_source['format'],
                  'source_identity': official_source.get('identity'),
                  'recording_url': meeting['video_url'], 'lineage': lineage,
                  'canonical_registry_sha256': validator.digest(sorted(
                      ({'id': p['id'], 'name': p['name']} for p in relevant_people), key=lambda p: p['id']))}
        input_key = validator.digest(common)
        run_dir = cache / input_key
        run_dir.mkdir(exist_ok=True)
        manifest_path = run_dir / 'manifest.json'
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
        else:
            names = {}
            for person in people:
                name = person.get('name', '').strip()
                # Initial-only canonical names cannot be completed from an ASR guess.
                if len(name.split()) < 2 or any(len(x.rstrip('.')) < 2 for x in name.split()):
                    continue
                names.setdefault(' '.join(name.casefold().split()), []).append(person)
            leads = []
            for index, segment in enumerate(segments):
                text = segment.get('text')
                start, end = segment.get('start'), segment.get('end')
                if (not isinstance(text, str) or not all(isinstance(t, (int, float)) and not isinstance(t, bool)
                        and math.isfinite(t) for t in (start, end)) or not 0 <= start < end):
                    continue
                # The utterance itself must start with the first-person statement;
                # a name mentioned later in a large turn never supplies identity.
                lead = re.match(r"^\s*(?:(?:hi(?: there)?|hello|um|uh|good evening)[, .]+)?(?:my name is|i['’]m|i am)\s+", text, re.I)
                if not lead:
                    continue
                matches = [persons for key, persons in names.items()
                           if re.match(re.escape(key) + r'\b', ' '.join(text[lead.end():].casefold().split()))]
                people_found = [p for group in matches for p in group]
                reason = None
                if len(people_found) != 1:
                    reason = 'canonical_full_name_missing_or_ambiguous'
                if end-start > 12:
                    reason = 'raw_intro_utterance_exceeds_12_seconds'
                person = people_found[0] if len(people_found) == 1 else None
                leads.append({'segment_index': index, 'start': start, 'end': end,
                              'person_id': person['id'] if person else None,
                              'person_name': person['name'] if person else None,
                              'status': 'held' if reason else 'pending', 'reason': reason})
            manifest = {'version': PRODUCER_VERSION, 'input_key': input_key, 'inputs': common, 'leads': leads}
            _write(manifest_path, manifest)
        requests, processed, seconds = [], 0, 0.
        for index, lead in enumerate(manifest['leads']):
            lead_dir = run_dir / str(index)
            if lead['status'] == 'ready':
                requests.append(json.loads((lead_dir / 'request.json').read_text()))
                continue
            if lead['status'] != 'pending' or processed >= MAX_CLIPS or seconds + lead['end']-lead['start'] > MAX_SECONDS:
                continue
            lead_dir.mkdir(exist_ok=True)
            clip = lead_dir / 'clip.wav'
            if not clip.exists():
                temporary = lead_dir / 'clip.pending.wav'
                subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(lead['start']),
                                '-i', str(recording), '-t', str(lead['end']-lead['start']), '-ac', '1', '-ar', '16000',
                                '-c:a', 'pcm_s16le', str(temporary)], check=True, timeout=90)
                temporary.replace(clip)
            clip_sha = file_sha(clip)
            # Paid/model artifacts depend on actual clip bytes and model inputs,
            # not on registry identity eligibility or the current validator.
            # Resolving a name collision re-runs admission using the same work.
            model_lineage = {key: value for key, value in lineage.items()
                             if key not in ('producer_sha256', 'validator_sha256')}
            artifact_dir = cache / 'artifacts' / validator.digest({
                'clip_sha256': clip_sha, 'model_lineage': model_lineage,
                'asr_parameters': {'language': 'en', 'response_format': 'json', 'include': ['logprobs'],
                                   'prompt': None, 'known_speaker_references': None},
                'diarization_parameters': {'accurate': True, 'device': 'auto'}})
            artifact_dir.mkdir(parents=True, exist_ok=True)
            asr_path, diar_path = artifact_dir / 'independent-asr.json', artifact_dir / 'fresh-diarization.json'

            # Save each paid response immediately; a later local failure reuses it.
            if not asr_path.exists():
                _write(asr_path, {**self._transcribe(clip), 'clip_sha256': clip_sha, 'lineage': lineage})
            if not diar_path.exists():
                _write(diar_path, {'clip_sha256': clip_sha, 'model': 'senko-camplusplus',
                                   'lineage': lineage, 'result': self._diarize(clip)})
            diar = json.loads(diar_path.read_text()).get('result') or {}
            labels = list(diar.get('speaker_centroids') or {})
            if len(labels) != 1:
                lead.update(status='held', reason='independent_clip_not_one_voice')
            else:
                source_run = {'meeting_id': meeting['id'], 'recording_id': recording_id,
                              'recording_sha256': common['recording']['sha256'],
                              'transcript_sha256': common['transcript']['sha256'],
                              'diarization_run_sha256': file_sha(diar_path)}
                request = {'mode': 'direct_source_self_introduction', 'person_id': lead['person_id'],
                           'person_name': lead['person_name'], 'recording': common['recording'],
                           'recording_url': meeting['video_url'], 'recording_id': recording_id,
                           'clip': reference(clip), 'clip_start': lead['start'], 'clip_end': lead['end'],
                           'transcript': common['transcript'], 'diarization': reference(diar_path),
                           'independent_asr': reference(asr_path), 'official_name_source': common['official_name_source'],
                           'official_format': common['official_format'], 'source_run': source_run,
                           'target_speaker_label': labels[0]}
                admission = validator.admit_identity(request, people)
                if admission['status'] == 'identity_admitted':
                    _write(lead_dir / 'request.json', request)
                    lead.update(status='ready', reason=None)
                    requests.append(request)
                else:
                    lead.update(status='held', reason=admission.get('reason'))
            processed += 1
            seconds += lead['end']-lead['start']
            _write(manifest_path, manifest)
        return {'status': 'produced', 'input_key': input_key, 'requests': requests,
                'pending': sum(x['status'] == 'pending' for x in manifest['leads']),
                'held': sum(x['status'] == 'held' for x in manifest['leads']),
                'clips_processed': processed, 'audio_seconds_processed': seconds}
