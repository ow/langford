"""Bounded primary-source evidence for unparsed outcome leads; no writes to DB."""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import hashlib,json,re,subprocess
from pipeline.ingestion.official_ballots import html_minutes_text
from pipeline.ingestion.vote_evidence import normalize_text

ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
inventory=json.loads((OUT/'canonical-official-motion-inventory-v2.json').read_text())
rows=[]
for source in inventory['sources']:
    if not source.get('unbound_outcome_leads'):continue
    path=ROOT/source['source_file']
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest==source['source_sha256']
    text=subprocess.check_output(['pdftotext','-layout',str(path),'-'],text=True) if path.suffix.lower()=='.pdf' else html_minutes_text(path)
    clean=re.sub(r'(?im)^\s*Minutes of[^\n]*\n','\n',text)
    clean=re.sub(r'(?m)^\s*\d+\s*$','',clean).replace('\f','\n')
    for lead in source['unbound_outcome_leads']:
        offset=lead['source_offset'];before=clean[max(0,offset-1800):offset]
        snippet=before+clean[offset:offset+350]
        category='source_structure_requires_review'
        if re.match(r'carried out\b',lead['source_quote'],re.I):category='narrative_not_decision'
        elif re.search(r'(?m)^[ \t]*(?:Amendment:[ \t]*|\.[ \t]+)MOVED[ \t]+BY[ \t]*:',before,re.I):category='literal_formal_heading_variant'
        elif re.search(r'\b(?:iVIOVED|IVIOVED|iVlOVED|MpyED|MOVE0|MOVEDBYl)',before,re.I):category='ocr_mover_heading_requires_rendered_machine_review'
        elif re.search(r'RISE AND REPORT',before,re.I):category='reported_resolution_needs_closed_session_scope_review'
        # Locate exact local source words on native pages. Multiple/no matches
        # remain uncertain rather than assigning an invented page number.
        anchor=' '.join(normalize_text(before).split()[-12:])+ ' '+normalize_text(lead['source_quote'])
        pages=[i+1 for i,page in enumerate(text.split('\f')) if anchor in normalize_text(page)]
        rows.append({'meeting_id':source['meeting_id'],'source_file':source['source_file'],'source_sha256':digest,
            'source_offset':offset,'outcome_quote':lead['source_quote'],'native_context':snippet,
            'page_candidates':pages,'page_locator':'exact_normalized_last12words_plus_outcome',
            'triage':category,'decision_or_ballot_certified':False})
report={'mode':'read_only_native_outcome_lead_triage','at':datetime.now(timezone.utc).isoformat(),
    'inventory_sha256':hashlib.sha256((OUT/'canonical-official-motion-inventory-v2.json').read_bytes()).hexdigest(),
    'summary':{'leads':len(rows),'triage':dict(Counter(r['triage'] for r in rows)),
        'uniquely_located_native_pages':sum(len(r['page_candidates'])==1 for r in rows),'live_writes':0,'paid_model_calls':0},'leads':rows}
(OUT/'unbound-native-outcome-leads-review.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report['summary'],indent=2))
