"""Cross-ASR self-introduction checks; no engine is treated as ground truth."""
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from analyze import enrollment

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
INTRO = re.compile(r"\b(?i:my name(?: is|'s)|I(?:'m| am))\s+([A-Z][\w'-]+(?:\s+[A-Z][\w'-]+){1,2})")


def read(path):
    return json.loads(path.read_text())


def normalized(value):
    return re.sub(r'[^a-z]', '', value.lower())


def dominant(segments, start, end, mapping):
    seconds = {}
    for segment in segments:
        overlap = max(0, min(end, segment['end']) - max(start, segment['start']))
        if overlap:
            pid = mapping.get(segment['speaker'], 'unresolved')
            seconds[pid] = seconds.get(pid, 0) + overlap
    if not seconds:
        return dict(person_id='no speech detected', share=0)
    pid = max(seconds, key=seconds.get)
    return dict(person_id=pid, share=seconds[pid] / sum(seconds.values()))


def main():
    manifest = read(HERE / 'manifest.json')
    prefix = manifest['prefix_seconds']
    refs = manifest['references']
    checks = []
    completion = {}
    for meeting in manifest['meetings']:
        mid = meeting['id']
        audio = ROOT / meeting['audio']
        raw = read(audio.with_name(audio.stem + '_raw_transcript.json'))
        raw = raw.get('segments', raw.get('sentences', [])) if isinstance(raw, dict) else raw
        cloud = []
        files = sorted((HERE / 'results/openai-chunks').glob(f'{mid}-*.json'))
        completion[str(mid)] = len(files)
        for path in files:
            chunk = read(path)
            cloud.extend(dict(start=s['start']+chunk['offset']-prefix,
                              end=s['end']+chunk['offset']-prefix,
                              text=s.get('text', ''), speaker=s['speaker'])
                         for s in chunk['response']['segments'])
        providers = dict(openai=(cloud, {f"person_{r['person_id']}": r['person_id'] for r in refs}))
        for kind in ('senko', 'community'):
            path = HERE / 'results' / f'{mid}-{kind}.json'
            if path.exists():
                data = read(path)
                mapping, _ = enrollment(data['segments'], refs)
                shifted = [dict(s, start=s['start']-prefix, end=s['end']-prefix) for s in data['segments']]
                providers[kind] = shifted, mapping
        for sentence in raw:
            match = INTRO.search(sentence.get('text', ''))
            if not match:
                continue
            name = match.group(1)
            start = sentence.get('start', sentence.get('start_time'))
            end = sentence.get('end', sentence.get('end_time'))
            # A second ASR must independently transcribe a matching introduction
            # nearby. Agreement is a contradiction signal, not a human label.
            corroboration = []
            for segment in cloud:
                if segment['start'] >= end+2 or segment['end'] <= start-2:
                    continue
                other = INTRO.search(segment['text'])
                if other and SequenceMatcher(None, normalized(name), normalized(other.group(1))).ratio() >= .8:
                    corroboration.append(other.group(1))
            if not corroboration:
                continue
            known = [r['person_id'] for r in refs
                     if SequenceMatcher(None, normalized(name), normalized(r['name'])).ratio() >= .8]
            expected = known[0] if len(known) == 1 else 'outside enrolled references'
            labels = {kind: dominant(segments, start, end, mapping)
                      for kind, (segments, mapping) in providers.items()}
            checks.append(dict(meeting_id=mid, start=start, end=end,
                               cached_asr_name=name, openai_asr_names=corroboration,
                               expected_person_id=expected, providers=labels))
    result = dict(method='Names explicitly self-introduced and corroborated by cached Parakeet and new OpenAI ASR; machine evidence only. Unresolved is abstention, not a wrong identity.',
                  completed_openai_chunks=completion, checks=checks)
    (HERE / 'identity_checks.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
