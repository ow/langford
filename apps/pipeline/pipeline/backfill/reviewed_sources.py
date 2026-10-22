"""Explicit original-image/source reviews for deterministic catch-up only.

Scans stay scans. Reviewed OCR never becomes official HTML/native PDF text,
attendance or ballot authority. Original files are never rewritten.
"""
import hashlib
import json
from pathlib import Path
import subprocess

import fitz

from pipeline.ingestion.source_claims import digest
from pipeline.ingestion.official_ballots import minutes_text_source
from pipeline.ingestion.canonical_motions import source_identity

STORE = Path(__file__).parent / 'data' / 'source-reviews'
ENROLLED = {
    204: '5ef923f4489f7478ea8a9cdd7a2655ec0bd67f7bf73ba0f0cda5c0040e1bdf4d',
    279: 'd5115af4efe65cc5c5e6f3511d97533695aacb2ba17468c917544a6414a005de',
    73: '4ed3f3b9e308c55f8d5229cf555413140277e8fd4ec3203ad750cd5a4ce03702',
    119: '93442224718402c931e205cefb6a5dfd2f64a5c712d8049bcea9367acfec70a4',
    217: 'a34c18f51ddae5a218078850d1bb1619923a6d64dd276cc60c4f7180f0e718c2',
    303: 'ce234e2aaf8ce032ee1d5f97f593229d55eed4c0842ce9d6fab90207dca5ed56',
    123: '29347cdade7c6905337d1a62360784cf18dcb429a8ad9a56c9c3a2d58d6c4e4e',
    86: '433959b2389fecf540475f4713bdd369486c5aee3fea501d99c730f967cae035',
    125: 'f0c2cc7b09696130b1b8f65115d2c2291580301f3f1cd6faf823a5fd5e6e599f',
    282: '201f37a3898585f87d5151e89c9ca646d43932e0424d66b8db4b968ea99942b6',
    144: '7b46190e4bd93effc9d0292d5d3c80a65dfae7aa25856796442e9c687873aab8',
}


def sha(value):
    return hashlib.sha256(value).hexdigest()


def bound_file(root, name, expected):
    path = root / name
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or sha(path.read_bytes()) != expected:
        raise ValueError('Reviewed source file changed')
    return path


def source_inventory(root, meeting):
    folder = root / meeting['archive_path'] / 'Minutes'
    if not folder.resolve().is_relative_to(root.resolve()):
        raise ValueError('Source inventory escapes archive root')
    entries=[]
    for path in sorted(folder.glob('*')):
        if path.suffix.lower() not in ('.pdf','.html'):
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('Untrusted original source path')
        sidecar=Path(str(path)+'.url')
        if sidecar.is_symlink():
            raise ValueError('Untrusted original URL sidecar')
        entries.append({'file':str(path.relative_to(root)), 'sha256':sha(path.read_bytes()),
                        'url':sidecar.read_text().strip() if sidecar.exists() else None})
    return entries


def validate_source_review(review, *, meeting, root, project_ref, municipality_id):
    if (review['schema'] != 'reviewed-original-minutes-v1' or review['project_ref'] != project_ref
            or review['municipality_id'] != municipality_id
            or any(meeting.get(k) != v for k,v in review['catalog'].items())
            or sorted(review['file_inventory'],key=lambda r:r['file']) != source_inventory(root,meeting)):
        raise ValueError('Reviewed source catalog/inventory changed')
    for file in review['file_inventory']:
        bound_file(root,file['file'],file['sha256'])
    if review['review_status'] != 'independently_reviewed_original_source':
        raise ValueError('Original source review not complete')


