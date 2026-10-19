"""Repo-owned, source-bound full transcriptions; never an unbound text alias.

The original PDF, parser objects and offsets remain immutable. A verified view
only supplies an exact full-body comparison for an already proved occurrence.
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import platform
import re

from .source_claims import digest, valid_inventory, project_claim
from .source_occurrences import own_formal_envelopes, envelope_proof

STORE = Path(__file__).parent / 'data' / 'native-transcriptions' / 'v1'
MANIFEST_SHA256 = '68c172624b7b7ca9bc597cddc0f5055ae9645cf54e70158842463ba94ac55caf'


def sha(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def store_inventory():
    if STORE.is_symlink():
        return [{'file': '.', 'sha256': None, 'symlink': True}]
    return [({'file': str(path.relative_to(STORE)), 'sha256': None, 'symlink': True}
             if path.is_symlink() else {'file': str(path.relative_to(STORE)), 'sha256': sha(path.read_bytes())})
            for path in sorted(STORE.rglob('*')) if path.is_file() or path.is_symlink()]


def _asset(name):
    path = STORE / name
    parents = [parent for parent in path.parents if parent == STORE or STORE in parent.parents]
    if (STORE.is_symlink() or path.is_symlink() or any(parent.is_symlink() for parent in parents)
            or not path.resolve().is_relative_to(STORE.resolve()) or not path.is_file()):
        raise ValueError('untrusted_transcription_asset')
    return path


def _store():
    manifest_bytes = _asset('manifest.json').read_bytes()
    if sha(manifest_bytes) != MANIFEST_SHA256:
        raise ValueError('transcription_manifest_changed')
    manifest = json.loads(manifest_bytes)
    if manifest['schema'] != 'trusted-native-transcriptions-v1' or manifest['version'] != 1 or manifest['enrollment'] != 'source-only-bound-comparison':
        raise ValueError('transcription_store_not_enrolled')
    actual = [row for row in store_inventory() if row['file'] != 'manifest.json']
    if actual != manifest['files']:
        raise ValueError('transcription_store_inventory_changed')
    for row in actual:
        _asset(row['file'])
    keys = [json.dumps(row['discovery_key'], sort_keys=True) for row in manifest['receipts']]
    if len(keys) != len(set(keys)):
        raise ValueError('duplicate_transcription_discovery_key')
    for name, expected in manifest['source_reviews'].items():
        if sha(_asset(name).read_bytes()) != expected:
            raise ValueError('transcription_review_changed')
    return manifest


def renderer_dependency_inventory():
    try:
        import fitz
        import pymupdf
        folder = Path(pymupdf.__file__).parent
        return {'pymupdf_version': fitz.VersionBind, 'mupdf_version': fitz.VersionFitz,
                'python_version': platform.python_version(), 'platform': platform.platform(), 'machine': platform.machine(),
                'pymupdf_wrapper_sha256': sha(Path(pymupdf.__file__).read_bytes()),
                'dependency_files': [{'basename': name, 'sha256': sha((folder/name).read_bytes())}
                                     for name in ('_extra.so', '_mupdf.so', 'libmupdf.dylib', 'libmupdfcpp.so')]}
    except (ImportError, OSError) as error:
        return {'status': 'renderer_dependencies_unavailable', 'error_type': type(error).__name__}


def _renderer_environment():
    expected = json.loads(_asset('render-environment.json').read_bytes())
    actual = renderer_dependency_inventory()
    if any(actual.get(key) != expected[key] for key in ('pymupdf_version', 'mupdf_version', 'python_version',
            'platform', 'machine', 'pymupdf_wrapper_sha256', 'dependency_files')):
        raise ValueError('transcription_renderer_environment_changed')
    return expected


def _geometry(document):
    pages, lines = [], []
    cursor = 0
    for page_index, page in enumerate(document):
        words = page.get_text('words', sort=False)
        groups = defaultdict(list)
        for index, word in enumerate(words):
            groups[(word[5], word[6])].append((index, word))
        page_lines = []
        for (block, line), items in groups.items():
            items.sort(key=lambda item: (item[1][0], item[1][7]))
            quote = ' '.join(item[1][4] for item in items)
            bbox = [min(item[1][0] for item in items), min(item[1][1] for item in items),
                    max(item[1][2] for item in items), max(item[1][3] for item in items)]
            page_lines.append({'page': page_index+1, 'native_block': block, 'native_line': line,
                               'bbox': bbox, 'quote': quote, 'raw_word_indices': [item[0] for item in items]})
        page_lines.sort(key=lambda line: (round(line['bbox'][1], 1), line['bbox'][0]))
        for line in page_lines:
            line.update(diagnostic_line_index=len(lines), diagnostic_geometry_text_start=cursor,
                        diagnostic_geometry_text_end=cursor+len(line['quote']))
            cursor += len(line['quote'])+1
            lines.append(line)
        pages.append({'page': page_index+1, 'width': page.rect.width, 'height': page.rect.height,
                      'raw_words': words, 'native_line_count': len(page_lines)})
    return pages, lines


def _verify_projected_geometry(value, lines):
    if isinstance(value, dict):
        if 'diagnostic_line_index' in value:
            index = value['diagnostic_line_index']
            if not isinstance(index, int) or not 0 <= index < len(lines):
                raise ValueError('transcription_geometry_out_of_bounds')
            actual = lines[index]
            for key, expected in value.items():
                if key in actual and actual[key] != expected:
                    raise ValueError('transcription_native_geometry_changed')
            if 'exact_original_quote_sha256' in value and sha(actual['quote']) != value['exact_original_quote_sha256']:
                raise ValueError('transcription_native_fragment_changed')
        for child in value.values():
            _verify_projected_geometry(child, lines)
    elif isinstance(value, list):
        for child in value:
            _verify_projected_geometry(child, lines)


def _verify_witness(witness, source, document, pages, lines):
    scope = witness['source_scope']
    if (scope['original_pdf_sha256'] != source['source_sha256'] or scope['original_public_url'] != source['source_url']
            or scope['native_source_date'] != source['local_date'] or scope['source_format'] != source['source_format']
            or scope['page_count'] != len(document)):
        raise ValueError('transcription_source_scope_changed')
    checks = [(sha(source['text']), 'ordinary_cleaned_text_sha256_hash_only'),
              (digest(pages), 'original_complete_pdf_native_pages_geometry_sha256_hash_only'),
              (digest(lines), 'original_complete_pdf_geometry_lines_sha256_hash_only'),
              (digest(source['blocks']), 'ordinary_complete_parsed_raw_blocks_sha256_hash_only'),
              (digest(source['formal_occurrence_inventory']), 'original_parser_formal_inventory_sha256_hash_only')]
    for actual, key in checks:
        if actual != witness[key]:
            raise ValueError('transcription_source_inventory_changed:'+key)
    inventory = witness['semantic_inventory']
    if digest(inventory) != witness['minimized_semantic_inventory_sha256']:
        raise ValueError('transcription_semantic_inventory_changed')
    introductions = inventory['original_formal_introductions']
    if len(introductions) != witness['all_original_introductions_retained'] or len({item['diagnostic_envelope_id'] for item in introductions}) != len(introductions):
        raise ValueError('transcription_introductions_incomplete')
    # Independently account for every native formal introducer and seconder,
    # including a pending main which has no standalone parsed completed block.
    native_movers = {line['diagnostic_line_index'] for line in lines if re.search(r'\bMOVED\s+BY\s*:', line['quote'], re.I)}
    native_seconders = {line['diagnostic_line_index'] for line in lines if re.search(r'\bSECONDED\s*:', line['quote'], re.I)}
    declared_movers = {item['introduction']['diagnostic_line_index'] for item in introductions}
    declared_seconders = {item['seconder_line']['diagnostic_line_index'] for item in introductions if item.get('seconder_line')}
    if native_movers != declared_movers or native_seconders != declared_seconders:
        raise ValueError('transcription_native_formal_inventory_incomplete')
    for ordinal, item in enumerate(introductions):
        fragments = [lines[boundary['diagnostic_line_index']] for boundary in item['complete_native_body_fragment_boundaries']]
        if digest(fragments) != item['complete_native_body_fragments_sha256_hash_only'] or not item['all_original_body_fragments_accounted_for']:
            raise ValueError('transcription_native_body_inventory_changed')
        if item['source_sequence_ordinal'] != ordinal:
            raise ValueError('transcription_introduction_order_changed')
        previous = introductions[ordinal-1]['introduction']['diagnostic_line_index'] if ordinal else None
        following = introductions[ordinal+1]['introduction']['diagnostic_line_index'] if ordinal+1 < len(introductions) else None
        if item['previous_original_introduction_line'] != previous or item['next_original_introduction_line'] != following:
            raise ValueError('transcription_original_adjacency_changed')
    _verify_projected_geometry(inventory, lines)


def _verify_receipt(receipt, source, block, document, lines, witness):
    raw = receipt['raw_occurrence_identity']
    original = receipt['original_public_source']
    discovery = receipt['discovery_key']
    if (original['pdf_sha256'] != source['source_sha256'] or original['url'] != source['source_url']
            or original['source_format'] != source['source_format'] or original['native_date'] != source['local_date']
            or original['ordinary_cleaned_text_sha256'] != sha(source['text'])
            or discovery['raw_source_offset'] != block['source_offset'] or discovery['raw_source_order'] != block['source_order']
            or sha(block['source_block']) != discovery['raw_source_block_sha256']
            or sha(block['source_block']) != raw['full_raw_block_sha256_hash_only']
            or block['motion_text'] != raw['raw_full_body'] or sha(block['motion_text']) != raw['raw_full_body_sha256']
            or block['outcome_quote'] != raw['raw_outcome_quote']):
        raise ValueError('transcription_raw_occurrence_changed')
    envelopes = own_formal_envelopes(source, block)
    if len(envelopes) != 1 or envelope_proof(source, envelopes[0]) != raw['whole_own_formal_envelope'] or digest(envelope_proof(source, envelopes[0])) != raw['whole_own_formal_envelope_sha256']:
        raise ValueError('transcription_own_envelope_changed')
    excerpt = raw['owned_formal_excerpt']
    chunks = []
    stop = 0
    for span in excerpt['raw_block_consumed_spans']:
        start, end = span['start'], span['end']
        if not stop <= start <= end <= len(block['source_block']):
            raise ValueError('transcription_excerpt_span_invalid')
        quote = block['source_block'][start:end]
        if sha(quote) != span['exact_quote_sha256']:
            raise ValueError('transcription_excerpt_changed')
        chunks.append(quote)
        stop = end
    if ''.join(chunks) != excerpt['quote'] or sha(excerpt['quote']) != excerpt['excerpt_sha256']:
        raise ValueError('transcription_excerpt_not_full_block')
    for name, expected in [('raw_body_span_within_original_full_block', block['motion_text']),
                            ('own_outcome_span_within_original_full_block', block['outcome_quote'])]:
        span = excerpt[name]
        if block['source_block'][span['start']:span['end']] != expected:
            raise ValueError('transcription_owned_span_changed')
    semantic = witness['semantic_inventory']
    native = [item for item in semantic['original_formal_introductions']
              if item['diagnostic_envelope_id'] == receipt['native_envelope_diagnostic_id_not_canonical_key']]
    heading = receipt['complete_governing_heading_geometry']
    if (len(native) != 1 or native[0]['native_heading'] != heading['native_number']
            or heading not in semantic['native_headings']
            or max(line['diagnostic_line_index'] for line in heading['complete_native_lines']) >= native[0]['introduction']['diagnostic_line_index']):
        raise ValueError('transcription_governing_native_frame_changed')
    next_heading = receipt['necessary_next_heading_only_projection']['native_heading']
    if next_heading not in semantic['native_headings'] or heading['immediate_next_heading'] != next_heading['native_number']:
        raise ValueError('transcription_native_next_heading_changed')
    native_frame = native[0]
    header = block['source_block'].split(block['motion_text'], 1)[0]
    for field in ('introduction', 'seconder_line'):
        line = native_frame.get(field)
        if not line or not re.sub(r'\s+', ' ', line['quote']).strip() in re.sub(r'\s+', ' ', header).strip():
            raise ValueError('transcription_native_actor_frame_changed')
    if not native_frame.get('own_outcome') or native_frame['own_outcome']['quote'] != block['outcome_quote']:
        raise ValueError('transcription_native_own_outcome_changed')
    _verify_projected_geometry(receipt['complete_governing_heading_geometry'], lines)
    _verify_projected_geometry(receipt['necessary_next_heading_only_projection'], lines)
    import fitz
    body = block['motion_text']
    raw_start = source['text'].find(block['source_block'], block['source_offset'])
    if raw_start < 0 or source['text'].find(block['source_block'], raw_start+1) >= 0:
        raise ValueError('transcription_full_block_not_unique')
    body_start = raw_start + excerpt['raw_body_span_within_original_full_block']['start']
    cursor, output, previous = 0, [], None
    for span in receipt['exact_consumed_spans']:
        start, end = span['raw_body_start'], span['raw_body_end']
        if (not cursor <= start <= end <= len(body) or previous == (start, end)
                or body[start:end] != span['raw_consumed_text'] or span['source_sha256'] != source['source_sha256']
                or span['clean_source_start'] != body_start+start or span['clean_source_end'] != body_start+end
                or source['text'][span['clean_source_start']:span['clean_source_end']] != span['raw_consumed_text']):
            raise ValueError('transcription_edit_span_invalid')
        evidence = span['evidence']
        render = evidence['candidate_render']
        page = document[render['page_one_based']-1]
        if evidence['page'] != render['page_one_based']:
            raise ValueError('transcription_glyph_page_changed')
        words = [list(word) for word in page.get_text('words', sort=False)]
        if 'raw_native_word' in evidence and not any(word[:4] == evidence['native_bbox'] and word[4] == evidence['raw_native_word'] for word in words):
            raise ValueError('transcription_glyph_word_changed')
        if any(word not in words for word in evidence.get('neighboring_word_geometry', [])):
            raise ValueError('transcription_insertion_neighbors_changed')
        if list(page.rect) != render['page_rect_points'] or sha(_asset(render['file']).read_bytes()) != render['png_sha256']:
            raise ValueError('transcription_render_asset_changed')
        clip = fitz.Rect(render['clip_bbox_points'])
        if [list(word) for word in page.get_text('words', clip=clip, sort=False)] != render['native_words_in_actual_clip']:
            raise ValueError('transcription_render_words_changed')
        pix = page.get_pixmap(matrix=fitz.Matrix(4, 4), clip=clip, colorspace=fitz.csRGB, alpha=False, annots=True)
        if (sha(pix.tobytes('png')) != render['png_sha256'] or sha(pix.samples) != render['pixel_samples_sha256']
                or (pix.width, pix.height, pix.stride) != (render['width'], render['height'], render['stride'])):
            raise ValueError('transcription_render_pixels_changed')
        output.extend((body[cursor:start], span['replacement_text']))
        cursor, previous = end, (start, end)
    output.append(body[cursor:])
    accepted = ''.join(output)
    if (len(receipt['exact_consumed_spans']) != receipt['span_count'] or accepted != receipt['accepted_complete_full_body']
            or sha(accepted) != receipt['accepted_complete_full_body_sha256']):
        raise ValueError('transcription_full_output_changed')
    return accepted


def source_binding(source):
    return digest({key: source.get(key) for key in ('source_sha256', 'source_url', 'source_format',
                   'source_classification', 'local_date', 'text', 'blocks', 'formal_occurrence_inventory')})


def load_reviewed_transcriptions(source, path):
    """Source-only verification. Failure cannot authorize corrected text."""
    try:
        manifest = _store()
        selected = [row for row in manifest['receipts'] if row['discovery_key']['original_pdf_sha256'] == source['source_sha256']]
        if not selected:
            return None
        if source.get('source_classification') != 'Council' or sha(Path(path).read_bytes()) != source['source_sha256']:
            raise ValueError('transcription_original_pdf_changed')
        _renderer_environment()
        import fitz
        views = {}
        with fitz.open(path) as document:
            pages, lines = _geometry(document)
            witnesses = {}
            for entry in selected:
                receipt = json.loads(_asset(entry['file']).read_bytes())
                if sha(_asset(entry['file']).read_bytes()) != entry['sha256'] or receipt['discovery_key'] != entry['discovery_key']:
                    raise ValueError('transcription_receipt_changed')
                ref = receipt['source_witness']
                if ref['file'] not in witnesses:
                    witness = json.loads(_asset(ref['file']).read_bytes())
                    if sha(_asset(ref['file']).read_bytes()) != ref['sha256']:
                        raise ValueError('transcription_witness_changed')
                    _verify_witness(witness, source, document, pages, lines)
                    witnesses[ref['file']] = witness
                matching = [block for block in source['blocks'] if block['source_offset'] == entry['discovery_key']['raw_source_offset'] and block['source_order'] == entry['discovery_key']['raw_source_order']]
                if len(matching) != 1:
                    raise ValueError('transcription_raw_block_missing')
                block = matching[0]
                accepted = _verify_receipt(receipt, source, block, document, lines, witnesses[ref['file']])
                views[f"{block['source_offset']}:{block['source_order']}"] = {
                    'status': 'verified_source_transcription', 'source_sha256': source['source_sha256'],
                    'source_binding_sha256': source_binding(source),
                    'raw_block_sha256': sha(block['source_block']), 'raw_body_sha256': sha(block['motion_text']),
                    'accepted_body': accepted, 'accepted_body_sha256': sha(accepted),
                    'canonical_key': receipt['raw_occurrence_identity']['key_preserved'],
                    'receipt_sha256': entry['sha256'], 'manifest_sha256': MANIFEST_SHA256,
                    'source_inventory_sha256': ref['semantic_inventory_sha256'],
                    'typed_subject': receipt['typed_role_action_source_review']}
        return {'status': 'verified', 'manifest_sha256': MANIFEST_SHA256, 'views': views}
    except (ValueError, KeyError, TypeError, OSError, IndexError) as error:
        return {'status': 'held', 'reason': str(error).split('\n')[0], 'manifest_sha256': MANIFEST_SHA256}


def bound_transcription(motion, source, block, claim_inventory):
    """Exact body supplement only after raw canonical identity is independently proved."""
    bundle = source.get('reviewed_transcriptions') or {}
    view = bundle.get('views', {}).get(f"{block['source_offset']}:{block['source_order']}")
    if (bundle.get('status') != 'verified' or not view or view['status'] != 'verified_source_transcription'
            or view['source_sha256'] != source.get('source_sha256') or view['raw_block_sha256'] != sha(block['source_block'])
            or view['raw_body_sha256'] != sha(block['motion_text']) or motion.get('text_content') != view['accepted_body']
            or not valid_inventory(claim_inventory, motion.get('meeting_id'))):
        return None
    if view.get('source_binding_sha256') != source_binding(source) or sha(view['accepted_body']) != view['accepted_body_sha256']:
        return None
    native_view = source.get('operative_views', {}).get(f"{block['source_offset']}:{block['source_order']}")
    if not native_view or native_view.get('status') != 'explicit_operative' or native_view.get('raw_block') != block:
        return None
    try:
        manifest = _store()
        entries = [entry for entry in manifest['receipts'] if entry['sha256'] == view['receipt_sha256']]
        if len(entries) != 1:
            return None
        receipt = json.loads(_asset(entries[0]['file']).read_bytes())
        if (view['manifest_sha256'] != MANIFEST_SHA256 or receipt['accepted_complete_full_body'] != view['accepted_body']
                or receipt['raw_occurrence_identity']['key_preserved'] != view['canonical_key']
                or receipt['typed_role_action_source_review'] != view['typed_subject']):
            return None
    except (ValueError, KeyError, TypeError, OSError):
        return None
    identity = (motion.get('meta') or {}).get('canonical_source_motion') or {}
    if (identity.get('key') != view['canonical_key'] or identity.get('raw_motion_text') != block['motion_text']
            or identity.get('source_file') != source.get('source_file') or identity.get('source_url') != source.get('source_url')
            or identity.get('source_format') != source.get('source_format') or identity.get('outcome_quote') != block['outcome_quote']
            or identity.get('formal_source_kind', 'moved_motion') != block.get('formal_source_kind', 'moved_motion')):
        return None
    if 'source_block' in identity:
        if identity['source_block'] != block['source_block']:
            return None
    elif identity.get('source_block_sha256') != sha(block['source_block']):
        return None
    if 'raw_motion_text_sha256' in identity and identity['raw_motion_text_sha256'] != sha(block['motion_text']):
        return None
    import re
    from .ballot_reconstruction import validate_roster_entries
    header = block['source_block'].split(block['motion_text'], 1)[0]
    for field, marker in (('mover_id', r'MOVED(?:\s+BY)?'), ('seconder_id', 'SECONDED')):
        names = re.findall(r'(?im)^\s*'+marker+r'\s*:\s*([^\n]+)', header)
        if len(names) != 1:
            return None
        people, unknown = validate_roster_entries(names[0], source.get('present', []))
        if unknown or len(people) != 1 or people[0]['id'] != motion.get(field):
            return None
    own = [row for row in claim_inventory['claims'] if row['id'] == motion['id']]
    if len(own) != 1 or own[0] != project_claim(motion):
        return None
    # Same canonical occurrence, exact full-body claim or primary typed subject
    # on another row is a competing claim. Parent bylaws and trailing context
    # outside an explicit own body do not assign ownership.
    identifiers = [item['number'] for item in view['typed_subject'].get('bylaw_roles', [])]
    identifiers += view['typed_subject'].get('file_ids', [])
    import re
    def claims(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from claims(child)
        elif isinstance(value, list):
            for child in value:
                yield from claims(child)
    for row in claim_inventory['claims']:
        if row['id'] == motion['id']:
            continue
        if row.get('text_content') in (view['accepted_body'], block['motion_text']):
            return None
        for claim in claims(row.get('meta') or {}):
            if claim.get('key') == view['canonical_key'] or view['canonical_key'] in (claim.get('previous_keys') or []) or (claim.get('source_sha256') == source['source_sha256'] and claim.get('source_offset') == block['source_offset'] and claim.get('source_order') == block['source_order']):
                return None
        # Stored full proof tails are deliberately excluded from this subject
        # check; their own operative raw_motion_text remains included.
        own_texts = [row.get('text_content') or '']
        own_texts += [claim.get(field) or '' for claim in claims(row.get('meta') or {})
                      for field in ('raw_motion_text', 'source_motion_text', 'original_motion_text', 'operative_body', 'accepted_complete_full_body')]
        if any(re.search(r'(?<![\w])'+re.escape(str(identifier))+r'(?![\w])', text, re.I)
               for identifier in identifiers for text in own_texts):
            return None
    return {key: value for key, value in view.items() if key not in ('accepted_body', 'typed_subject')} | {
        'method': 'trusted_exact_source_transcription_and_complete_claim_inventory',
        'claim_inventory_sha256': claim_inventory['fingerprint']}
