"""Extractive speech statements with raw-source and persisted-row provenance.

AI speaker guesses, aliases and recorded votes are never named utterance proof.
The private identity ledger is authoritative only while its exact source/row
identity tuple remains current. No audio/model calls or identity writes occur.
"""
import hashlib
import json
import math
import marshal
import re
from pathlib import Path

VERSION = 'source-bound-key-statements-v2'
TYPES = {'claim', 'proposal', 'objection', 'recommendation', 'financial', 'public_input'}


def _space(text):
    return ' '.join(str(text or '').split())


def _bounds(segment):
    if not isinstance(segment, dict):
        return None
    start = segment.get('start')
    end = segment.get('end')
    if start is None:
        start = segment.get('start_time')
    if end is None:
        end = segment.get('end_time')
    if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in (start, end)):
        return None
    return (start, end) if 0 <= start < end else None


def source_segments(data):
    value = data.get('segments', []) if isinstance(data, dict) else data
    return value if isinstance(value, list) else []


def format_refinement_transcript(data, source_sha256):
    """Keep source-array indexes and measured times, never invented offsets."""
    segments = source_segments(data)
    if not segments:
        return ''
    lines = [f'TRANSCRIPT_SOURCE_SHA256={source_sha256}']
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            lines.append(f'[source_index={index}; invalid_segment]')
            continue
        bounds = _bounds(segment)
        start, end = bounds if bounds else ('unknown', 'unknown')
        lines.append(f"[source_index={index}; start={start}; end={end}] {segment.get('speaker', 'Unknown')}: {segment.get('text', '')}")
    return '\n'.join(lines)


def load_statement_context(supabase, meeting_id, transcript_path):
    """Read only the original file, current rows, canonical people and ledger."""
    try:
        raw = Path(transcript_path).read_bytes()
        original = source_segments(json.loads(raw))
    except (OSError, ValueError, TypeError):
        return {'status': 'held', 'reason': 'structured_original_transcript_unavailable'}
    def fetch(table, columns, scoped):
        rows = []
        while True:
            query = supabase.table(table).select(columns)
            if scoped:
                query = query.eq('meeting_id', meeting_id)
            page = query.order('id').range(len(rows), len(rows)+999).execute().data or []
            rows.extend(page)
            if len(page) < 1000:
                return rows
    rows = fetch('transcript_segments', 'id,meeting_id,person_id,speaker_name,start_time,end_time,text_content', True)
    people = fetch('people', 'id,name', False)
    try:
        receipts = fetch('transcript_identity_evidence', 'id,segment_id,meeting_id,person_id,source_run,after_row,status,reverted_at,validator_sha256,input_sha256', True)
    except Exception:
        # Content may still be retained anonymously. No legacy name fallback.
        receipts = []
    return {'status': 'available', 'meeting_id': meeting_id,
            'source_sha256': hashlib.sha256(raw).hexdigest(), 'segments': original,
            'stored_segments': rows, 'people': people, 'identity_receipts': receipts,
            '_transcript_path': str(Path(transcript_path).resolve())}


