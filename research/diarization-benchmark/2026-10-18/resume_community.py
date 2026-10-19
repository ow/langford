"""Offline full-recording Community-1 run with content-bound private checkpoints.

Does not run preparation, send API requests, or update production. The existing
reference prefix remains an enrollment diagnostic, never identity ground truth.
"""
from __future__ import annotations
import hashlib
import fcntl
import json
import os
from pathlib import Path
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SCRATCH = Path('/private/tmp/langford-diarization-bench')
PRIVATE = ROOT / '.private/research/diarization-benchmark/2026-10-19'
REVISION = '3533c8cf8e369892e6b79ff1bf80f7b0286a54ee'


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


LOADED_RUNNER_SHA256 = sha(__file__)

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.pending')
    temporary.write_text(json.dumps(value, indent=2, default=str)+'\n')
    temporary.replace(path)


def update_state(**values):
    path = PRIVATE/'state.json'
    current = json.loads(path.read_text()) if path.exists() else {}
    current.update(values, updated_at_unix=time.time())
    save(path, current)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def checkpoint_valid(path):
    receipt = path.with_suffix(path.suffix+'.sha.json')
    if not path.exists() or not receipt.exists():
        return False
    if json.loads(receipt.read_text()).get('sha256') != sha(path):
        raise RuntimeError('Full-stage checkpoint integrity mismatch')
    return True


def checkpoint_receipt(path):
    save(path.with_suffix(path.suffix+'.sha.json'), {'sha256': sha(path)})


class CachedEmbedding:
    """Preserve each actual model batch, keyed by all waveform/mask bytes."""
    def __init__(self, model, directory):
        self.model, self.directory = model, Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.computed = self.reused = 0

    def __getattr__(self, key):
        return getattr(self.model, key)

    def __call__(self, waveforms, masks):
        import numpy as np
        hasher = hashlib.sha256()
        for value in (waveforms, masks):
            array = value.detach().cpu().contiguous().numpy()
            hasher.update(str((array.shape, array.dtype.str)).encode())
            hasher.update(array.tobytes())
        key = hasher.hexdigest()
        path = self.directory / (key+'.npy')
        metadata = path.with_suffix('.json')
        if path.exists() and metadata.exists():
            receipt = json.loads(metadata.read_text())
            if receipt['input_sha256'] != key or receipt['output_sha256'] != sha(path):
                raise RuntimeError('Embedding checkpoint integrity mismatch')
            result = np.load(path, allow_pickle=False)
            self.reused += 1
            return result
        result = self.model(waveforms, masks=masks)
        temporary = path.with_suffix('.pending.npy')
        np.save(temporary, result, allow_pickle=False)
        temporary.replace(path)
        save(metadata, {'input_sha256': key, 'output_sha256': sha(path),
                        'shape': list(result.shape)})
        self.computed += 1
        return result


