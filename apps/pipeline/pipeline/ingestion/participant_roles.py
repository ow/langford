"""Meeting-only documentary staff and committee roles, never employment terms.

Original minutes bind identity and scope. Bounded local OCR may corroborate a
PDF header/member roster; conflicting person readings stay unresolved. Original
files, person records, memberships and database rows are never changed here.
"""
from collections import defaultdict
from datetime import date, datetime
from pathlib import PurePosixPath, Path
import re
import hashlib
import json
import subprocess
import tempfile
from urllib.parse import urlparse
from typing import Literal, TypedDict, NotRequired


class ParticipantRoleObservation(TypedDict):
    person_id: int
    meeting_id: int
    classification: Literal["government_staff", "committee_member"]
    role: str
    organization: str
    observed_date: str
    native_source_date: str
    method: Literal["official_minutes_explicit_role_v1"]
    source_file: str
    source_sha256: str
    source_url: str
    source_quote: str
    evidence_kind: str
    header_validation: NotRequired[dict]

METHOD = 'official_minutes_explicit_role_v1'
_MONTHS = 'January|February|March|April|May|June|July|August|September|October|November|December'
_STAFF = re.compile(r'^(?:(?:Senior|Deputy|Assistant|Acting)\s+)?(?:Manager|Planner|Engineer|Superintendent|Inspector|Chief Administrative Officer|Corporate Officer|Director\s+of)\b', re.I)
_MUNICIPAL = re.compile(r'^(?:Chief Administrative Officer|(?:Deputy |Acting )?Corporate Officer|(?:Deputy )?Director of Corporate Services|Legislative Services Administrative Coordinator|Legislative Services Coordinator|City Engineer|Municipal Clerk)$', re.I)
_ORGANIZATIONS = (
    (re.compile(r'\bCapital\s+Regional\s+District\b', re.I), 'Capital Regional District'),
    (re.compile(r'\bCRD\b'), 'Capital Regional District'),
    (re.compile(r'\bRoyal\s+Canadian\s+Mounted\s+Police\b', re.I), 'Royal Canadian Mounted Police'),
    (re.compile(r'\bWest\s+Shore\s+RCMP\b', re.I), 'West Shore RCMP'),
)


