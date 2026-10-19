"""Backfill cached transcripts and explicitly named votes without replacing records.

Run from apps/pipeline: python -m pipeline.backfill.records --report /tmp/plan.json
Add --apply and optionally --limit for an inspected pilot before the full run.
No transcription or model APIs are used. Existing transcripts/votes are preserved.
"""
from __future__ import annotations

import argparse
import collections
from datetime import date
from difflib import SequenceMatcher
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor, Json, execute_values

from pipeline import config, parser
from pipeline.paths import BASE_DIR
from pipeline.speaker_evidence import label_key, has_temporal_support

ROOT = Path(BASE_DIR)
EXCLUDED = ('_raw_transcript', '_segments', '_benchmark', '_gemini_speakers')


def transcript_file(folder):
    files = sorted(p for p in (folder / 'Audio').glob('*.json') if not any(x in p.name for x in EXCLUDED))
    return files[0] if len(files) == 1 else None


def unit(vector):
    v = np.asarray(vector, dtype=float)
    if v.ndim != 1 or len(v) != 192 or not np.all(np.isfinite(v)) or not np.linalg.norm(v):
        return None
    return v / np.linalg.norm(v)


def voice_consensus(vector, anchors, exclude_recording=None):
    """Require three distinct recordings, high similarity and separation from alternatives."""
    v = unit(vector)
    if v is None:
        return None
    scored = sorted([(float(v @ a['vector']), a['person_id'], a['recording'])
                     for a in anchors if a['recording'] != exclude_recording], reverse=True)
    seen, best = set(), []
    for similarity, person, recording in scored:
        if recording in seen:
            continue
        seen.add(recording)
        best.append((similarity, person, recording))
        if len(best) == 3:
            break
    if len(best) < 3 or len({x[1] for x in best}) != 1 or best[-1][0] < .90:
        return None
    person = best[0][1]
    alternative = max((s for s, p, _ in scored if p != person), default=0)
    if best[-1][0] - alternative < .05:
        return None
    return {'person_id': person, 'similarity': best[-1][0], 'margin': best[-1][0] - alternative}


def normalized(text):
    return ' '.join(re.findall(r'[a-z0-9]+', (text or '').lower()))


def explicit_vote_blocks(minutes):
    """Parse only named choices adjacent to a motion result. CARRIED supplies no names."""
    starts = list(re.finditer(r'(?:\*\*)?MOVED\s+(?:BY\s*)?:', minutes, re.I))
    for i, start in enumerate(starts):
        block = minutes[start.end():starts[i + 1].start() if i + 1 < len(starts) else len(minutes)]
        outcome = re.search(r'Motion\s+(CARRIED(?:\s+UNANIMOUSLY)?|DEFEATED|WITHDRAWN)', block, re.I)
        seconded = re.search(r'SECONDED\s*(?:BY\s*)?:[^\n]*\n', block, re.I)
        if not outcome or not seconded or seconded.end() > outcome.start():
            continue
        text = block[seconded.end():outcome.start()]
        # The first result ends the motion. Only nearby, explicitly labelled vote lines qualify.
        after = block[outcome.end():]
        choices = []
        for line in after.splitlines()[:9]:
            clean = re.sub(r'[*_>]', '', line).strip()
            prefix = re.match(r'(OPPOSED|IN FAVOU?R|AGAINST|ABSTAINED?)\s*:\s*(.+)', clean, re.I)
            suffix = re.match(r'((?:Mayor|Councillors?)\s+.+?)\s+(opposed|voted against|voted in favou?r|abstained)\b', clean, re.I)
            if prefix:
                verb, names = prefix.groups()
            elif suffix:
                names, verb = suffix.groups()
            else:
                continue
            names = re.split(r'\s+\d+(?:\.\d+)*\.?\s+', names)[0]
            vote = 'Yes' if re.search(r'favou?r', verb, re.I) else 'Abstain' if re.search('abstain', verb, re.I) else 'No'
            choices.append((names, vote, clean[:600]))
        if choices:
            yield {'text': text, 'result': outcome[1].upper(), 'choices': choices}