def main():
    PRIVATE.mkdir(parents=True, exist_ok=True)
    run_lock = (PRIVATE/'.run.lock').open('a')
    try:
        fcntl.flock(run_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError('Community-1 benchmark already active; refusing duplicate heavy work')
    update_state(status='initializing_community_1', pid=os.getpid(), new_paid_requests=0)
    # Set before importing torch. The GPU allocator may not consume arbitrary
    # fractions of unified memory while other work is active on this M4/32GiB.
    os.environ['PYTORCH_MPS_HIGH_WATERMARK_RATIO'] = '0.40'
    os.environ['PYTORCH_MPS_LOW_WATERMARK_RATIO'] = '0.30'
    os.environ['PYANNOTE_METRICS_ENABLED'] = '0'
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ.setdefault('MPLCONFIGDIR', str(SCRATCH/'matplotlib'))
    import importlib.metadata
    import numpy as np
    import soundfile as sf
    import torch
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    from pyannote.audio import Pipeline
    import pyannote.audio.pipelines.speaker_diarization as implementation
    from pyannote.core import SlidingWindow, SlidingWindowFeature
    from huggingface_hub import get_token
    import resource
    token = get_token()
    if not token:
        token_path = SCRATCH/'hf-token'
        token = token_path.read_text().strip() if token_path.exists() else None
    if not token:
        raise RuntimeError('Model credential unavailable; no credential is logged')
    PRIVATE.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    pipeline = Pipeline.from_pretrained('pyannote/speaker-diarization-community-1', revision=REVISION, token=token)
    device = 'mps' if torch.backends.mps.is_available() else 'cpu'
    pipeline.to(torch.device(device))
    pipeline.segmentation_batch_size = 32
    pipeline.embedding_batch_size = 32
    initialization = time.perf_counter()-started
    manifest = json.loads((PRIVATE/'legacy-protocol-manifest.json').read_text())
    versions = {name: importlib.metadata.version(name) for name in ('pyannote.audio', 'torch', 'numpy', 'soundfile')}
    hub = Path(os.environ.get('HF_HOME', str(Path.home()/'.cache/huggingface'))) / 'hub'
    assets = {}
    for repository in ('models--pyannote--speaker-diarization-community-1',
                       'models--pyannote--segmentation-3.0', 'models--pyannote--wespeaker-voxceleb-resnet34-LM'):
        for artifact in sorted((hub/repository/'snapshots').glob('**/*')):
            if artifact.is_file():
                assets[str(artifact.relative_to(hub))] = sha(artifact)
    protocol = {'model_revision': REVISION, 'model_assets_sha256': fingerprint(assets),
                'manifest_sha256': sha(PRIVATE/'legacy-protocol-manifest.json'),
                'versions': versions, 'device': device,
                'torch_threads': 4, 'segmentation_batch_size': 32, 'embedding_batch_size': 32,
                'implementation_sha256': sha(implementation.__file__), 'runner_sha256': LOADED_RUNNER_SHA256,
                'mps_high_watermark_ratio': os.environ['PYTORCH_MPS_HIGH_WATERMARK_RATIO'],
                'mps_low_watermark_ratio': os.environ['PYTORCH_MPS_LOW_WATERMARK_RATIO']}
    print(json.dumps({'stage': 'initialized', 'seconds': initialization, **protocol}), flush=True)
    update_state(status='running_community_1', protocol=protocol)
    initial_embedding = pipeline._embedding
    original_segmentation = pipeline.get_segmentations
    original_embeddings = pipeline.get_embeddings
    for meeting in manifest['meetings']:
        mid = meeting['id']
        destination = HERE/'results'/f'{mid}-community.json'
        audio_path = SCRATCH/str(mid)/'input.wav'
        inputs = {**protocol, 'meeting_id': mid, 'audio_sha256': sha(audio_path)}
        if destination.exists():
            previous = json.loads(destination.read_text())
            previous_inputs = previous.get('protocol') or {}
            compared_keys = set(inputs) - {'runner_sha256', 'mps_high_watermark_ratio', 'mps_low_watermark_ratio'}
            if any(previous_inputs.get(key) != inputs[key] for key in compared_keys):
                raise RuntimeError('Existing completed output has different or missing input/model provenance')
            print(json.dumps({'stage': 'completed_output_reused', 'meeting_id': mid}), flush=True)
            continue
        # Exporter/logging or allocator-limit fixes must not discard model work.
        # Model code/assets, inference parameters, library versions and actual
        # input audio remain in the checkpoint namespace; each batch additionally
        # rechecks every waveform/mask byte before reuse.
        semantic_inputs = {key: value for key, value in inputs.items()
                           if key not in ('runner_sha256', 'mps_high_watermark_ratio', 'mps_low_watermark_ratio')}
        cache = PRIVATE/'checkpoints'/str(mid)/fingerprint(semantic_inputs)
        cache.mkdir(parents=True, exist_ok=True)
        save(cache/('attempt-'+LOADED_RUNNER_SHA256+'.json'), inputs)
        embedding = CachedEmbedding(initial_embedding, cache/'embedding-batches')
        pipeline._embedding = embedding
        segmentation_path = cache/'segmentations.npz'
        full_stage_reused = {'segmentation': checkpoint_valid(segmentation_path),
                             'embeddings': checkpoint_valid(cache/'embeddings.npy')}
        def segmentations(this, file, hook=None):
            if checkpoint_valid(segmentation_path):
                with np.load(segmentation_path, allow_pickle=False) as saved:
                    value = SlidingWindowFeature(saved['data'], SlidingWindow(
                        start=float(saved['start']), duration=float(saved['duration']), step=float(saved['step'])))
                print(json.dumps({'stage': 'segmentation_checkpoint_reused', 'meeting_id': mid}), flush=True)
                return value
            value = original_segmentation(file, hook=hook)
            temporary = segmentation_path.with_suffix('.pending.npz')
            np.savez(temporary, data=value.data, start=value.sliding_window.start,
                     duration=value.sliding_window.duration, step=value.sliding_window.step)
            temporary.replace(segmentation_path)
            checkpoint_receipt(segmentation_path)
            return value
        embedding_path = cache/'embeddings.npy'
        def embeddings(this, file, binary_segmentations, exclude_overlap=False, hook=None):
            if checkpoint_valid(embedding_path):
                return np.load(embedding_path, allow_pickle=False)
            value = original_embeddings(file, binary_segmentations, exclude_overlap=exclude_overlap, hook=hook)
            temporary = embedding_path.with_suffix('.pending.npy')
            np.save(temporary, value, allow_pickle=False)
            temporary.replace(embedding_path)
            checkpoint_receipt(embedding_path)
            return value
        pipeline.get_segmentations = types.MethodType(segmentations, pipeline)
        pipeline.get_embeddings = types.MethodType(embeddings, pipeline)
        audio, rate = sf.read(str(audio_path), dtype='float32')
        began = time.perf_counter()
        last = {}
        def progress(step, artifact, file=None, total=None, completed=None):
            # Release unused GPU batch buffers before full-recording CPU AHC/VBx.
            if device == 'mps' and step == 'embeddings' and artifact is not None and completed is None:
                torch.mps.empty_cache()
            now = time.perf_counter()
            if now-last.get(step, 0) >= 30 or (total is not None and completed == total):
                status = {'meeting_id': mid, 'stage': step,
                          'completed': None if completed is None else int(completed),
                          'total': None if total is None else int(total),
                          'elapsed_seconds': now-began, 'embedding_batches_computed': embedding.computed,
                          'embedding_batches_reused': embedding.reused,
                          'process_peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
                if device == 'mps':
                    status['mps_driver_allocated_bytes'] = torch.mps.driver_allocated_memory()
                save(PRIVATE/'progress.json', status)
                print(json.dumps(status), flush=True)
                last[step] = now
        update_state(status='running_community_1', active_meeting_id=mid)
        print(json.dumps({'meeting_id': mid, 'stage': 'full_recording_start', 'audio_seconds': len(audio)/rate}), flush=True)
        result = pipeline({'waveform': torch.from_numpy(audio).unsqueeze(0), 'sample_rate': rate}, hook=progress)
        elapsed = time.perf_counter()-began
        def clean(annotation):
            return [{'start': turn.start, 'end': turn.end, 'speaker': speaker}
                    for turn, _, speaker in annotation.itertracks(yield_label=True)]
        output = {'provider': 'community-1', 'device': device, 'seconds': elapsed,
                  'initialization_seconds': initialization, 'protocol': inputs,
                  'segments': clean(result.exclusive_speaker_diarization),
                  'overlap_segments': clean(result.speaker_diarization),
                  'embedding_batches_computed': embedding.computed, 'embedding_batches_reused': embedding.reused,
                  'full_stage_checkpoints_reused': full_stage_reused,
                  'runtime_scope': ('resumed_attempt_only_not_fresh_full_meeting_throughput'
                                    if embedding.reused or any(full_stage_reused.values())
                                    else 'single_complete_meeting_attempt'),
                  'process_peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
        save(destination, output)
        save(PRIVATE/f'{mid}-completion.json', {'meeting_id': mid, 'seconds': elapsed,
              'output_sha256': sha(destination), 'segment_count': len(output['segments']),
              'input_audio_sha256': inputs['audio_sha256'], 'protocol': protocol})
        print(json.dumps({'meeting_id': mid, 'stage': 'complete', 'seconds': elapsed}), flush=True)
        del audio, result
        if device == 'mps':
            torch.mps.empty_cache()

    update_state(status='community_1_two_meetings_completed', active_meeting_id=None)


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        # Only the exception class goes into machine state; credentials never do.
        state_path = PRIVATE/'state.json'
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        if state.get('pid') == os.getpid():
            update_state(status='community_1_failed', error_type=type(error).__name__)
        raise
