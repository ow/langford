"""Typed original-header evidence; arrival clocks never become body offsets."""
from datetime import datetime
import re
import hashlib
import fitz
from .ballot_reconstruction import validate_roster_entries
from .historical_references import chronology_reference_spans
from .vote_evidence import outcome_family, normalize_text

_CLOCK = r'(\d{1,2}):(\d{2})\s*(a\.?m\.?|p\.?m\.?)'
_DAY = r'[A-Za-z]+\s+\d{1,2},\s+\d{4}'
_MONTH = r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
_DATE_FRAGMENT = rf'\b(?:{_MONTH}\.?\s+\d{{1,2}}|\d{{1,2}}\s+{_MONTH}\.?|\d{{1,4}}[-/]\d{{1,2}})\b'


def _minutes(hour, minute, meridiem):
    hour, minute = int(hour), int(minute)
    if not 1 <= hour <= 12 or not 0 <= minute <= 59:
        raise ValueError('Invalid clock')
    return hour % 12 * 60 + minute + (720 if meridiem.lower().startswith('p') else 0)


def _day(value):
    return datetime.strptime(' '.join(value.split()), '%B %d, %Y').date().isoformat()


def original_header_attendance(native_text, clean_text, path, people, source_format):
    """Account for complete entry suffixes and retain original native geometry."""
    hit = re.search(r'\bPRESENT\s*:', native_text, re.I)
    if not hit:
        return None
    end = re.search(r'\b(?:ATTENDING|ABSENT|REGRETS)\s*:', native_text[hit.end():], re.I)
    if not end:
        return None
    roster = native_text[hit.end():hit.end()+end.start()]
    if not re.search(r'\b(?:arrived|attended)\b', roster, re.I):
        return None
    held = {'status': 'header_attendance_annotation_invalid', 'native_roster_quote': roster.strip()}
    try:
        if source_format != 'original_pdf_layout':
            return held
        with fitz.open(path) as doc:
            words = doc[0].get_text('words')
            starts = [w for w in words if w[4].upper().rstrip(':') == 'PRESENT']
            assert len(starts) == 1
            stops = [w for w in words if w[4].upper().rstrip(':') in {'ATTENDING', 'ABSENT', 'REGRETS'} and w[1] > starts[0][1]]
            assert stops
            stop = min(w[1] for w in stops)
            geometry = [list(w) for w in words if starts[0][1]-1 <= w[1] < stop]
        entries = list(re.finditer(r'(?m)^[ \t]*(?:Mayor|Councillor)\s+[^\n]+(?:\n(?![ \t]*(?:Mayor|Councillor)\b)[^\n]*)*', roster))
        annotations = []
        view = roster
        spans = []
        for entry in entries:
            value = entry[0].strip()
            if not re.search(r'\b(?:arrived|attended)\b', value, re.I):
                continue
            identity, suffix = re.split(r'\s+-\s+', value, maxsplit=1)
            found, unknown = validate_roster_entries(identity, people)
            assert len(found) == 1 and not unknown
            person = found[0]
            # Require a full initial/surname identity, rather than a surname alias.
            literal = re.fullmatch(r'(?:Mayor|Councillor)\s+([A-Z])\.\s+([A-Za-z-]+)', identity)
            assert literal and person['name'][0].casefold() == literal[1].casefold()
            assert person['name'].split()[-1].casefold() == literal[2].casefold()
            arrival = re.fullmatch(r'(?:Remote,\s*)?arrived\s+(?:at\s+)?'+_CLOCK, suffix, re.I)
            modality = re.fullmatch(r'Attended remotely\s+('+_DAY+r')\s*&\s*in person on\s+('+_DAY+r')', suffix, re.I)
            annotation = {'person_id': person['id'], 'canonical_name': person['name'], 'raw_entry_quote': value}
            if arrival:
                annotation.update(kind='late_arrival', minute_of_day=_minutes(*arrival.groups()), source_clock=arrival[0])
            elif modality:
                dates = [_day(modality[1]), _day(modality[2])]
                assert dates[0] < dates[1]
                annotation.update(kind='dated_modality', dates=dates, modes=['remote', 'in_person'])
            else:
                return held
            # Apply exactly the existing footer cleanup to locate the entry's
            # derived span, but retain the unabridged original quote above.
            derived = re.sub(r'(?m)^\s*\d+\s*$', '', value).strip()
            assert clean_text.count(derived) == 1
            at = clean_text.index(derived)
            start = at + len(identity)
            spans.append([start, at+len(derived)])
            view = view.replace(value, identity, 1)
            annotations.append(annotation)
        assert annotations
        present, unknown = validate_roster_entries(view, people)
        assert not unknown
        return {'status': 'typed_original_header', 'native_roster_quote': roster.strip(),
                'roster_view': view.strip(), 'present': present, 'annotations': annotations,
                'consumed_clean_spans': spans, 'page': 1, 'native_word_boxes': geometry}
    except (AssertionError, ValueError, IndexError, KeyError, TypeError, RuntimeError):
        return held


