"""Bind native and rendered witnesses to 36 identity/source-correction statuses."""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import hashlib,json,re,unicodedata,fitz

ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
native_path=OUT/'legacy36-independent-native-review.json';native=json.loads(native_path.read_text())
proposal_path=OUT/'legacy-source-identity-triage-v2.json';proposal=json.loads(proposal_path.read_text());by_id={r['motion_id']:r for r in proposal['proposals']}
prior_path=OUT/'canonical-nonexact-rendered-text-review.json';prior=json.loads(prior_path.read_text());prior_by_id={r['legacy_motion_id']:r for r in prior['records']}

def norm(s):
    s=re.sub(r'\bTHAT(?=Council\b|Committee\b)','THAT ',s,flags=re.I)
    return ' '.join(re.findall(r'[a-z0-9]+',unicodedata.normalize('NFKC',s).casefold()))

def match_lines(image, target):
    ocr_path=Path(image['ocr_path']);ocr=json.loads(ocr_path.read_text());parts=[norm(line['candidates'][0]['text']) for line in ocr['lines']]
    text=' '.join(parts);wanted=norm(target);count=text.count(wanted);found=text.find(wanted);selected=[];offset=0
    if count==1:
        for line,part in zip(ocr['lines'],parts):
            end=offset+len(part)
            if offset<found+len(wanted) and found<end:selected.append(line)
            offset=end+1
    return {'page':image['page'],'image_path':image['image_path'],'image_sha256':image['image_sha256'],'ocr_path':str(ocr_path),
            'ocr_sha256':hashlib.sha256(ocr_path.read_bytes()).hexdigest(),'exact_normalized_occurrences':count,
            'minimum_top_candidate_confidence':min((line['candidates'][0]['confidence'] for line in selected),default=None),
            'bounded_lines':selected}