def match_motion(text, motions):
    clean = normalized(text)
    if len(clean) < 35:
        return None
    scores = sorted([(SequenceMatcher(None, clean, normalized(m['text_content']), autojunk=False).ratio(), m['id']) for m in motions], reverse=True)
    if not scores or scores[0][0] < .78 or (len(scores) > 1 and scores[0][0] - scores[1][0] < .08):
        return None
    return scores[0][1]


def named_people(names, people):
    # Explicitly named surnames must resolve uniquely to an existing permanent person ID.
    found = []
    surnames = collections.defaultdict(list)
    for p in people:
        surnames[p['name'].split()[-1].lower()].append(p)
    for surname, candidates in surnames.items():
        if len(candidates) == 1 and re.search(r'\b' + re.escape(surname) + r'\b', names, re.I):
            found.append(candidates[0]['id'])
    # Any unrecognized name invalidates the line rather than partially recovering a vote list.
    residual = names
    for surname in surnames:
        residual = re.sub(r'\b' + re.escape(surname) + r'\b', '', residual, flags=re.I)
    residual = re.sub(r'\b(?:Mayor|Councillors?|and|the)\b|\b[A-Z]\.|[\s,.;:&-]', '', residual, flags=re.I)
    return found if not residual else []


def load_data(connection):
    with connection.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT m.*, (SELECT count(*) FROM transcript_segments t WHERE t.meeting_id=m.id) segment_count FROM meetings m WHERE municipality_id=1 ORDER BY meeting_date DESC,id")
        meetings = list(cur.fetchall())
        cur.execute('SELECT a.*,p.name FROM meeting_speaker_aliases a JOIN people p ON p.id=a.person_id JOIN meetings m ON m.id=a.meeting_id WHERE m.municipality_id=1')
        aliases = list(cur.fetchall())
        cur.execute("SELECT p.id,p.name,m.start_date,m.end_date FROM people p JOIN memberships m ON m.person_id=p.id JOIN organizations o ON o.id=m.organization_id WHERE o.municipality_id=1 AND o.classification='Council'")
        members = list(cur.fetchall())
        cur.execute('SELECT mo.id,mo.meeting_id,mo.text_content,mo.result FROM motions mo JOIN meetings m ON m.id=mo.meeting_id WHERE m.municipality_id=1')
        motions = list(cur.fetchall())
    with connection.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('SELECT id,name FROM people')
        people = list(cur.fetchall())
    return meetings, aliases, members, motions, people


