"""Native document references are chronology tokens, never attendance events.

Receipts preserve original offsets and consumed text. Only complete prior-document
references with original geometry may be omitted from date/clock observations.
"""
from datetime import datetime
from pathlib import Path
import hashlib
import re
import fitz
from .vote_evidence import outcome_family

_DAY = r'[A-Za-z]+\s+\d{1,2},\s+\d{4}'
_INTRO = 'THAT Council adopt the recommendations for each item of the Consent Agenda as presented:'
_TITLE = r'(?:Special Council|Council|[A-Za-z]+(?: [A-Za-z]+)* Advisory)'
_BULLET = re.compile(r'(?m)^[ \t]*[•·][ \t]+(?P<title>(?P<draft>Draft )?Minutes of the '+_TITLE+r' Meeting - (?P<date>'+_DAY+r')(?P<clock> \d{1,2}(?::\d{2})?\s*(?:am|pm))? \((?P<mode>ADOPT|RECEIVE)\))[ \t]*$')
_HEADING = re.compile(r'(?m)^[ \t]*(?P<number>\d+\.\d+)[ \t]+(?P<title>[A-Za-z]+(?: [A-Za-z]+)* Committee Meeting Resolutions - (?P<date>'+_DAY+r'))[ \t]*$')


def _sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def original_historical_references(text, path, blocks, local_date, source_format, source_sha256):
    """Fail closed on absent/ambiguous geometry; no repaired dates or fuzzy text."""
    receipts = []
    if source_format != 'original_pdf_layout' or hashlib.sha256(Path(path).read_bytes()).hexdigest() != source_sha256:
        return None
    try:
        native = []
        with fitz.open(path) as doc:
            for page_number, page in enumerate(doc, 1):
                words = page.get_text('words')
                for block in page.get_text('dict', flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)['blocks']:
                    for line in block.get('lines', []):
                        native.append({'page': page_number, 'quote': ''.join(s['text'] for s in line['spans']).strip(),
                                       'bbox': list(line['bbox']), 'words': words})
        def prior(value):
            parsed = datetime.strptime(' '.join(value.split()), '%B %d, %Y').date().isoformat()
            return parsed if parsed < local_date else None
        def geometry(quote):
            hits = [line for line in native if line['quote'] == quote]
            return hits[0] if len(hits) == 1 else None
        def unique(value):
            return text.count(value) == 1
        def receipt(hit, kind, date, geo, **proof):
            return {'kind': kind, 'start': hit.start(), 'end': hit.end(), 'consumed_text': hit[0],
                    'reference_date': date, 'page': geo['page'], 'native_bbox': geo['bbox'], **proof}
        for block in blocks:
            body = block['motion_text']
            if (block.get('formal_source_kind') != 'moved_motion' or outcome_family(block['result']) != 'passed'
                    or not body.startswith(_INTRO) or not unique(body)):
                continue
            tail = body[len(_INTRO):]
            hits = list(_BULLET.finditer(tail))
            # Consume the ENTIRE list, including whitespace, rather than ignoring
            # a suffix that could turn a document title into a session condition.
            cursor = 0
            valid = bool(hits)
            for hit in hits:
                valid = valid and not tail[cursor:hit.start()].strip()
                cursor = hit.end()
            if not valid or tail[cursor:].strip():
                continue
            quote = block['source_block']
            if (not unique(quote) or quote.count(body) != 1
                    or len(re.findall(r'(?m)^\s*MOVED BY:', quote)) != 1
                    or len(re.findall(r'(?m)^\s*SECONDED:', quote)) != 1):
                continue
            body_start = text.index(body)
            for hit in _BULLET.finditer(text, body_start+len(_INTRO), body_start+len(body)):
                date, geo = prior(hit['date']), geometry(hit['title'])
                if not date or not geo or not unique(hit[0]):
                    continue
                if (hit['draft'] is not None) != (hit['mode'] == 'RECEIVE'):
                    continue
                if hit['clock']:
                    clock = re.fullmatch(r' (\d{1,2})(?::(\d{2}))?\s*(am|pm)', hit['clock'])
                    if not 1 <= int(clock[1]) <= 12 or not 0 <= int(clock[2] or 0) <= 59:
                        continue
                bullets = [w for w in geo['words'] if w[4] in ('•', '·') and w[2] < geo['bbox'][0]
                           and abs((w[1]+w[3]-geo['bbox'][1]-geo['bbox'][3])/2) < 3]
                if len(bullets) != 1:
                    continue
                receipts.append(receipt(hit, 'historical_received_draft_minutes_reference' if hit['draft'] else 'historical_adopted_minutes_reference', date, geo,
                    native_bullet=list(bullets[0]), formal_wrapper={'source_offset': block['source_offset'], 'source_order': block['source_order'],
                    'motion_text_sha256': _sha(body), 'source_block_sha256': _sha(quote), 'outcome': block['outcome_quote']}))
        for hit in _HEADING.finditer(text):
            date, geo = prior(hit['date']), geometry(hit['title'])
            if not date or not geo or not unique(hit[0]):
                continue
            parent_number = hit['number'].split('.')[0]
            parents = list(re.finditer(r'(?m)^[ \t]*'+re.escape(parent_number)+r'\.[ \t]+COMMITTEE RESOLUTIONS[ \t]*$', text[:hit.start()]))
            child = re.match(r'\s*('+re.escape(hit['number'])+r'\.1)[ \t]+([^\n]+)', text[hit.end():])
            if len(parents) != 1 or not child:
                continue
            parent = parents[0]
            if text[parent.end():hit.start()].strip():
                continue
            parent_geo, child_geo = geometry('COMMITTEE RESOLUTIONS'), geometry(child[2].strip())
            # Number labels and titles must share the actual native baseline.
            def numbered(g, label):
                return g and g['page'] == geo['page'] and len([w for w in g['words'] if w[4] == label
                    and w[2] < g['bbox'][0] and abs((w[1]+w[3]-g['bbox'][1]-g['bbox'][3])/2) < 3]) == 1
            if not numbered(geo, hit['number']) or not numbered(parent_geo, parent_number+'.') or not numbered(child_geo, child[1]):
                continue
            if not parent_geo['bbox'][1] < geo['bbox'][1] < child_geo['bbox'][1]:
                continue
            # A heading inside an operative body is not structural narrative.
            if any(b['motion_text'] in text and text.index(b['motion_text']) <= hit.start() < text.index(b['motion_text'])+len(b['motion_text']) for b in blocks):
                continue
            receipts.append(receipt(hit, 'historical_committee_resolutions_heading_reference', date, geo,
                parent_heading={'start': parent.start(), 'end': parent.end(), 'consumed_text': parent[0], 'native_bbox': parent_geo['bbox']},
                following_child_heading={'start': hit.end()+child.start(), 'end': hit.end()+child.end(), 'consumed_text': child[0], 'native_bbox': child_geo['bbox']}))
    except (ValueError, KeyError, TypeError, IndexError, RuntimeError):
        return None
    return {'source_sha256': source_sha256, 'text_sha256': _sha(text), 'references': receipts}


def chronology_reference_spans(source):
    """Recheck witnesses against the current unmodified source before using them."""
    proof = source.get('historical_chronology_references') or {}
    text = source['text']
    if proof.get('source_sha256') != source['source_sha256'] or proof.get('text_sha256') != _sha(text):
        return []
    return [r for r in proof.get('references', []) if text[r['start']:r['end']] == r['consumed_text']]
