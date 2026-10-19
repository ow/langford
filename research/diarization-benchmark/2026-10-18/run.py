"""Isolated full-meeting diarization experiment. Never writes to Supabase/archive.

Run with pipeline's Python for prepare/senko/openai, the isolated Python for
community. All large audio and cached API responses live under /private/tmp.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import wave

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SCRATCH = Path('/private/tmp/langford-diarization-bench')
MODEL = 'gpt-4o-transcribe-diarize'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, default=str) + '\n')
    temp.replace(path)


def load(path):
    return json.loads(path.read_text())


def encode(audio, target, start=None, duration=None, mp3=False):
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    cmd = ['ffmpeg', '-nostdin', '-loglevel', 'error', '-y']
    if start is not None:
        cmd += ['-ss', str(start)]
    cmd += ['-i', str(audio)]
    if duration is not None:
        cmd += ['-t', str(duration)]
    cmd += ['-ar', '16000', '-ac', '1']
    cmd += ['-c:a', 'libmp3lame', '-b:a', '48k'] if mp3 else ['-c:a', 'pcm_s16le']
    subprocess.run(cmd + [str(target)], check=True)


def prepare():
    from pipeline import config
    from pipeline.backfill.records import transcript_file, unit, voice_consensus
    from pipeline.speaker_evidence import label_key
    import psycopg2
    import numpy as np

    manifest = load(OUT / 'manifest.json')
    excluded = {m['id'] for m in manifest['meetings']}
    anchors, candidates = [], []
    with psycopg2.connect(config.DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute('''SELECT a.meeting_id,a.speaker_label,a.person_id,p.name,
                m.archive_path,m.video_url,m.meta
                FROM meeting_speaker_aliases a JOIN people p ON p.id=a.person_id
                JOIN meetings m ON m.id=a.meeting_id
                WHERE m.municipality_id=1 ORDER BY m.meeting_date DESC''')
            rows = cur.fetchall()
    for mid, label, pid, name, folder, recording, meta in rows:
        if mid in excluded:
            continue
        file = transcript_file(ROOT / folder)
        if not file:
            continue
        data = load(file)
        key = label_key(label)
        vector = data.get('speaker_centroids', {}).get(key)
        old = (meta or {}).get('speaker_centroids', {}).get(key)
        if vector is None or old is None or np.shape(vector) != np.shape(old) or not np.allclose(vector, old, atol=1e-6):
            continue
        vector = unit(vector)
        if vector is None:
            continue
        anchor = dict(recording=recording or str(file), person_id=pid, vector=vector)
        anchors.append(anchor)
        if pid in {1, 21, 23}:
            candidates.append((mid, name, file, data, key, anchor))
    references = []
    for target in [21, 1, 23]:
        for mid, name, file, data, key, anchor in candidates:
            if anchor['person_id'] != target:
                continue
            check = voice_consensus(anchor['vector'], anchors, anchor['recording'])
            if not check or check['person_id'] != target:
                continue
            options = [s for s in data['segments'] if label_key(s.get('speaker')) == key
                       and s.get('speaker_confidence', 0) >= .99
                       and s.get('end', 0) - s.get('start', 0) >= 9]
            if not options:
                continue
            segment = options[0]
            audio = file.with_suffix('.m4a')
            if not audio.exists():
                continue
            references.append(dict(person_id=target, name=name, meeting_id=mid,
                audio=str(audio.relative_to(ROOT)), start=segment['start']+.25,
                seconds=8, enrollment='existing alias + exact centroid lineage + three independent recording voice consensus; both benchmark meetings excluded',
                consensus=check))
            break
        else:
            raise RuntimeError(f'No independent machine reference for {target}')
    # Explicit self-introduction, official minutes and the existing 54-meeting
    # Lisa research manifest. Not one of the two target recordings.
    lisa = next((ROOT/'archive/langford/Council/2023/01').glob('*18c87b49*/Audio/*.m4a'))
    references.append(dict(person_id=353, name='Lisa Foxall', meeting_id=338,
        audio=str(lisa.relative_to(ROOT)), start=3968.44, seconds=7.2,
        enrollment='spoken self-introduction + official minutes + cross-meeting research manifest'))
    # Equal eight-second reference slots, separated by two seconds of silence.
    # All engines hear the same enrollment prefix; OpenAI also receives its
    # native known-speaker references on every API chunk.
    for index, ref in enumerate(references):
        wav = SCRATCH/'references'/f"{ref['person_id']}.wav"
        encode(ROOT/ref['audio'], wav, ref['start'], ref['seconds'])
        ref['sha256'] = hashlib.sha256(wav.read_bytes()).hexdigest()
        ref['prefix_start'] = index*10.
        ref['prefix_end'] = index*10.+ref['seconds']
    manifest['references'] = references
    manifest['prefix_seconds'] = len(references)*10.
    save(OUT/'manifest.json', manifest)
    for meeting in manifest['meetings']:
        started = time.perf_counter()
        mid = meeting['id']
        original = SCRATCH/str(mid)/'original.wav'
        joined = SCRATCH/str(mid)/'input.wav'
        encode(ROOT/meeting['audio'], original)
        if not joined.exists():
            with wave.open(str(joined), 'wb') as target:
                target.setnchannels(1); target.setsampwidth(2); target.setframerate(16000)
                for ref in references:
                    with wave.open(str(SCRATCH/'references'/f"{ref['person_id']}.wav"), 'rb') as source:
                        target.writeframes(source.readframes(source.getnframes()))
                    target.writeframes(b'\0' * int((10-ref['seconds'])*16000)*2)
                with wave.open(str(original), 'rb') as source:
                    while block := source.readframes(16000*30):
                        target.writeframes(block)
        print(json.dumps(dict(prepared=mid,seconds=round(time.perf_counter()-started,2))),flush=True)


def run_senko():
    import numpy as np
    import senko
    manifest = load(OUT/'manifest.json')
    t = time.perf_counter()
    diarizer = senko.Diarizer(device='auto', quiet=False)
    init = time.perf_counter()-t
    for m in manifest['meetings']:
        dest = OUT/'results'/f"{m['id']}-senko.json"
        if dest.exists():
            continue
        t = time.perf_counter()
        result = diarizer.diarize(str(SCRATCH/str(m['id'])/'input.wav'))
        elapsed = time.perf_counter()-t
        def clean(items):
            return [dict(start=float(s['start']),end=float(s['end']),speaker=s['speaker']) for s in items]
        save(dest,dict(provider='senko',model='senko-0.1.0/CAM++',seconds=elapsed,
            initialization_seconds=init,segments=clean(result['merged_segments']),
            raw_segments=clean(result['raw_segments']),
            speaker_centroids={k:np.asarray(v).tolist() for k,v in result['speaker_centroids'].items()}))
        print(json.dumps(dict(provider='senko',meeting_id=m['id'],seconds=elapsed)),flush=True)


def run_openai(workers=3, skip_chunks=()):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from openai import OpenAI
    from pipeline import config
    manifest = load(OUT/'manifest.json')
    client = OpenAI(api_key=config.OPENAI_API_KEY, timeout=1200, max_retries=0)
    refs = manifest['references']
    extra = dict(known_speaker_names=[f"person_{r['person_id']}" for r in refs],
        known_speaker_references=['data:audio/wav;base64,'+base64.b64encode(
            (SCRATCH/'references'/f"{r['person_id']}.wav").read_bytes()).decode() for r in refs])
    jobs = []
    for m in manifest['meetings']:
        duration = m['duration_seconds']+manifest['prefix_seconds']
        for i, start in enumerate(range(0, int(duration)+1, 600)):
            if start>=duration:
                continue
            jobs.append((m['id'], i, float(start), min(600.,duration-start)))
    jobs = [job for job in jobs if f'{job[0]}:{job[1]}' not in skip_chunks]
    def process(job):
        mid,index,start,duration = job
        dest = OUT/'results'/'openai-chunks'/f'{mid}-{index:03d}.json'
        if dest.exists():
            return load(dest)
        audio = SCRATCH/str(mid)/f'chunk-{index:03d}.mp3'
        encode(SCRATCH/str(mid)/'input.wav', audio, start, duration, mp3=True)
        assert audio.stat().st_size < 25_000_000
        t = time.perf_counter()
        started_at = time.time()
        with audio.open('rb') as stream:
            raw_response = client.audio.transcriptions.with_raw_response.create(file=stream,
                model=MODEL,response_format='diarized_json',chunking_strategy='auto',extra_body=extra)
            response = raw_response.parse()
        result = dict(meeting_id=mid,chunk=index,offset=start,requested_seconds=duration,
            api_started_at=started_at,api_finished_at=time.time(),
            elapsed_seconds=time.perf_counter()-t,model=MODEL,input_sha256=hashlib.sha256(audio.read_bytes()).hexdigest(),
            rate_limits={k:v for k,v in raw_response.headers.items() if k.startswith('x-ratelimit-')},
            reference_sha256={r['person_id']:r['sha256'] for r in refs},response=response.model_dump(mode='json'))
        save(dest,result)
        print(json.dumps(dict(provider='openai',meeting_id=mid,chunk=index,seconds=result['elapsed_seconds'],segments=len(result['response'].get('segments',[])))),flush=True)
        return result
    t = time.perf_counter()
    errors = []
    # Verify model/account access before scheduling the complete experiment.
    process(jobs[0])
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(process,job):job for job in jobs[1:]}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as error:
                job=futures[future]
                errors.append(dict(job=job,error=str(error)))
                print(json.dumps(errors[-1]),flush=True)
    save(OUT/'results'/'openai-run.json',dict(wall_seconds=time.perf_counter()-t,workers=workers,jobs=len(jobs),errors=errors))


def run_community():
    os.environ.setdefault('MPLCONFIGDIR', str(SCRATCH/'matplotlib'))
    os.environ.setdefault('PYANNOTE_METRICS_ENABLED','0')
    import torch
    import pickle
    import soundfile as sf
    from pyannote.audio import Pipeline
    from huggingface_hub import get_token
    torch.set_num_threads(4)
    if not get_token():
        raise RuntimeError('Community-1 needs local Hugging Face login and model access')
    t = time.perf_counter()
    pipeline = Pipeline.from_pretrained('pyannote/speaker-diarization-community-1',
        revision='3533c8cf8e369892e6b79ff1bf80f7b0286a54ee',token=get_token())
    device = 'mps' if torch.backends.mps.is_available() else 'cpu'
    pipeline.to(torch.device(device))
    init = time.perf_counter()-t
    print(json.dumps(dict(provider='community-1',stage='initialized',device=device,seconds=init)),flush=True)
    for m in load(OUT/'manifest.json')['meetings']:
        dest = OUT/'results'/f"{m['id']}-community.json"
        if dest.exists():
            continue
        audio, rate = sf.read(str(SCRATCH/str(m['id'])/'input.wav'),dtype='float32')
        print(json.dumps(dict(provider='community-1',meeting_id=m['id'],stage='starting',samples=len(audio))),flush=True)
        t = time.perf_counter()
        last_progress = {}
        def progress(step_name, artifact, file=None, total=None, completed=None):
            now = time.perf_counter()
            if now-last_progress.get(step_name, 0) >= 30 or (total is not None and completed == total):
                print(json.dumps(dict(provider='community-1',meeting_id=m['id'],stage=step_name,
                    completed=int(completed) if completed is not None else None,
                    total=int(total) if total is not None else None,elapsed=now-t)),flush=True)
                last_progress[step_name] = now
        output = pipeline({'waveform':torch.from_numpy(audio).unsqueeze(0),'sample_rate':rate},hook=progress)
        elapsed = time.perf_counter()-t
        # Preserve completed model output before JSON conversion, independently of exporter code.
        with (SCRATCH/str(m['id'])/'community-output.pkl').open('wb') as checkpoint:
            pickle.dump(output,checkpoint)
        def clean(annotation):
            return [dict(start=turn.start,end=turn.end,speaker=speaker)
                for turn, _, speaker in annotation.itertracks(yield_label=True)]
        save(dest,dict(provider='community-1',device=device,seconds=elapsed,
            torch_num_threads=torch.get_num_threads(),
            initialization_seconds=init,segments=clean(output.exclusive_speaker_diarization),
            overlap_segments=clean(output.speaker_diarization)))
        print(json.dumps(dict(provider='community-1',meeting_id=m['id'],seconds=elapsed)),flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=['prepare','senko','openai','community'])
    p.add_argument('--workers',type=int,default=3)
    p.add_argument('--skip-chunks',nargs='*',default=[],help='Chunk keys still running in another process; prevents duplicate requests')
    args=p.parse_args()
    if args.phase=='prepare':prepare()
    elif args.phase=='senko':run_senko()
    elif args.phase=='openai':run_openai(args.workers,args.skip_chunks)
    else:run_community()