def _day(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _source_hold(source, meeting):
    try:
        path = PurePosixPath(source['source_file'])
        if path.is_absolute() or '..' in path.parts or path.parts[0] != 'archive' or '\\' in str(path):
            return 'project_relative_original_source_required'
        if not re.fullmatch(r'[0-9a-f]{64}', source['source_sha256']):
            return 'original_source_sha256_required'
        url = urlparse(source['source_url'])
        if url.scheme != 'https' or url.hostname not in {'langford.ca', 'www.langford.ca', 'pub-langford.escribemeetings.com'}:
            return 'official_original_source_url_required'
        if source.get('error') or source['source_format'] not in {'original_pdf_layout', 'official_html_structural'}:
            return 'canonical_original_minutes_required'
        own_header = re.split(r'\bPRESENT\b', source['text'], maxsplit=1, flags=re.I)[0]
        header = source['source_header']
        if header.strip() != own_header.strip():
            return 'own_header_text_binding_changed'
        dates = list(re.finditer(r'\b(' + _MONTHS + r')\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(20\d{2})\b', header, re.I))
        if len(dates) != 1:
            return 'native_own_header_date_unknown_or_ambiguous'
        native = datetime.strptime(' '.join(dates[0].groups()), '%B %d %Y').date()
        catalog = _day(meeting['meeting_date'])
        if native != _day(source['local_date']) or abs((native-catalog).days) > 1:
            return 'native_catalog_meeting_date_mismatch'
        if not re.search(r'\b(?:Council|Committee|Commission)\b', header, re.I):
            return 'native_meeting_heading_unknown'
    except (KeyError, ValueError, TypeError, IndexError):
        return 'original_source_binding_incomplete'
    return None


def _person_patterns(people):
    initials = defaultdict(list)
    full_names = defaultdict(list)
    patterns = []
    for person in people:
        words = re.findall(r"[A-Za-z'-]+", person['name'])
        if len(words) < 2:
            continue
        initials[(words[0][0].casefold(), words[-1].casefold())].append(person)
        if len(words[0]) > 1:
            full_names[tuple(word.casefold() for word in words)].append(person)
    for words, candidates in full_names.items():
        expression = r'(?<![A-Za-z])' + r'\s+'.join(map(re.escape, words)) + r'(?![A-Za-z])'
        patterns.append((re.compile(expression, re.I), candidates[0] if len(candidates) == 1 else None,
                         None if len(candidates) == 1 else 'ambiguous_full_name'))
    for (initial, surname), candidates in initials.items():
        expression = r'(?<![A-Za-z])' + re.escape(initial) + r'\.\s*' + re.escape(surname) + r'(?![A-Za-z])'
        patterns.append((re.compile(expression, re.I), candidates[0] if len(candidates) == 1 else None,
                         None if len(candidates) == 1 else 'ambiguous_initial_surname'))
    return patterns


def _names(text, patterns):
    matches = []
    for pattern, person, reason in patterns:
        for match in pattern.finditer(text):
            matches.append((match.start(), match.end(), person, reason))
    return sorted(matches, key=lambda value: (value[0], -value[1]))


def _paragraph(text, position):
    boundaries = list(re.finditer(r'\n[ \t]*\n', text[:position]))
    start = boundaries[-1].end() if boundaries else 0
    after = re.search(r'\n[ \t]*\n', text[position:])
    end = position + after.start() if after else len(text)
    return start, end


def _roster_entries(text, patterns):
    """Keep native PDF column geometry; continuation cells inherit one column."""
    marker = re.search(r'\bATTENDING\s*:', text, re.I)
    if not marker:
        return []
    stop = re.search(r'(?im)^\s*(?:Meeting available|\d+\.\s|CALL TO ORDER)', text[marker.end():])
    if not stop:
        return []
    end = marker.end() + stop.start()
    lines = text[marker.start():end].splitlines()
    columns = {}; entries = []
    for index, original in enumerate(lines):
        line = re.sub(r'^ATTENDING\s*:', lambda m: ' '*len(m[0]), original, flags=re.I)
        for cell in re.finditer(r'\S(?:.*?\S)?(?=\s{2,}|$)', line):
            value = cell[0]; names = [hit for hit in _names(value, patterns) if hit[0] == 0]
            near = next((key for key in columns if abs(key-cell.start()) <= 3), None)
            if names:
                _, right, person, reason = names[0]
                if not value[right:].startswith(','):
                    continue
                entry = {'person': person, 'reason': reason, 'role': value[right+1:].strip(), 'first': index, 'last': index}
                entries.append(entry); columns[cell.start()] = entry
            elif near is not None:
                columns[near]['role'] += ' ' + value
                columns[near]['last'] = index
    for entry in entries:
        entry['source_quote'] = '\n'.join(lines[entry['first']:entry['last']+1])
    return entries


def _native_committee_ocr(source, patterns):
    """Only corroborate original image words; never substitute a person's identity."""
    if source['source_format'] != 'original_pdf_layout' or not re.search(r'\bAdvisory\s+Committee\b', source['source_header'], re.I):
        return None
    try:
        from .native_header_ocr import recover_pdf_header_date
        import fitz
        root = Path(__file__).resolve().parents[4]
        original = root / source['source_file']
        if not original.is_file() or hashlib.sha256(original.read_bytes()).hexdigest() != source['source_sha256']:
            return None
        cache = Path(tempfile.gettempdir()) / 'participant-role-header-validation'
        day, proof = recover_pdf_header_date(original, catalog_date=source['stored_date'], cache_dir=cache)
        if not proof or day != source['local_date'] or proof['source_sha256'] != source['source_sha256']:
            return None
        raw = Path(proof['ocr_receipt']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != proof['ocr_receipt_sha256'] or hashlib.sha256(Path(proof['render_file']).read_bytes()).hexdigest() != proof['render_sha256']:
            return None
        header = json.loads(raw)
        config = header['config']
        helper = Path(__file__).with_name('native_header_vision.swift')
        if config['source_sha256'] != source['source_sha256'] or config['helper_sha256'] != hashlib.sha256(helper.read_bytes()).hexdigest() or config['page'] != 1 or config['render_scale'] != 6:
            return None
        titles = []
        for line in header['ocr']['lines']:
            candidates = line['candidates']
            if not candidates or not any(re.search(r'Advisory\s+Committee', c['text'], re.I) for c in candidates):
                continue
            if candidates[0]['confidence'] != 1 or not re.fullmatch(r'(Community Advisory Committee|Sustainable Development Advisory Committee) Minutes', candidates[0]['text']):
                return None
            titles.append(candidates[0]['text'])
            if any(c['confidence'] == 1 and re.fullmatch(r'(Community Advisory Committee|Sustainable Development Advisory Committee) Minutes', c['text']) and c['text'] != candidates[0]['text'] for c in candidates):
                return None
        if len(titles) != 1:
            return None
        with fitz.open(original) as pdf:
            page = pdf[0]
            present = [w for w in page.get_text('words') if re.fullmatch('PRESENT:?', w[4], re.I)]
            staff = [w for w in page.get_text('words') if re.fullmatch('ATTENDING:?', w[4], re.I)]
            if len(present) != 1 or len(staff) != 1 or not 0 < present[0][1] < staff[0][1] < page.rect.height:
                return None
            clip = [0, present[0][1]-2, page.rect.width, staff[0][1]-1]
            roster_config = {'source_sha256':source['source_sha256'], 'helper_sha256':config['helper_sha256'],
                             'page':1, 'clip':clip, 'render_scale':6, 'header_receipt_sha256':proof['ocr_receipt_sha256']}
            key = hashlib.sha256(json.dumps(roster_config, sort_keys=True).encode()).hexdigest()
            folder = cache / 'present-roster-ocr' / source['source_sha256'] / key
            folder.mkdir(parents=True, exist_ok=True)
            image = folder / 'present.png'; receipt = folder / 'ocr.json'
            if not image.exists():
                page.get_pixmap(matrix=fitz.Matrix(6,6), clip=fitz.Rect(clip)).save(image)
        render_sha = hashlib.sha256(image.read_bytes()).hexdigest()
        if receipt.exists():
            saved = json.loads(receipt.read_text())
            if saved['config'] != roster_config or saved['render_sha256'] != render_sha:
                return None
            ocr = saved['ocr']
        else:
            binary = cache / 'native-header-ocr' / f"helper-{config['helper_sha256']}-{config['machine']}" / 'langford-native-ocr'
            ocr = json.loads(subprocess.run([str(binary), str(image)], check=True, capture_output=True, text=True, timeout=40).stdout)
            receipt.write_text(json.dumps({'config':roster_config, 'render_sha256':render_sha, 'ocr':ocr}, sort_keys=True))
        if ocr['engine'] != 'macOS Vision VNRecognizeTextRequest' or ocr['vision_revision'] != 3:
            return None
        lines = [line['candidates'][0] for line in ocr['lines'] if line['candidates']]
        if any(line['confidence'] != 1 for line in lines) or sum(bool(re.fullmatch('PRESENT:?', line['text'])) for line in lines) != 1:
            return None
        roster_text = '\n'.join(line['text'] for line in lines)
        ids = {person['id'] for _, _, person, ambiguity in _names(roster_text, patterns) if person is not None and ambiguity is None}
        if hashlib.sha256(original.read_bytes()).hexdigest() != source['source_sha256']:
            return None
        compact = {'method':'macos_vision_original_pdf_header_and_present_corroboration', 'committee_heading':titles[0],
                   'native_source_date':day, 'source_sha256':source['source_sha256'], 'helper_sha256':config['helper_sha256'],
                   'header_render_sha256':proof['render_sha256'], 'header_receipt_sha256':proof['ocr_receipt_sha256'],
                   'present_render_sha256':render_sha, 'present_receipt_sha256':hashlib.sha256(receipt.read_bytes()).hexdigest(),
                   'engine':ocr['engine'], 'vision_revision':ocr['vision_revision']}
        return titles[0].removesuffix(' Minutes'), compact, ids
    except (OSError, ValueError, KeyError, TypeError, IndexError, RuntimeError, subprocess.SubprocessError):
        return None


def _committee_present(source, patterns):
    """Read only the native member column; staff/absent columns never confer membership."""
    suffix = r'(?:[ \t]+Minutes)?'
    if source['source_format'] == 'official_html_structural':
        suffix = r'(?:[ \t]+Minutes|[ \t]*-[ \t]*(?:' + _MONTHS + r')\s+\d{1,2},\s*20\d{2})?'
    headings = re.findall(r'(?im)^[ \t]*(Community Advisory Committee|Sustainable Development Advisory Committee)' + suffix + r'[ \t]*$', source['source_header'])
    if source['source_format'] == 'official_html_structural':
        title_date = re.search(r'-[ \t]*(' + _MONTHS + r')\s+(\d{1,2}),\s*(20\d{2})[ \t]*$', source['source_header'].strip(), re.I)
        if title_date:
            try:
                title_day = datetime.strptime(' '.join(title_date.groups()), '%B %d %Y').date()
            except ValueError:
                return None
            if title_day != _day(source['local_date']):
                return None
    corroboration = None
    if len(headings) != 1:
        corroboration = _native_committee_ocr(source, patterns)
        if not corroboration:
            original = Path(__file__).resolve().parents[4] / source['source_file']
            if source['source_format'] == 'original_pdf_layout' and re.search(r'\bAdvisory\s+Committee\b', source['source_header'], re.I) and original.is_file():
                return '', '', [], 'committee_image_validation_unavailable', [], {}, None
            return None
        organization = corroboration[0]
    else:
        organization = ' '.join(word.capitalize() for word in headings[0].split())
    marker = re.search(r'\bPRESENT\s*:', source['text'], re.I)
    if not marker:
        return organization, '', [], 'committee_present_boundary_unknown', [], {}, None
    line_start = source['text'].rfind('\n', 0, marker.start()) + 1
    lines = source['text'][line_start:].splitlines()
    parallel = re.search(r'\bATTENDING\s*:', lines[0], re.I)
    column_end = parallel.start() if parallel else None
    selected = []; quote_lines = []; bounded = False
    for index, line in enumerate(lines):
        member_column = line[:column_end] if column_end is not None else line
        if index and re.match(r'^[ \t]*(?:ABSENT|ATTENDING|REGRETS)\b', member_column, re.I):
            bounded = True
            break
        selected.append(re.sub(r'\bPRESENT\s*:', '', member_column, count=1, flags=re.I) if index == 0 else member_column)
        quote_lines.append(line)
    if not bounded:
        return organization, '', [], 'committee_present_boundary_unknown', [], {}, None
    roster = '\n'.join(selected)
    quote = '\n'.join(quote_lines).lstrip(' \t').rstrip()
    names = _names(roster, patterns)
    mask = list(roster)
    for left, right, person, ambiguity in names:
        mask[left:right] = ' ' * (right-left)
    residue = re.sub(r'\b(?:Mayor|Councillors?|Committee|Members?|Chair|Vice|Acting|Remote|Remotely|and)\b', ' ', ''.join(mask), flags=re.I)
    if re.search(r'[A-Za-z0-9]', residue):
        return organization, quote, [], 'committee_present_unaccounted_tokens', [], {}, None
    ids = [person['id'] for _, _, person, _ in names if person is not None]
    if len(ids) != len(set(ids)):
        return organization, quote, [], 'committee_present_repeated_identity', [], {}, None
    absent = re.search(r'(?im)^[ \t]*(?:ABSENT|REGRETS)\b[ \t]*:?', source['text'][marker.end():])
    extra = []
    if absent:
        after = source['text'][marker.end()+absent.end():]
        boundary = re.search(r'(?im)^[ \t]*(?:ATTENDING\b|Meeting available|\d+\.\s|CALL TO ORDER)', after)
        absent_quote = after[:boundary.start()] if boundary else after
        absent_ids = {person['id'] for _, _, person, _ in _names(absent_quote, patterns) if person is not None}
        contradicted = set(ids) & absent_ids
        for pid in sorted(contradicted):
            extra.append({'person_id':pid, 'reason':'committee_present_absent_contradiction', 'source_quote':quote+'\nABSENT: '+absent_quote.rstrip()})
        names = [hit for hit in names if hit[2] is None or hit[2]['id'] not in contradicted]
    if corroboration:
        native_ids = {person['id'] for _, _, person, _ in names if person is not None}
        for pid in sorted(corroboration[2] - native_ids):
            extra.append({'person_id':pid, 'reason':'image_identity_not_substituted_for_native_text', 'source_quote':quote})
        for _, _, person, _ in names:
            if person is not None and person['id'] not in corroboration[2]:
                extra.append({'person_id':person['id'], 'reason':'native_text_image_roster_identity_disagreement', 'source_quote':quote})
        names = [hit for hit in names if hit[2] is None or hit[2]['id'] in corroboration[2]]
    per_person_quotes = {}
    if parallel:
        # Retain the already valid first-row witness when extending the left
        # member column; a geometry fix must not rewrite prior role evidence.
        first_marker = re.search(r'\bPRESENT\s*:', lines[0], re.I)
        first_quote = lines[0][first_marker.start():column_end].rstrip()
        per_person_quotes = {person['id']:first_quote for left, _, person, _ in names
                             if person is not None and left < len(selected[0])}
    return organization, quote, names, None, extra, per_person_quotes, corroboration[1] if corroboration else None


def participant_role_observations(source, *, meeting, people):
    """Return person-ID keyed, source-bound observations for this meeting only.

    Intended ingestion hook: merge these observations into
    ``meetings.meta.participant_roles`` after the original-minutes loader passes.
    The caller owns metadata CAS and preservation; this function never updates
    person memberships, council terms, transcript links or existing metadata.
    """
    reason = _source_hold(source, meeting)
    if reason:
        return {'status': 'source_held', 'observations': {}, 'holds': [{'reason': reason}]}
    text = source['text']; patterns = _person_patterns(people)
    observations: dict[str, ParticipantRoleObservation] = {}
    holds = []; conflicted = set()

    def add(person, role, organization, quote, evidence_kind, ambiguity=None, classification="government_staff", header_validation=None):
        if person is None:
            holds.append({'reason': ambiguity or 'ambiguous_initial_surname', 'source_quote': quote})
            return
        key = str(person['id'])
        if key in conflicted:
            return
        value = {'person_id': person['id'], 'meeting_id': meeting['id'], 'classification': classification,
                 'role': role, 'organization': organization, 'observed_date': _day(meeting['meeting_date']).isoformat(),
                 'native_source_date': _day(source['local_date']).isoformat(), 'method': METHOD,
                 'source_file': source['source_file'], 'source_sha256': source['source_sha256'],
                 'source_url': source['source_url'], 'source_quote': quote, 'evidence_kind': evidence_kind}
        if header_validation:
            value['header_validation'] = header_validation
        old = observations.get(key)
        if old and (old['role'].casefold(), old['organization'].casefold()) != (role.casefold(), organization.casefold()):
            observations.pop(key); conflicted.add(key)
            holds.append({'person_id': person['id'], 'reason': 'conflicting_explicit_meeting_roles'})
        else:
            observations.setdefault(key, value)

    committee = _committee_present(source, patterns)
    if committee:
        organization, quote, names, committee_hold, extra_holds, per_person_quotes, header_validation = committee
        holds.extend(extra_holds)
        if committee_hold:
            holds.append({'reason': committee_hold, 'source_quote': quote})
        else:
            for _, _, person, ambiguity in names:
                member_quote = per_person_quotes.get(person['id'], quote) if person is not None else quote
                add(person, 'Committee member', organization, member_quote, 'formal_committee_present_roster', ambiguity, 'committee_member', header_validation)

    # The original City/Town heading plus a municipal-only formal staff function
    # is required. Generic private-sector titles are never enough.
    city = re.search(r'\b((?:City|Town|Village|District) of [A-Za-z][A-Za-z -]{1,45})\s*\n', source['source_header'])
    if city and ' '.join(city[1].casefold().split()) != 'city of langford':
        holds.append({'reason': 'municipal_organization_heading_unknown', 'source_quote': city[0].rstrip()})
        city = None
    if city:
        for entry in _roster_entries(text, patterns):
            role = ' '.join(entry['role'].split()).strip(' ,')
            if _MUNICIPAL.fullmatch(role):
                add(entry['person'], role, city[1].strip(), entry['source_quote'], 'formal_attending_municipal_function', entry['reason'])

    for left, right, person, ambiguous in _names(text, patterns):
        if not re.match(r'\s*,', text[right:]):
            continue
        paragraph_start, paragraph_end = _paragraph(text, left)
        before = text[paragraph_start:left]
        if re.search(r'\b(?:Mayor|Councillors?|Board Director)\s*$', before, re.I):
            continue
        after = text[right:paragraph_end].lstrip(' ,\n\t')
        if not _STAFF.match(after):
            continue
        organizations = [(m.start(), m.end(), organization) for expression, organization in _ORGANIZATIONS
                         for m in expression.finditer(after)]
        if not organizations:
            continue
        organization_start, organization_end, organization = min(organizations)
        role = ' '.join(after[:organization_start].split()).strip(' ,')
        if len(role) > 160 or _names(role, patterns):
            continue
        action = after[organization_end:]
        if not re.match(r'^\s*(?:\([A-Z]{2,8}\))?\s*,?\s*(?:provided|presented|responded|answered|spoke|addressed|outlined|explained|attended)\b', action, re.I):
            continue
        quote = text[left:paragraph_end].rstrip()
        add(person, role, organization, quote, 'explicit_public_body_role_and_actual_participation', ambiguous)
    if any(h['reason'] == 'committee_image_validation_unavailable' for h in holds):
        # The metadata caller must retain prior evidence when an image engine
        # is unavailable, rather than interpreting missing observations as removal.
        return {'status': 'source_held', 'observations': {}, 'holds': holds}
    return {'status': 'parsed', 'observations': observations, 'holds': holds}
