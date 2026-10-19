"""Independent exact-match lifecycle audit; no fuzzy vote matcher or deduplication.

Reads official minutes caches. Every formal mover-bounded motion is retained,
including repeated wording. Conflicting compatible body occurrences are held.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def normalize(value):
    return re.sub(r'[^a-z0-9]+', ' ', value.casefold()).strip()


def raw_motion_blocks(source):
    starts = list(re.finditer(r'(?im)^\s*\*{0,2}MOVED BY\s*:', source))
    for i, match in enumerate(starts):
        block = source[match.start():starts[i+1].start() if i+1 < len(starts) else len(source)]
        outcome = re.search(r'(?im)^\s*\*{0,2}(?:Motion\s+)?(CARRIED(?:\s+UNANIMOUSLY)?|NOT CARRIED|DEFEATED|WITHDRAWN|TABLED)\b[^\n]*', block)
        if not outcome:
            continue
        body = block[:outcome.start()]
        that = re.search(r'\bTHAT\b', body, re.I)
        if not that:
            continue
        yield {'motion_text': body[that.start():].strip(), 'result': outcome.group(1).upper(),
               'outcome_quote': outcome.group(0).strip(), 'source_block': block.strip()}


def analyze(proposal, meetings):
    by_id = {m['id']: m for m in meetings}
    cache = {}
    records = []
    for update in proposal['lifecycle_updates']:
        evidence = update['meta']['lifecycle_evidence']
        meeting = by_id[evidence['meeting_id']]
        folder = Path(meeting['archive_path']) if meeting.get('archive_path') else None
        if folder and not folder.is_absolute():
            folder = ROOT / folder
        source_file = folder / 'minutes.md' if folder else None
        record = {'matter_id': update['id'], 'motion_id': evidence['motion_id'], 'meeting_id': evidence['meeting_id'],
                  'target_motion_text': evidence['source_text'], 'status': 'persisted_motion_only'}
        if not source_file or not source_file.is_file():
            record['reason'] = 'official_minutes_cache_unavailable'
            records.append(record)
            continue
        if source_file not in cache:
            text = source_file.read_text()
            cache[source_file] = (text, list(raw_motion_blocks(text)))
        text, blocks = cache[source_file]
        matches = [b for b in blocks if normalize(b['motion_text']) == normalize(evidence['source_text'])]
        urls = []
        for companion in sorted((folder / 'Minutes').glob('*.url')):
            value = companion.read_text().strip()
            if value:
                urls.append(value)
        record.update({'source_file': str(source_file.relative_to(ROOT)),
            'source_sha256': hashlib.sha256(source_file.read_bytes()).hexdigest(),
            'source_urls': urls, 'exact_matches': len(matches)})
        if not matches:
            record['reason'] = 'no_exact_normalized_formal_motion_match'
        else:
            results = sorted({match['result'] for match in matches})
            # Identity/amount/negation equality is implied by whole-body exact normalization.
            # Unanimity adds precision but is compatible with a carried source outcome.
            success = {'CARRIED', 'CARRIED UNANIMOUSLY'}
            if set(results).issubset(success):
                record['status'] = 'official_minutes_exact'
                record['source_quotes'] = [{'motion_text': m['motion_text'], 'outcome_quote': m['outcome_quote']} for m in matches]
                record['results'] = results
            elif not set(results).intersection(success):
                record['status'] = 'contradicted'
                record['reason'] = 'exact_source_motion_has_no_carried_outcome'
                record['results'] = results
                record['source_quotes'] = [{'motion_text': m['motion_text'], 'outcome_quote': m['outcome_quote']} for m in matches]
            else:
                record['reason'] = 'repeated_wording_with_conflicting_outcomes'
                record['results'] = results
        records.append(record)
    from collections import Counter
    return {'mode': 'independent_read_only_exact_source_audit', 'summary': dict(Counter(r['status'] for r in records)), 'records': records}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--proposal', type=Path, required=True)
    parser.add_argument('--meetings', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(json.loads(args.proposal.read_text()), json.loads(args.meetings.read_text()))
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result['summary']))