def plan_backfill(connection):
    meetings, aliases, members, motions, people = load_data(connection)
    alias_by_meeting, motions_by_meeting = collections.defaultdict(list), collections.defaultdict(list)
    for a in aliases:
        alias_by_meeting[a['meeting_id']].append(a)
    for m in motions:
        motions_by_meeting[m['meeting_id']].append(m)
    files, anchors = {}, []
    for meeting in meetings:
        path = (ROOT / (meeting['archive_path'] or 'missing')).resolve()
        if not path.is_relative_to(ROOT / 'archive' / 'langford') or (path / 'shared_media.json').exists():
            continue
        file = transcript_file(path)
        if file is None:
            continue
        try:
            data = json.loads(file.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or not data.get('segments'):
            continue
        files[meeting['id']] = (file, data)
        old = (meeting['meta'] or {}).get('speaker_centroids', {})
        recording = meeting['video_url'] or str(file)
        for alias in alias_by_meeting[meeting['id']]:
            key = label_key(alias['speaker_label'])
            new = data.get('speaker_centroids', {}).get(key)
            prior = old.get(key)
            if new is not None and prior is not None and np.shape(new) == np.shape(prior) and np.allclose(new, prior, atol=1e-6):
                vector = unit(new)
                if vector is not None:
                    anchors.append({'recording': recording, 'meeting_id': meeting['id'], 'person_id': alias['person_id'], 'vector': vector})
    # Only identities with >=5 successful independent checks, no false positives or negatives
    # among accepted predictions, can be assigned to new transcript rows.
    correct, errors = collections.defaultdict(set), set()
    for anchor in anchors:
        result = voice_consensus(anchor['vector'], anchors, anchor['recording'])
        if not result:
            continue
        predicted, actual = result['person_id'], anchor['person_id']
        if predicted == actual:
            correct[actual].add(anchor['recording'])
        else:
            errors.update((actual, predicted))
    council_ids = {m['id'] for m in members}
    eligible = {p for p, recordings in correct.items() if len(recordings) >= 5 and p not in errors and p in council_ids}
    summary = {'voice_anchors': len(anchors), 'voice_validation_correct': {p: len(recordings) for p, recordings in correct.items()}, 'voice_conflicted_people': sorted(errors), 'voice_eligible_people': sorted(eligible), 'transcripts': [], 'votes': [], 'skipped': []}
    plans = []
    for meeting in meetings:
        mid = meeting['id']
        folder = (ROOT / (meeting['archive_path'] or 'missing')).resolve()
        if not folder.is_relative_to(ROOT / 'archive' / 'langford') or meeting['meeting_date'] > date.today():
            continue
        active = [m for m in members if (not m['start_date'] or m['start_date'] <= meeting['meeting_date']) and (not m['end_date'] or m['end_date'] >= meeting['meeting_date'])]
        active_ids = {m['id'] for m in active}
        plan = {'meeting_id': mid, 'rows': [], 'votes': [], 'motion_evidence': {}}
        if meeting['segment_count'] == 0 and mid in files:
            file, data = files[mid]
            speaker_map = {}
            recording = meeting['video_url'] or str(file)
            for key, vector in data.get('speaker_centroids', {}).items():
                match = voice_consensus(vector, anchors, recording)
                if match and match['person_id'] in eligible & active_ids:
                    speaker_map[key] = match
            people_names = {m['id']: m['name'] for m in active}
            for index, seg in enumerate(parser.extract_transcript_segments(str(file))):
                start, end = seg['start_time'], seg['end_time']
                if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or not math.isfinite(start) or not math.isfinite(end) or start < 0 or not start < end <= 24 * 3600 or not seg['text'].strip():
                    continue
                identity = speaker_map.get(label_key(seg['speaker'])) if has_temporal_support(data['segments'][index]) else None
                pid = identity['person_id'] if identity else None
                plan['rows'].append((mid, pid, people_names[pid] if pid else seg['speaker'], start, end, seg['text'], 'VOICE_CONSENSUS_BACKFILL' if pid else 'CACHED_TRANSCRIPT_BACKFILL'))
            plan['transcript_evidence'] = {'source_path': str(file.relative_to(ROOT)), 'sha256': hashlib.sha256(file.read_bytes()).hexdigest(), 'speaker_matches': speaker_map}
            summary['transcripts'].append({'meeting_id': mid, 'date': str(meeting['meeting_date']), 'segments': len(plan['rows']), 'attributed_segments': sum(r[1] is not None for r in plan['rows']), 'people_seconds': dict(collections.Counter({pid: sum(r[4]-r[3] for r in plan['rows'] if r[1]==pid) for pid in {r[1] for r in plan['rows'] if r[1] is not None}}))})
        elif meeting['segment_count'] == 0 and (folder / 'shared_media.json').exists():
            summary['skipped'].append({'meeting_id': mid, 'reason': 'Shared recording needs verified meeting boundaries'})
        minutes = folder / 'minutes.md'
        if minutes.exists() and motions_by_meeting[mid]:
            source = minutes.read_text()
            evidence_seen = set()
            for block in explicit_vote_blocks(source):
                motion_id = match_motion(block['text'], motions_by_meeting[mid])
                if motion_id is None:
                    continue
                for names, vote, excerpt in block['choices']:
                    if vote == 'No' and 'UNANIMOUS' in block['result']:
                        continue
                    for pid in named_people(names, people):
                        key = (motion_id, pid, vote)
                        if key in evidence_seen:
                            continue
                        evidence_seen.add(key)
                        plan['votes'].append((motion_id, pid, vote))
                        evidence = {'person_id': pid, 'vote': vote, 'excerpt': excerpt, 'source_path': str(minutes.relative_to(ROOT)), 'minutes_url': meeting['minutes_url'], 'source_sha256': hashlib.sha256(source.encode()).hexdigest(), 'method': 'explicit_named_vote', 'partial_record': True, 'source_motion_text': normalized(block['text'])[:1800], 'matched_motion_text': next(m['text_content'] for m in motions_by_meeting[mid] if m['id'] == motion_id)}
                        plan['motion_evidence'].setdefault(motion_id, []).append(evidence)
                        summary['votes'].append({'meeting_id': mid, 'motion_id': motion_id, **evidence})
        # Do not apply conflicting named choices for the same motion/person.
        choices = collections.defaultdict(set)
        for motion, person, vote in plan['votes']:
            choices[(motion, person)].add(vote)
        plan['votes'] = [v for v in plan['votes'] if len(choices[v[:2]]) == 1]
        if plan['rows'] or plan['votes']:
            plans.append(plan)
    return plans, summary


def apply_plan(connection, plans):
    counts = collections.Counter()
    for index, plan in enumerate(plans, 1):
        with connection:
            with connection.cursor() as cur:
                mid = plan['meeting_id']
                cur.execute('SELECT id FROM meetings WHERE id=%s AND municipality_id=1 FOR UPDATE', (mid,))
                if cur.fetchone() is None:
                    raise RuntimeError(f'Meeting {mid} disappeared')
                if plan['rows']:
                    cur.execute('SELECT 1 FROM transcript_segments WHERE meeting_id=%s LIMIT 1', (mid,))
                    if cur.fetchone() is None:
                        execute_values(cur, 'INSERT INTO transcript_segments (meeting_id,person_id,speaker_name,start_time,end_time,text_content,attribution_source) VALUES %s', plan['rows'], page_size=300)
                        cur.execute("UPDATE meetings SET has_transcript=true,meta=coalesce(meta,'{}'::jsonb)||jsonb_build_object('cached_transcript_backfill',%s::jsonb) WHERE id=%s", (Json(plan['transcript_evidence']), mid))
                        counts['transcript_meetings'] += 1
                        counts['transcript_segments'] += len(plan['rows'])
                for motion, person, vote in plan['votes']:
                    cur.execute('INSERT INTO votes (motion_id,person_id,vote) VALUES (%s,%s,%s) ON CONFLICT (motion_id,person_id) DO NOTHING RETURNING id', (motion, person, vote))
                    if cur.fetchone():
                        counts['votes'] += 1
                        cur.execute("UPDATE motions SET meta=coalesce(meta,'{}'::jsonb)||jsonb_build_object('named_vote_backfill',%s::jsonb,'individual_vote_coverage','named_only') WHERE id=%s AND meeting_id=%s", (Json(plan['motion_evidence'][motion]), motion, mid))
        if index % 10 == 0 or index == len(plans):
            print(json.dumps({'completed_meetings': index, 'total_meetings': len(plans), 'applied': dict(counts)}), flush=True)
    return dict(counts)


def main():
    argp = argparse.ArgumentParser(description=__doc__)
    argp.add_argument('--report', type=Path, required=True)
    argp.add_argument('--apply', action='store_true')
    argp.add_argument('--limit', type=int)
    args = argp.parse_args()
    if args.limit is not None and args.limit < 1:
        argp.error('--limit must be positive')
    connection = psycopg2.connect(config.DATABASE_URL)
    try:
        plans, summary = plan_backfill(connection)
        connection.rollback()
        args.report.write_text(json.dumps(summary, indent=2, default=str) + '\n')
        print(json.dumps({'eligible_voice_people': summary['voice_eligible_people'], 'transcript_meetings': len(summary['transcripts']), 'segments': sum(x['segments'] for x in summary['transcripts']), 'attributed_segments': sum(x['attributed_segments'] for x in summary['transcripts']), 'named_vote_candidates': len(summary['votes']), 'skipped': len(summary['skipped'])}))
        if args.apply:
            print(json.dumps({'applied': apply_plan(connection, plans[:args.limit] if args.limit else plans)}))
    finally:
        connection.close()


if __name__ == '__main__':
    main()
