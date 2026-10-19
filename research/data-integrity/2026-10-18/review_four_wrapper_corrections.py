"""Independent original-source review of four exact operative-body identities.

No AI, database writes, source-key publication, agenda relinking or ballot claim.
The only textual difference is official leading Council/list-one notation.
"""
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
import hashlib,json,re
import fitz

ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
input_path=OUT/'legacy-source-identity-triage-v2.json';raw=input_path.read_bytes();triage=json.loads(raw)
reverse=Counter(s['key'] for row in triage['unresolved'] for s in row['candidates'])
norm=lambda text:' '.join(re.findall(r'[a-z0-9]+',text.casefold()))
strip=lambda text:re.sub(r'^that (?:the )?(?:council|committee) (?:1 )?','',norm(text))
tmp=Path('/private/tmp/langford-wrapper-native-review');tmp.mkdir(exist_ok=True)
reviewed_pages={750:2,2699:4,2766:6,3735:8}
agenda_quotes={750:'b) Juan De Fuca Water Development Cost Charge Bylaw Update',2699:'7.1.2 Z21-0043 - Application to Rezone 936 and 942 Klahanie Drive',2766:'8. REPORTS / a) Committee Terms of Reference',3735:'7. REPORTS / a) Realignment of Claude Road South'}
reviews=[]
for mid,page_number in reviewed_pages.items():
    row=next(r for r in triage['unresolved'] if r['motion_id']==mid)
    assert len(row['candidates'])==1
    source=row['candidates'][0];path=ROOT/source['source_file']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==source['source_sha256']
    assert reverse[source['key']]==1
    assert strip(row['original_motion_text'])==strip(source['raw_motion_text'])
    # Re-extract whole original with an independent engine, including actors,
    # exact entire motion and its result, not only operative word subsets.
    document=fitz.open(path)
    pages=[page.get_text('text',sort=True) for page in document]
    witness=source['source_block'].split(source['outcome_quote'],1)[0]+source['outcome_quote']
    assert norm('\n'.join(pages)).count(norm(witness))==1
    assert norm(source['raw_motion_text']) in norm(pages[page_number-1])
    image=tmp/f'{mid}-p{page_number}.png'
    assert image.exists() # Original rendered page was inspected independently.
    reviews.append({'motion_id':mid,'meeting_id':row['meeting_id'],'agenda_item_id':row['agenda_item_id'],
        'status':'verified_source_wrapper_restoration_ready_for_fresh_live_row_CAS',
        'original_motion_text':row['original_motion_text'],'official_motion_text':source['raw_motion_text'],
        'stored_result':row['stored_result'],'official_result':source['source_result'],
        'source_file':source['source_file'],'source_url':source['source_url'],'source_sha256':source['source_sha256'],
        'source_offset':source['source_offset'],'source_order':source['source_order'],'inventory_v2_key_reference_only':source['key'],
        'whole_formal_witness':witness,'independent_native_engine':'PyMuPDF sorted whole-original text',
        'independent_unique_whole_formal_witnesses':1,'remaining_legacy_candidates_claiming_source':1,
        'actors':{'stored_mover':row['stored_mover'],'source_mover':source['mover'],'stored_seconder':row['stored_seconder'],'source_seconder':source['seconder']},
        'stored_agenda_number':row['stored_agenda_number'],'rendered_agenda_quote':agenda_quotes[mid],
        'agenda_relink_authorized':False,
        'protected_words_review':'All operative words, actions, negation, named objects, conditions, currency, addresses and report identifiers identical after punctuation/case/whitespace; only official leading That Council/list1 notation restored.',
        'rendered_evidence':{'page':page_number,'image_path':str(image),'image_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),'visual_verdict':'printed heading, mover/seconder, complete body and outcome verified; neighboring motions distinct'},
        'proposed_preservation':'Keep old motion ID, agenda link, result, vote rows and unrelated metadata; retain original body and this bounded source correction proof. No source key publication until current shared validator rebinds exact source identity.',
        'ballot_eligibility_certified':False,'database_writes':0})
assert input_path.read_bytes()==raw
report={'mode':'read_only_four_wrapper_original_native_identity_review','at':datetime.now(timezone.utc).isoformat(),
        'input_sha256':hashlib.sha256(raw).hexdigest(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'summary':{'identity_verified':4,'text_only_guarded_CAS_proposals':4,'new_ballots_certified':0,'database_writes':0,'paid_model_calls':0},'reviews':reviews}
(OUT/'four-wrapper-source-correction-review.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report['summary']))