reviews=[];lexical=[]
lexical_ids={r['motion_id'] for r in proposal['proposals'] if r['mapping_method']=='unique_exact_native_body_all_archive'}
literal_eligible={1007,1131,1519,1525,1773,3509}
for row in native['reviews']:
    mid=row['motion_id'];p=by_id[mid];s=p['candidates'][0]
    identity_verified=row['exact_full_formal_witness_occurrences']==1
    evidence=[];method='independent_PyMuPDF_unique_entire_formal_witness'
    for image in row['images']:
        evidence.append({'body':match_lines(image,row['original_motion_text']), 'full_formal_witness':match_lines(image,row['full_formal_witness'])})
    if mid in lexical_ids:
        assert norm(row['original_motion_text'])==norm(row['official_motion_text'])
        body=[entry['body'] for entry in evidence if entry['body']['exact_normalized_occurrences']==1]
        assert len(body)==1
        lexical_lines=[line for line in body[0]['bounded_lines'] if re.search(r'\bTHAT\s+Council\b',line['candidates'][0]['text'],re.I)]
        assert lexical_lines and all(line['candidates'][0]['confidence']>=.99 for line in lexical_lines)
        lexical_confidence=min(line['candidates'][0]['confidence'] for line in lexical_lines)
        if not identity_verified:
            witnesses=[entry['full_formal_witness'] for entry in evidence if entry['full_formal_witness']['exact_normalized_occurrences']==1]
            assert len(witnesses)==1
            identity_verified=True;method='rendered_primary_page_unique_entire_formal_witness'
        lexical.append({'motion_id':mid,'source_file':s['source_file'],'source_sha256':s['source_sha256'],
            'existing_readable_text':row['original_motion_text'],'raw_native_text':row['official_motion_text'],
            'only_lexical_change':'literal THATCouncil -> THAT Council','all_other_normalized_words_identical':True,
            'independent_unique_full_formal_witness':identity_verified,'body_rendered_evidence':body[0],
            'lexical_join_line_minimum_confidence':lexical_confidence,'raw_source_body_rewritten':False,'database_body_rewritten':False})
    if mid in (1131,1132):
        matching=[entry['full_formal_witness'] for entry in evidence if entry['full_formal_witness']['exact_normalized_occurrences']==1]
        assert len(matching)==1 and matching[0]['minimum_top_candidate_confidence']>=.99
        identity_verified=True;method='rendered_primary_page_unique_entire_formal_witness'
    if mid==1959:
        # Both the formal motion and actors repeat. The original agenda10.1
        # distinguishes this decision from the expressly re-read item10.13.
        scope=s['agenda_number_hint']+' '+s['agenda_title_hint']+' '+row['full_formal_witness']
        assert s['agenda_number_hint']=='10.1'
        matches=[match_lines(image,scope) for image in row['images']]
        assert sum(e['exact_normalized_occurrences'] for e in matches)==1
        evidence.append({'agenda_bounded_formal_witness':next(e for e in matches if e['exact_normalized_occurrences']==1)})
        identity_verified=True;method='rendered_exact_agenda10_1_plus_actors_whole_motion_outcome_distinguishes_reread10_13'
    prior_evidence=None
    if mid in prior_by_id:
        previous=prior_by_id[mid]
        assert previous['source_binary_sha256']==s['source_sha256']
        image=Path(previous['render_path']);assert image.exists() and hashlib.sha256(image.read_bytes()).hexdigest()==previous['render_sha256']
        prior_evidence={'review_file':str(prior_path.relative_to(ROOT)),'review_sha256':hashlib.sha256(prior_path.read_bytes()).hexdigest(),
            'source_sha256':previous['source_binary_sha256'],'render_sha256':previous['render_sha256'],'page':previous['page_one_based']}
        identity_verified=True;method='frozen_independent_rendered_review_same_original_binary_and_verified_render_hash'
    assert identity_verified,mid
    if mid in lexical_ids:status='verified_lexical_only_no_database_text_change_needed'
    elif mid in prior_by_id:status='verified_identity_typography_policy_hold_preserve_readable_text'
    elif mid==3199:status='verified_identity_clerk_narrative_boundary_hold'
    elif mid in (1132,1133):status='verified_identity_printed_redundant_council_wrapper_display_policy_hold'
    elif mid in literal_eligible:status='verified_source_correction_eligible_guarded_text_only_CAS'
    else:
        assert norm(row['original_motion_text'])==norm(row['official_motion_text'])
        status='verified_repeated_formal_identity_needs_source_key_binding_not_text_rewrite'
    reviews.append({'motion_id':mid,'meeting_id':row['meeting_id'],'source_key':row['source_key'],'source_file':row['source_file'],'source_sha256':row['source_sha256'],
        'identity_verified':identity_verified,'identity_method':method,'status':status,'original_motion_text':row['original_motion_text'],'official_motion_text':row['official_motion_text'],
        'stored_result':p['stored_result'],'official_result':s['source_result'],'actors':row['actors'],'stored_agenda_number':p['stored_agenda_number'],
        'source_agenda_hint':s['agenda_number_hint'],'agenda_relink_authorized':False,'numbers_equal':row['numbers_equal'],'negation_equal':row['negation_equal'],
        'actions_equal':row['actions_equal'],'full_formal_witness':row['full_formal_witness'],'rendered_evidence':evidence,'prior_rendered_evidence':prior_evidence,
        'ballot_eligibility_certified_by_identity_review':False,'live_writes':0})
lexical_report={'mode':'read_only_14_exact_lexical_join_native_rendered_review','at':datetime.now(timezone.utc).isoformat(),
    'proposal_sha256':hashlib.sha256(proposal_path.read_bytes()).hexdigest(),'summary':{'candidates':len(lexical),'all_rendered_bodies_exactly_once':True,
    'all_other_words_identical':True,'minimum_lexical_join_line_ocr_confidence':min(r['lexical_join_line_minimum_confidence'] for r in lexical),
    'minimum_wrapped_body_line_ocr_confidence':min(r['body_rendered_evidence']['minimum_top_candidate_confidence'] for r in lexical),
    'paid_model_calls':0,'live_writes':0},'reviews':lexical}
(OUT/'lexical14-native-rendered-review.json').write_text(json.dumps(lexical_report,indent=2)+'\n')
report={'mode':'read_only_final_36_source_identity_and_correction_policy_review','at':datetime.now(timezone.utc).isoformat(),
    'input_sha256':{str(path.name):hashlib.sha256(path.read_bytes()).hexdigest() for path in [proposal_path,native_path,prior_path]},
    'summary':{'identities':len(reviews),'independently_verified':sum(r['identity_verified'] for r in reviews),'statuses':dict(Counter(r['status'] for r in reviews)),
    'live_writes':0,'paid_model_calls':0},'reviews':reviews}
(OUT/'legacy36-source-only-correction-plan.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report['summary'],indent=2))