def source_from_review(review, *, meeting, root, people, cache_dir, project_ref, municipality_id):
    validate_source_review(review,meeting=meeting,root=root,project_ref=project_ref,municipality_id=municipality_id)
    proof = {'review_sha256':digest(review),'mode':review['mode'],'authority':'deterministic_catchup_only',
             'file_inventory':review['file_inventory'], 'catalog':review['catalog']}
    if review['mode']=='no_decisions_expected':
        notice=review['notice'];bound_file(root,notice['file'],notice['sha256'])
        return {'error':'no_decisions_expected_from_original_notice', 'notice':notice,
                'source_file':notice['file'],'source_sha256':notice['sha256'],'source_url':notice['url'],
                'source_review_evidence':proof}
    path=bound_file(root,review['selected_file'],review['source_sha256'])
    if review['mode']=='reviewed_scan':
        if fitz.VersionBind!=review['pymupdf_version']:
            raise ValueError('Reviewed scan renderer changed')
        helper=Path(__file__).parents[1]/'ingestion'/'native_header_vision.swift'
        if sha(helper.read_bytes())!=review['helper_source_sha256']:
            raise ValueError('Reviewed OCR helper changed')
        with fitz.open(path) as document:
            if [p['page'] for p in review['pages']]!=list(range(1,len(document)+1)):
                raise ValueError('Reviewed scan pages incomplete')
            for page in review['pages']:
                image=document[page['page']-1].get_pixmap(matrix=fitz.Matrix(review['render_scale'],review['render_scale']))
                if (sha(image.tobytes('png'))!=page['render_sha256'] or page['source_sha256']!=review['source_sha256']
                        or page['source_url']!=review['source_url'] or page['render_scale']!=review['render_scale']
                        or page['ocr']['engine']!='macOS Vision VNRecognizeTextRequest' or page['ocr']['vision_revision']!=3):
                    raise ValueError('Reviewed scan image/OCR provenance changed')
        text=review['reviewed_text'];source_format='original_pdf_reviewed_local_ocr'
    else:
        with fitz.open(path) as document:
            if sha(document[0].get_text().encode())!=review['native_first_page_sha256']:
                raise ValueError('Reviewed native header changed')
        text=subprocess.run(['pdftotext','-layout',str(path),'-'],check=True,capture_output=True,text=True,timeout=40).stdout
        source_format='original_pdf_layout'
    source=minutes_text_source(meeting,root=root,people=people,cache_dir=cache_dir,path=path,text=text,
                               source_format=source_format,source_sha256=review['source_sha256'])
    if source.get('error'):
        return source
    if source['source_url']!=review['source_url']:
        raise ValueError('Reviewed original public URL changed')
    source['source_review_evidence']=proof
    if review.get('header_date'):
        source['local_date']=review['header_date']['date']
        source['source_date_evidence']={'method':'reviewed_original_image_header_date',**review['header_date'],**proof}
        from pipeline.ingestion.operative_motion_body import derive_operative_motion_views
        views=derive_operative_motion_views(source['blocks'],source_file=path,source_sha256=source['source_sha256'],source_date=source['local_date'])
        source['operative_views']={f"{b['source_offset']}:{b['source_order']}":v for b,v in zip(source['blocks'],views)}
    if review.get('committee_scope'):
        source.update(reviewed_committee_scope=review['committee_scope'],present=[],header_attendance=None,
                      roster_unknown=['committee_scope_review_does_not_certify_roster'])
    if review['mode']=='reviewed_scan':
        if digest(source['blocks'])!=review['parsed_blocks_sha256'] or sha(source['text'].encode())!=review['source_text_sha256']:
            raise ValueError('Reviewed scan parsing changed')
        accepted={entry['source_key']:entry for entry in review['accepted_decisions']}
        if len(accepted)!=len(review['accepted_decisions']):
            raise ValueError('Duplicate reviewed scan occurrence')
        views={}
        for block in source['blocks']:
            identity=source_identity(meeting['id'],source,block);entry=accepted.get(identity['key'])
            view={'source_sha256':source['source_sha256'],'raw_block':block,'status':'scan_body_not_independently_reviewed_held'}
            if entry:
                if (digest(block)!=entry['raw_block_sha256'] or entry['result']!=block['result']
                        or len(entry['pages'])!=1 or entry['pages'][0] not in range(1,len(review['pages'])+1)):
                    raise ValueError('Reviewed scan decision changed')
                view.update(status='explicit_operative',version='reviewed-original-image-ocr-body-v1',
                            operative_body=entry['operative_body'],match_aliases=[],excluded_spans=[],
                            original_image_review={'review_sha256':digest(review),'pages':entry['pages'],
                                                   'corrections':entry.get('corrections',[]),'authority':'operative_body_and_result_only'})
            views[f"{block['source_offset']}:{block['source_order']}"]=view
        if len(accepted)!=sum(v['status']=='explicit_operative' for v in views.values()):
            raise ValueError('Reviewed scan occurrence not found')
        source.update(operative_views=views,present=[],header_attendance=None,
                      source_date_evidence={'method':'reviewed_original_scan_header','review_sha256':digest(review),
                                            'raw_ocr_header':source['source_header']},
                      roster_unknown=['scan_not_attendance_or_ballot_authority'],
                      source_review_holds=review.get('remaining_holds',[]))
    return source


def load_reviewed_minutes(meeting, *, root, people, cache_dir, project_ref, municipality_id):
    if meeting['id'] not in ENROLLED:
        return None
    try:
        path=STORE/f"{meeting['id']}.json"
        if STORE.is_symlink() or path.is_symlink() or not path.resolve().is_relative_to(STORE.resolve()):
            raise ValueError('Untrusted source review path')
        raw=path.read_bytes()
        if sha(raw)!=ENROLLED[meeting['id']]:
            raise ValueError('Enrolled source review changed')
        return source_from_review(json.loads(raw),meeting=meeting,root=root,people=people,cache_dir=cache_dir,
                                  project_ref=project_ref,municipality_id=municipality_id)
    except (ValueError,OSError,KeyError,RuntimeError,subprocess.SubprocessError) as error:
        return {'error':'reviewed_original_source_held','reason':str(error)}
