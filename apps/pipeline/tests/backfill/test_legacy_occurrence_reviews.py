"""Abbreviated legacy ownership must not certify body/outcome or weaken ingest."""
from copy import deepcopy
import hashlib

import pytest

from ingestion.ballot_fixture import official_context, TEXT, PEOPLE
from pipeline.ingestion.official_ballots import load_official_minutes
from pipeline.ingestion.canonical_motions import canonical_motion_plan, source_identity
from pipeline.ingestion.source_claims import build_claim_inventory, digest, project_claim
from pipeline.backfill import legacy_occurrence_reviews as reviews


@pytest.fixture
def case(tmp_path, monkeypatch):
    context = official_context(tmp_path)
    path = tmp_path/context['source']['source_file']
    html = path.read_text()
    motion = html[html.index('<div class="AgendaItemMotion">'):]
    path.write_text(html[:-6]+motion[:-6].replace('2269','2270')+'</div>')
    source = load_official_minutes(context['meeting'],root=tmp_path,people=PEOPLE,cache_dir=tmp_path/'cache')
    assert len(source['blocks'])==2
    old = {'id':309,'meeting_id':77,'agenda_item_id':99,'text_content':'THAT Council adopt tree bylaw2269 [details omitted].',
           'result':None,'mover_id':None,'seconder_id':None,'meta':{'manual_evidence':'preserve'}}
    inventory = build_claim_inventory([old],meeting_id=77,expected_count=1)
    block = source['blocks'][0]
    review = {'schema':'reviewed-legacy-occurrence-reservations-v1','meeting_id':77,'project_ref':'test-project','municipality_id':1,
              'source_sha256':source['source_sha256'],'source_url':source['source_url'],'source_file':source['source_file'],
              'source_date':source['local_date'],'source_text_sha256':hashlib.sha256(source['text'].encode()).hexdigest(),
              'formal_inventory_sha256':digest(source['formal_occurrence_inventory']),'claim_inventory_sha256':inventory['fingerprint'],
              'native_pages':[],'reservations':[{'motion_id':309,'claim_sha256':digest(project_claim(old)),
                  'legacy_text':old['text_content'],'source_identity':source_identity(77,source,block),
                  'raw_block_sha256':digest(block),'authority':'occurrence_reservation_only'}]}
    monkeypatch.setattr(reviews,'load_review',lambda meeting_id:deepcopy(review))
    context.update(source=source,meeting_claim_inventory=inventory,allow_reviewed_legacy_reservations=True,
                   project_ref='test-project',municipality_id=1,archive_root=tmp_path)
    return context,old,review


def test_catchup_reserves_abbreviation_but_leaves_text_unknown_outcome_and_ballots_untouched(case):
    context,old,review = case
    before = deepcopy(old)
    items,report = canonical_motion_plan([],context,[old])
    additions = [motion for item in items for motion in item['motions']]
    assert [motion['motion_text'] for motion in additions]==[TEXT.replace('2269','2270')]
    assert report['unmapped_legacy_ids']==[]
    assert report['held'][0]['reason']=='reviewed_legacy_occurrence_reserved_no_rewrite'
    assert old==before and old['result'] is None
    # Ordinary ingestion still applies its original complete-body guard.
    context.pop('allow_reviewed_legacy_reservations')
    items,report = canonical_motion_plan([],context,[old])
    assert not [motion for item in items for motion in item['motions']]
    assert report['unmapped_legacy_ids']==[309]


@pytest.mark.parametrize('change', ['claim','source','project','inventory','authority','duplicate','competing'])
def test_changed_or_competing_review_cannot_unlock_additions(case,change):
    context,old,review = case
    if change=='claim':old['result']='CARRIED'
    elif change=='source':context['source']['text']+=' changed'
    elif change=='project':context['project_ref']='other-project'
    elif change=='inventory':review['claim_inventory_sha256']='different'
    elif change=='authority':review['reservations'][0]['authority']='full_transcription'
    elif change=='duplicate':review['reservations'].append(deepcopy(review['reservations'][0]))
    else:
        other = {**old,'id':310,'text_content':TEXT}
        context['meeting_claim_inventory']=build_claim_inventory([old,other],meeting_id=77,expected_count=2)
        review['claim_inventory_sha256']=context['meeting_claim_inventory']['fingerprint']
        items,report=canonical_motion_plan([],context,[old,other])
        assert report['status']=='reviewed_legacy_occurrence_review_stale'
        assert not [motion for item in items for motion in item['motions']]
        return
    if change=='claim':
        context['meeting_claim_inventory']=build_claim_inventory([old],meeting_id=77,expected_count=1)
    items,report=canonical_motion_plan([],context,[old])
    assert report['status']=='reviewed_legacy_occurrence_review_stale'
    assert not [motion for item in items for motion in item['motions']]


def test_enrolled_artifact_tampering_is_rejected(tmp_path, monkeypatch):
    # Exercise the real enrolled-file gate, rather than a mocked validator.
    actual_loader = __import__('pipeline.backfill.legacy_occurrence_reviews',fromlist=['load_review']).load_review
    original = reviews.STORE/'215.json'
    (tmp_path/'215.json').write_bytes(original.read_bytes()+b' ')
    monkeypatch.setattr(reviews,'STORE',tmp_path)
    with pytest.raises(ValueError,match='artifact changed'):
        actual_loader(215)


def test_successful_addition_requires_new_inventory_review_before_future_catchup(case):
    context,old,review=case
    items,report=canonical_motion_plan([],context,[old])
    added=[motion for item in items for motion in item['motions']][0]
    persisted={'id':310,'meeting_id':77,'agenda_item_id':100,'text_content':added['motion_text'],
               'result':added['result'],'meta':{'canonical_source_motion':added['_canonical_source_motion']}}
    context['meeting_claim_inventory']=build_claim_inventory([old,persisted],meeting_id=77,expected_count=2)
    items,report=canonical_motion_plan([],context,[old,persisted])
    assert report['status']=='reviewed_legacy_occurrence_review_stale'
    assert not [motion for item in items for motion in item['motions']]
