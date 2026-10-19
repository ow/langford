"""Read-only original-PDF header date review, with local rendered OCR receipts.

No catalog date supplies a missing digit. All dates below were independently
read from rendered page-one headers; catalog dates are compared only afterwards.
OCR failure on an ordinal stays a machine-parser hold, even when readable here.
"""
from pathlib import Path
from datetime import date, datetime, timezone
from collections import Counter
import hashlib,json,re
import fitz

ROOT=Path(__file__).resolve().parents[3]; OUT=Path(__file__).parent
TMP=Path('/private/tmp/langford-native-header-review')
names=['current-full-ballot-audit.json','ballot-source-current-snapshot.json','canonical-official-motion-inventory-v3.json','legacy36-source-only-correction-plan.json']
raw={name:(OUT/name).read_bytes() for name in names}
audit,snapshot,inventory,corrections=(json.loads(raw[name]) for name in names)
held=[r for r in audit['motions'] if r['status']=='source_date_unknown']
six={1007,1131,1519,1525,1773,3509}
related=[r for r in corrections['reviews'] if r['motion_id'] in six]
ids={r['meeting_id'] for r in held+related}
# Independently legible rendered header dates, never inferred from filename.
read_dates={20:('2026-03-17',None),55:('2019-10-07','Monday'),70:('2020-03-19','Thursday'),87:('2020-02-25','Tuesday'),109:('2019-12-02','Monday'),120:('2019-04-01','Monday'),141:('2020-05-21','Thursday'),144:('2016-11-21','Monday'),153:('2020-06-01','Monday'),353:('2016-04-18','Monday')}
reviews=[]
for mid in sorted(ids):
    source=next(r for r in inventory['sources'] if r['meeting_id']==mid)
    path=ROOT/source['source_file']; sha=hashlib.sha256(path.read_bytes()).hexdigest()
    assert sha==source['source_sha256']
    doc=fitz.open(path); page=doc[0]; printed_date,weekday=read_dates[mid]
    native=page.get_text('text',sort=True)
    base=TMP/f'{mid}-{sha}-header.png'
    variants=[]
    for img in [base,TMP/f'{mid}-header-6x.png']:
        if not img.exists():continue
        op=img.with_suffix('.vision.json');ocr=json.loads(op.read_text())
        # Require a month name and year on the same full header line.
        month=date.fromisoformat(printed_date).strftime('%B');year=printed_date[:4]
        lines=[line for line in ocr['lines'] if any(month in c['text'] and year in c['text'] for c in line['candidates'])]
        variants.append({'image_path':str(img),'image_sha256':hashlib.sha256(img.read_bytes()).hexdigest(),'ocr_path':str(op),'ocr_sha256':hashlib.sha256(op.read_bytes()).hexdigest(),'engine':ocr['engine'],'date_lines':lines})
    assert variants
    day=date.fromisoformat(printed_date).day
    # Strict grammatical ordinal only, not replacing OCR s/5 with st.
    expression=rf'\b{re.escape(date.fromisoformat(printed_date).strftime("%B"))}\s+{day}(?:st|nd|rd|th)?\s*,\s*{printed_date[:4]}\b'
    matches=[(v,line,c) for v in variants for line in v['date_lines'] for c in line['candidates'] if re.search(expression,c['text']) and c['confidence']>=.95]
    computed=date.fromisoformat(printed_date).strftime('%A')
    assert not weekday or weekday==computed
    meeting=next(r for r in snapshot['meetings'] if r['id']==mid)
    catalog_date=str(meeting['meeting_date'])[:10]
    node=next(r for r in inventory['canonical_motions'] if r['meeting_id']==mid)
    reviews.append({'meeting_id':mid,'source_file':source['source_file'],'source_url':node['source_url'],'source_sha256':sha,'page':1,
        'render_clip':{'base':'full page width, top52%,3x','supplement':'full page width, top24%,6x if present'},
        'native_header_text':native.split('PRESENT')[0],'printed_date_independent_rendered_review':printed_date,'printed_weekday':weekday,
        'computed_weekday':computed,'weekday_matches':weekday==computed if weekday else None,'catalog_date_comparison_only':catalog_date,'catalog_matches':catalog_date==printed_date,
        'machine_status':'strict_local_OCR_complete_date_candidate' if matches else 'hold_ordinal_OCR_incomplete_despite_legible_rendered_date',
        'rendered_visual_review':'complete printed day, month, year legible; ordinal21st on144 requires visual supplement; no catalog digit supplied',
        'ocr_variants':variants,'strict_matching_candidates':[{'text':c['text'],'confidence':c['confidence'],'bounding_box':line['bounding_box'],'image_sha256':v['image_sha256']} for v,line,c in matches],
        'held_decision_ids':[r['motion_id'] for r in held if r['meeting_id']==mid],
        'six_correction_ids':[r['motion_id'] for r in related if r['meeting_id']==mid],
        'ballot_eligibility_certified':False,'database_writes':0})
assert all((OUT/name).read_bytes()==content for name,content in raw.items())
report={'mode':'read_only_original_native_PDF_header_date_recovery_proposals','at':datetime.now(timezone.utc).isoformat(),
    'input_sha256':{n:hashlib.sha256(b).hexdigest() for n,b in raw.items()},'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'summary':{'source_date_unknown_decisions':len(held),'deduplicated_held_sources':len({r['meeting_id'] for r in held}),'additional_six_correction_sources':len(ids)-len({r['meeting_id'] for r in held}),
        'reviewed_original_PDFs':len(reviews),'machine_statuses':dict(Counter(r['machine_status'] for r in reviews)),
        'held_decisions_with_strict_local_OCR_date':sum(len(r['held_decision_ids']) for r in reviews if r['machine_status']=='strict_local_OCR_complete_date_candidate'),
        'printed_weekday_matches':sum(r['weekday_matches'] is True for r in reviews),'printed_weekday_not_present':sum(r['printed_weekday'] is None for r in reviews),
        'database_writes':0,'production_edits':0,'paid_model_calls':0},
    'automation_limits':['OCR confidence is not calibrated probability; admission also requires original source hash, header location, full date syntax, weekday agreement where printed, and catalog comparison only after independent recovery.',
        'Meeting144 cannot pass strict OCR from current output: 215/21s is not a valid ordinal. Do not silently strip digits or substitute catalog day.',
        'This is a date-only proposal; roster, presence, policy, formal-motion identity, outcomes, and complete choices still require shared-validator replay.',
        'Production has no new OCR date fallback from this research-only review; a guarded Mac-native OCR integration with persisted evidence remains future work.'],
    'reviews':reviews}
(OUT/'native-header-date-recovery-proposals.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report['summary'],indent=2))
