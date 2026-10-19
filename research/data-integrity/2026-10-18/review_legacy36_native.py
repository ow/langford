"""Independent native-engine binding and rendered source review for 36 identities.

No proposal verdict is proof: reopen/hash original source, independently extract
with PyMuPDF (not the pdftotext production parser), and require the complete
MOVED/SECONDED/body/outcome witness. Original seven rendered-typography holds
remain holds. Local rendered OCR evidence is collected separately, never used
as an unbounded alias or global text replacement.
"""
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
import hashlib,json,re,unicodedata
import fitz
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
proposal_path=OUT/'legacy-source-identity-triage-v2.json';proposal_bytes=proposal_path.read_bytes();data=json.loads(proposal_bytes)
TMP=Path('/private/tmp/langford-legacy36-native-review');TMP.mkdir(exist_ok=True)


def normalized(value):
    value=unicodedata.normalize('NFKC',value)
    value=re.sub(r'\bTHAT(?=Council\b|Committee\b)','THAT ',value,flags=re.I)
    return ' '.join(re.findall(r'[a-z0-9]+',value.casefold()))

cache={};reviews=[]
known_literal_holds={1557,1943,3299,3326,3328,3399,3654}
for row in data['proposals']:
    source=row['candidates'][0];path=ROOT/source['source_file'];binary_sha=hashlib.sha256(path.read_bytes()).hexdigest()
    assert binary_sha==source['source_sha256']
    if binary_sha not in cache:
        if path.suffix.lower()=='.pdf':
            document=fitz.open(path);pages=[page.get_text('text',sort=True) for page in document]
            native='\n'.join(pages)
            native=re.sub(r'(?im)^\s*Minutes of[^\n]*\n','\n',native)
            native=re.sub(r'(?m)^\s*\d+\s*$','',native)
            cache[binary_sha]={'pages':pages,'normalized_native':normalized(native),'document':document,'engine':'PyMuPDF sorted native text'}
        else:
            soup=BeautifulSoup(path.read_text(),'html.parser')
            nodes=soup.select('.AgendaItemMotion')
            cache[binary_sha]={'nodes':nodes,'engine':'original structural HTML AgendaItemMotion DOM'}
    native=cache[binary_sha]
    block=source['source_block'];outcome_at=block.find(source['outcome_quote'])
    witness=block[:outcome_at+len(source['outcome_quote'])]
    page_candidates=[]
    if 'document' in native:
        full_count=native['normalized_native'].count(normalized(witness))
        body_count=native['normalized_native'].count(normalized(source['raw_motion_text']))
        page_candidates=[i+1 for i,page in enumerate(native['pages']) if normalized(source['raw_motion_text']) in normalized(page)]
        if not page_candidates:
            suffix=' '.join(normalized(source['raw_motion_text']).split()[-8:])
            page_candidates=[i+1 for i,page in enumerate(native['pages']) if suffix in normalized(page)]
        if row['motion_id'] in (1131,1132):page_candidates=[7]
    else:
        full_count=0;body_count=0
        for node in native['nodes']:
            body=' '.join(part.get_text(' ',strip=True) for part in node.select('.MotionText'))
            if normalized(body)==normalized(source['raw_motion_text']):
                body_count+=1
                mover=node.select_one('.MovedBy .Value');seconder=node.select_one('.SecondedBy .Value');result=node.select_one('.MotionResult')
                if mover and seconder and result and normalized(mover.get_text())==normalized(source['mover']) and normalized(seconder.get_text())==normalized(source['seconder']) and normalized(source['source_result']) in normalized(result.get_text()):full_count+=1
    category='source_correction_proposed_requires_guarded_row_CAS'
    if row['motion_id'] in known_literal_holds:category='known_rendered_source_typography_hold_preserve_readable_body'
    elif row['motion_id']==3199:category='clerk_narrative_in_formal_body_hold_until_boundary_review'
    elif normalized(row['original_motion_text'])==normalized(source['raw_motion_text']):
        category='source_identity_binding_only_existing_body_readable'
    if full_count!=1:category='independent_native_witness_not_unique_or_text_engine_difference_hold'
    images=[]
    # Render the lexical-boundary cases without replacing any document/archive.
    if (row['mapping_method']=='unique_exact_native_body_all_archive' or row['motion_id'] in (1131,1132,1959)) and page_candidates and 'document' in native:
        for page_number in page_candidates:
            image_path=TMP/f'{binary_sha}-p{page_number}.png'
            if not image_path.exists():native['document'][page_number-1].get_pixmap(matrix=fitz.Matrix(2.5,2.5)).save(image_path)
            images.append({'page':page_number,'image_path':str(image_path),'image_sha256':hashlib.sha256(image_path.read_bytes()).hexdigest(),
                           'ocr_path':str(image_path.with_suffix('.vision.json'))})
    reviews.append({'motion_id':row['motion_id'],'meeting_id':row['meeting_id'],'source_key':source['key'],'source_file':source['source_file'],'source_sha256':binary_sha,
        'independent_engine':native['engine'],'exact_full_formal_witness_occurrences':full_count,'exact_full_body_occurrences':body_count,'page_candidates':page_candidates,
        'full_formal_witness':witness,'original_motion_text':row['original_motion_text'],'official_motion_text':source['raw_motion_text'],
        'actors':{'stored_mover':row['stored_mover'],'source_mover':source['mover'],'stored_seconder':row['stored_seconder'],'source_seconder':source['seconder']},
        'protected_original':row['protected_original'],'protected_source':source['protected_source'],'numbers_equal':source['numbers_equal'],
        'negation_equal':source['negation_equal'],'actions_equal':source['actions_equal'],'added_source_tokens':source['added_source_tokens'],
        'review_status':category,'images':images,'live_writes':0,'ballot_eligibility_certified_by_identity_review':False})
assert proposal_path.read_bytes()==proposal_bytes
report={'mode':'read_only_independent_native36_source_identity_review','at':datetime.now(timezone.utc).isoformat(),'proposal_sha256':hashlib.sha256(proposal_bytes).hexdigest(),
    'summary':{'proposals':len(reviews),'independent_unique_full_formal_witnesses':sum(r['exact_full_formal_witness_occurrences']==1 for r in reviews),
    'statuses':dict(Counter(r['review_status'] for r in reviews)),'rendered_lexical_boundary_pages':sum(len(r['images']) for r in reviews),'live_writes':0,'paid_model_calls':0},'reviews':reviews}
(OUT/'legacy36-independent-native-review.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report['summary'],indent=2))