def bind_key_statement(statement, context):
    """Resolve actual source tuples; source-array and DB indexes are unrelated."""
    def held(reason):
        return {'status': 'held', 'reason': reason, 'validator_version': VERSION}
    if statement.get('evidence_kind') != 'transcript':
        return held('spoken_statement_requires_transcript_not_recorded_vote_or_summary')
    if context.get('status') != 'available':
        return held(context.get('reason', 'source_context_unavailable'))
    if statement.get('transcript_source_sha256') != context['source_sha256']:
        return held('original_transcript_hash_missing_or_changed')
    indexes = statement.get('source_segment_indexes')
    if not isinstance(indexes, list) or not indexes or any(type(i) is not int for i in indexes):
        return held('source_indexes_required')
    if indexes != list(range(indexes[0], indexes[-1]+1)) or indexes[0] < 0 or indexes[-1] >= len(context['segments']):
        return held('source_indexes_not_unique_contiguous_in_range')
    selected = [context['segments'][i] for i in indexes]
    if any(not isinstance(s, dict) or not isinstance(s.get('speaker', 'Unknown'), str) for s in selected):
        return held('malformed_original_segment')
    labels = {s.get('speaker', 'Unknown') for s in selected}
    if len(labels) != 1:
        return held('source_quote_crosses_raw_speakers')
    quote = statement.get('source_quote')
    if not isinstance(quote, str) or not _space(quote):
        return held('exact_quote_absent_from_original_selected_segments')
    quote = _space(quote)
    pattern = (r'(?<!\w)' if re.match(r'\w', quote[0]) else '') + re.escape(quote) + (r'(?!\w)' if re.match(r'\w', quote[-1]) else '')
    if not re.search(pattern, _space(' '.join(s.get('text', '') for s in selected))):
        return held('exact_quote_absent_from_original_selected_segments')
    if statement.get('statement_type') not in TYPES:
        return held('unsupported_statement_type')
    matched, original_bindings = [], []
    for index, segment in zip(indexes, selected):
        bounds = _bounds(segment)
        if not bounds or not _space(segment.get('text')):
            return held('invalid_original_segment')
        signature = (bounds, segment.get('text'))
        if sum((_bounds(s), s.get('text')) == signature for s in context['segments'] if isinstance(s, dict)) != 1:
            return held('original_source_tuple_not_unique')
        candidates = [row for row in context['stored_segments']
                      if row.get('meeting_id') == context['meeting_id'] and _bounds(row)
                      and row['start_time'] <= bounds[0] < bounds[1] <= row['end_time']
                      and _space(segment['text']) in _space(row.get('text_content'))]
        if len(candidates) != 1:
            return held('persisted_source_tuple_missing_or_ambiguous')
        matched.append(candidates[0])
        original_bindings.append({'source_index': index, 'segment_id': candidates[0]['id'],
                                  'start': bounds[0], 'end': bounds[1],
                                  'speaker': segment.get('speaker', 'Unknown'), 'text': segment['text']})
    rows = {r['id']: r for r in matched}
    admitted, evidence_ids, receipt_hashes = [], [], []
    identity_fields = ('id', 'meeting_id', 'person_id', 'speaker_name', 'start_time', 'end_time', 'text_content')
    for row in rows.values():
        valid = [receipt for receipt in context.get('identity_receipts', [])
                 if receipt.get('status') == 'applied' and receipt.get('reverted_at') is None
                 and receipt.get('segment_id') == row['id'] and receipt.get('meeting_id') == context['meeting_id']
                 and receipt.get('person_id') is not None and receipt.get('person_id') == row.get('person_id')
                 and receipt.get('source_run', {}).get('meeting_id') == context['meeting_id']
                 and receipt.get('source_run', {}).get('transcript_sha256') == context['source_sha256']
                 and all(receipt.get('after_row', {}).get(key) == row.get(key) for key in identity_fields)
                 and re.fullmatch('[0-9a-f]{64}', receipt.get('validator_sha256') or '')
                 and re.fullmatch('[0-9a-f]{64}', receipt.get('input_sha256') or '')]
        if not valid:
            admitted.append(None)
        else:
            admitted.append(row['person_id'])
            evidence_ids.extend(receipt['id'] for receipt in valid)
            receipt_hashes.extend(hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(',', ':')).encode()).hexdigest() for receipt in valid)
    pid = admitted[0] if admitted and admitted[0] is not None and len(set(admitted)) == 1 else None
    person = next((p for p in context.get('people', []) if p['id'] == pid), None)
    if person and sum(_space(p['name']).casefold() == _space(person['name']).casefold() for p in context['people']) != 1:
        person = None
    if not person:
        pid = None
        evidence_ids = []
        receipt_hashes = []
    raw_label = next(iter(labels))
    public_label = raw_label if re.fullmatch(r'speaker_[0-9]+', raw_label, re.IGNORECASE) else 'Unidentified speaker'
    data = {'speaker_name': person['name'] if person else public_label, 'person_id': pid,
            'statement_type': statement['statement_type'], 'statement_text': quote,
            'context': statement.get('context'), 'source_segment_ids': list(rows),
            'start_time': _bounds(selected[0])[0]}
    evidence = {'validator_version': VERSION, 'transcript_source_sha256': context['source_sha256'],
                'source_segment_indexes': indexes, 'source_segment_ids': list(rows),
                'source_quote_sha256': hashlib.sha256(quote.encode()).hexdigest(),
                'identity_receipt_ids': sorted(set(evidence_ids)),
                'identity_receipt_sha256s': sorted(set(receipt_hashes)),
                'identity_status': 'admitted_source_bound_identity' if person else 'unlinked_no_current_identity_admission'}
    return {'status': 'source_supported', 'data': data, 'evidence': evidence,
            'source_binding': {'raw_segments': original_bindings, 'expected_segments': list(rows.values())}}



def publish_key_statement(supabase, meeting_id, agenda_item_id, supported, context):
    """One service-only transaction validates, deduplicates and publishes proof."""
    if hashlib.sha256(Path(context['_transcript_path']).read_bytes()).hexdigest() != context['source_sha256']:
        raise RuntimeError('Original statement source changed before publication')
    payload = {'meeting_id': meeting_id, 'agenda_item_id': agenda_item_id,
               'statement': supported['data'], 'transcript_source_sha256': context['source_sha256'],
               'source_segment_count': len(context['segments']),
               **supported['source_binding'], 'identity_receipt_ids': supported['evidence']['identity_receipt_ids'],
               'validator_version': VERSION, 'validator_sha256': VALIDATOR_SHA256}
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    result = supabase.rpc('publish_source_bound_key_statement', {
        'p_input_canonical_json': encoded, 'p_input_sha256': hashlib.sha256(encoded.encode()).hexdigest(),
    }).execute().data
    if not isinstance(result, dict) or result.get('status') not in {'published', 'already_published'}:
        raise RuntimeError('Atomic source-bound statement publication held')
    return result


# Hash the code/defaults actually loaded by this worker, not newer source files.
VALIDATOR_SHA256 = hashlib.sha256(
    VERSION.encode()+json.dumps(sorted(TYPES)).encode()+b''.join(
        marshal.dumps(value.__code__)+json.dumps({'defaults':value.__defaults__, 'kwdefaults':value.__kwdefaults__},
                                                sort_keys=True).encode()
        for name,value in sorted(globals().items())
        if callable(value) and getattr(value, '__module__', None)==__name__ and hasattr(value,'__code__'))
).hexdigest()