def header_attendance_before_vote(source, block, position):
    """Prove BEFORE-arrival absence only; later/straddling decisions stay held."""
    header = source.get('header_attendance')
    if not header:
        return None
    if header['status'] != 'typed_original_header':
        return {'status': header['status']}
    text = source['text']
    annotations = header['annotations']
    modalities = [a for a in annotations if a['kind'] == 'dated_modality']
    if modalities:
        # Any independently documented resumption opens an unresolved attendance
        # session. Neither a day change nor modality resets physical presence.
        body_start = re.search(r'(?im)^.*called the meeting to order.*$', text)
        narrative = text[body_start.start() if body_start else 0:position]
        transition = re.search(r'(?i)\b(?:resum(?:e|ed)|reconven(?:e|ed)|recess(?:ed)?)\b|THAT\s*Council\s*(?:resume|reconvene)', narrative)
        calls = re.findall(r'(?i)called the meeting to order', narrative)
        try:
            other_day = any(_day(m[0]) != source['local_date'] for m in re.finditer(_DAY, narrative))
        except ValueError:
            other_day = True
        later_fragment = False
        for annotation in modalities:
            for value in annotation['dates'][1:]:
                day = datetime.fromisoformat(value)
                month = rf'(?:{day.strftime("%B")}|{day.strftime("%b")})\.?'
                number = rf'0?{day.day}(?:st|nd|rd|th)?'
                if re.search(rf'\b(?:{month}\s+{number}|{number}\s+{month})\b', narrative, re.I):
                    later_fragment = True
        if transition or len(calls) > 1 or other_day or later_fragment:
            return {'status': 'resumed_session_presence_unresolved'}
        if any(a['dates'][0] != source['local_date'] for a in modalities):
            return {'status': 'header_attendance_annotation_invalid'}
    arrivals = [a for a in annotations if a['kind'] == 'late_arrival']
    absent = []
    bounds = []
    if arrivals:
        calls = list(re.finditer(r'(?i)\bcalled the meeting to order at\s+'+_CLOCK, text))
        if len(calls) != 1 or calls[0].start() >= position:
            return {'status': 'header_arrival_vote_time_unresolved'}
        try:
            lower = _minutes(*calls[0].groups())
        except ValueError:
            return {'status': 'header_arrival_vote_time_unresolved'}
        # A close-at-time resolution supplies an upper bound for its own vote
        # and earlier decisions in that continuous narrative segment. Scheduled
        # adjourn/resume times and unrelated dates never supply lower bounds.
        closings = []
        for candidate in source['blocks']:
            body = candidate['motion_text']
            opening = re.match(r'(?i)^THAT Council close the meeting at\s+'+_CLOCK+r'\s+to the public pursuant to section\s+90\b', body)
            if not opening or candidate.get('formal_source_kind') != 'moved_motion' or outcome_family(candidate['result']) != 'passed':
                continue
            # The whole operative body must be unconditional and undated.
            # Section90's statutory hypothetical about public disclosure is a
            # reason for closure, not a condition on whether/when Council closes.
            normalized = normalize_text(body)
            normalized = normalized.replace('subject to solicitor client privilege', '')
            normalized = re.sub(r'could reasonably be expected to harm the interests of the municipality if they were held in public', '', normalized)
            if (re.search(r'\b(?:if|when|unless|provided|conditional|scheduled|schedule|tomorrow|today|next|future|will|would|upon|after|before|until|following|contingent|later|noon|midnight)\b', normalized)
                    or len(list(re.finditer(_CLOCK, body, re.I))) != 1
                    or re.search(r'\bsubject to\b', normalized)
                    or re.search(_DATE_FRAGMENT, body, re.I)
                    or re.search(r'\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b', body)
                    or re.search(r'(?i)\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b', body)):
                continue
            quote = candidate['source_block']
            start = text.find(quote)
            if start < 0 or text.find(quote, start+1) >= 0:
                continue
            if len(re.findall(r'(?im)^\s*MOVED BY:', quote)) != 1 or len(re.findall(r'(?im)^\s*SECONDED:', quote)) != 1:
                continue
            if start < position and (candidate['source_offset'],candidate['source_order']) != (block['source_offset'],block['source_order']):
                continue
            # An immediate clock followed by the ordinary statutory closure
            # clause excludes conditional, future and separately dated suffixes.
            prefix = quote[:quote.find(body)]
            if re.search(r'(?i)\b(?:if|when|tomorrow|next|scheduled|would|will)\b', prefix):
                continue
            closings.append((start, candidate, opening))
        if not closings:
            return {'status': 'header_arrival_vote_time_unresolved'}
        upper_offset, upper_block, upper_hit = min(closings, key=lambda item:item[0])
        # Any competing clock/date or session transition makes ordering unsafe.
        segment = text[calls[0].start():upper_offset]
        references = chronology_reference_spans(source)
        def narrative_token(match):
            start, end = calls[0].start()+match.start(), calls[0].start()+match.end()
            return not any(r['start'] <= start and end <= r['end'] for r in references)
        try:
            upper = _minutes(*upper_hit.groups())
            clocks = [_minutes(*m.groups()) for m in re.finditer(_CLOCK, segment, re.I) if narrative_token(m)] + [upper]
            dates = [_day(m[0]) for m in re.finditer(_DAY, segment) if narrative_token(m)]
        except ValueError:
            return {'status': 'header_arrival_vote_time_unresolved'}
        if (upper < lower or any(a > b for a,b in zip(clocks, clocks[1:]))
                or any(day != source['local_date'] for day in dates)
                or re.search(r'(?i)\b(?:adjourn|resume|reconvene)\b', segment)):
            return {'status': 'header_arrival_vote_time_unresolved'}
        for annotation in arrivals:
            if not lower <= upper < annotation['minute_of_day']:
                return {'status': 'header_arrival_vote_time_unresolved'}
            absent.append(annotation['person_id'])
        bounds.append({**({'historical_reference_classification': references} if references else {}), 'source_date': source['local_date'], 'lower_quote': calls[0][0],
                       'upper_quote': upper_hit[0], 'upper_offset': upper_offset,
                       'upper_source_block': upper_block['source_block'],
                       'upper_source_identity': {'source_sha256': source['source_sha256'],
                           'source_offset': upper_block['source_offset'], 'source_order': upper_block['source_order'],
                           'motion_text_sha256': hashlib.sha256(upper_block['motion_text'].encode()).hexdigest(),
                           'source_block_sha256': hashlib.sha256(upper_block['source_block'].encode()).hexdigest()},
                       'method': 'ordered_same_session_close_time_upper_bound_strictly_before_arrival'})
    return {'status': 'header_attendance_validated', 'absent_person_ids': sorted(absent),
            'annotations': annotations, 'clock_bounds': bounds,
            'native_roster_quote': header['native_roster_quote'], 'native_word_boxes': header['native_word_boxes']}
