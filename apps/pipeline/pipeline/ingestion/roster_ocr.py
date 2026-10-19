"""Reviewed original-image roster views; raw minutes and motion identities stay intact.

Receipts are discovered by exact original PDF hash, never meeting ID or fuzzy
name. This adapter runs no OCR/model: reviewed local image evidence is re-bound
to original bytes, native geometry and current exact canonical/dated office.
"""
from datetime import date
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

import fitz

from .ballot_reconstruction import validate_roster_entries

STORE = Path(__file__).parent / 'data' / 'roster-ocr'
ROOT = Path(__file__).resolve().parents[4]


def _digest(value):
    return hashlib.sha256(value).hexdigest()


@lru_cache(maxsize=16)
def _image_binding(pdf_bytes, receipt_bytes):
    receipt = json.loads(receipt_bytes)
    with fitz.open(stream=pdf_bytes, filetype='pdf') as document:
        page = document[receipt['page'] - 1]
        words = page.get_text('words')
        present = [w for w in words if w[4].upper().rstrip(':') == 'PRESENT']
        attending = [w for w in words if w[4].upper().rstrip(':') == 'ATTENDING']
        assert len(present) == len(attending) == 1
        crop = receipt['roster_crop']
        clip = fitz.Rect(crop['clip_pdf_points'])
        assert clip.y0 <= present[0][1] < attending[0][1] <= clip.y1
        assert clip.x0 == page.rect.x0 and clip.x1 == page.rect.x1
        assert [list(w) for w in words if fitz.Rect(w[:4]).intersects(clip)] == crop['native_words']
        image = page.get_pixmap(matrix=fitz.Matrix(crop['render_scale'], crop['render_scale']), clip=clip)
        assert _digest(image.tobytes('png')) == crop['render_sha256']
        field = receipt.get('identity_field_crop')
        if field:
            box = fitz.Rect(field['clip_pdf_points'])
            assert clip.contains(box)
            assert all(list(w) in crop['native_words'] for w in field['native_words'])
            assert all(box.contains(fitz.Rect(w[:4])) for w in field['native_words'])
            image = page.get_pixmap(matrix=fitz.Matrix(field['render_scale'], field['render_scale']), clip=box)
            assert _digest(image.tobytes('png')) == field['render_sha256']
    return True


def reviewed_roster_view(source, *, meeting, people, memberships):
    """Return a separate validated roster view, or an explicit hold for known proof."""
    try:
        index = json.loads((STORE / 'index.json').read_bytes())
        expected = index.get(source.get('source_sha256'))
        if not expected:
            return source
        receipt_path = STORE / (source['source_sha256'] + '.json')
        receipt_bytes = receipt_path.read_bytes()
        assert _digest(receipt_bytes) == expected
        receipt = json.loads(receipt_bytes)
        assert receipt['version'] == 1 and receipt['method'] == 'reviewed_original_pdf_roster_ocr_v1'
        assert receipt['review_status'] == 'original_image_and_exact_canonical_dated_office_independently_reviewed'
        assert source['source_format'] == 'original_pdf_layout'
        assert source['source_url'] == receipt['source_url']
        assert source['local_date'] == receipt['source_date']
        assert abs((date.fromisoformat(source['local_date']) - date.fromisoformat(str(meeting['meeting_date'])[:10])).days) <= 1
        assert source['source_classification'] in {'Council', 'Committee of the Whole'}
        assert source['roster_quote'].strip() == receipt['native_present_quote'].strip()
        path = Path(source['source_file'])
        pdf_bytes = (path if path.is_absolute() else ROOT / path).read_bytes()
        assert _digest(pdf_bytes) == source['source_sha256'] == receipt['source_sha256']
        assert _digest(Path(__file__).with_name('native_header_vision.swift').read_bytes()) == receipt['helper_source_sha256']
        assert fitz.VersionBind == receipt['pymupdf_version']
        _image_binding(pdf_bytes, receipt_bytes)
        change = receipt['replacement']
        line = receipt['target_ocr_line']
        assert line['candidates'][0]['confidence'] == 1
        literal = change['literal']
        letters = lambda value: re.sub('[^a-z]', '', value.casefold())
        assert all(letters(literal) in letters(candidate['text']) for candidate in line['candidates'])
        container = receipt.get('identity_field_crop') or receipt['roster_crop']
        assert line in container['ocr']['lines']
        initial, surname = literal.split('. ')
        canonical = [p for p in people if p['name'].split()[-1].casefold() == surname.casefold() and p['name'][0].casefold() == initial.casefold()]
        assert len(canonical) == 1 and canonical[0]['name'] == change['canonical_name']
        person = canonical[0]
        offices = [m for m in memberships if m['person_id'] == person['id'] and m.get('organization_id') == meeting.get('organization_id') and m.get('classification') == 'Council' and (m.get('role') or '').casefold() == change['role'].casefold() and m.get('start_date') and m['start_date'] <= source['local_date'] and (not m.get('end_date') or m['end_date'] >= source['local_date'])]
        assert len(offices) == 1
        assert source['roster_quote'].count(change['raw']) == 1
        corrected = source['roster_quote'].replace(change['raw'], literal, 1)
        notation = re.sub(r'\b(Mayor|Councillors?)([A-Z])\.(?=\s*[A-Z])', r'\1 \2.', corrected, flags=re.I)
        present, unknown = validate_roster_entries(notation, people)
        assert not unknown and person['id'] in {p['id'] for p in present}
        proof = {'method': receipt['method'], 'source_sha256': source['source_sha256'], 'source_url': source['source_url'], 'source_date': source['local_date'], 'receipt_sha256': expected, 'raw_roster_quote': source['roster_quote'], 'corrected_roster_view': corrected, 'raw_identity': change['raw'], 'literal_original_image_identity': literal, 'person_id': person['id'], 'canonical_name': person['name'], 'dated_office': dict(offices[0]), 'page': receipt['page'], 'crop_sha256': receipt['roster_crop']['render_sha256'], 'identity_ocr_line': line, 'original_native_word_boxes': receipt['roster_crop']['native_words'], 'helper_source_sha256': receipt['helper_source_sha256'], 'validation': 'original_binary_image_geometry_exact_name_and_same_organization_dated_office'}
        view = {**source, 'present': present, 'roster_quote': corrected, 'roster_unknown': [], 'ambiguous_names': [], 'roster_source_validation': proof}
        # Any cached timeline was computed against the uncorrected role view.
        view.pop('presence_events', None)
        view.pop('unknown_presence_events', None)
        return view
    except (OSError, ValueError, KeyError, TypeError, AssertionError, RuntimeError):
        return {**source, 'roster_source_validation': {'status': 'held_original_roster_ocr_proof_invalid'}}
