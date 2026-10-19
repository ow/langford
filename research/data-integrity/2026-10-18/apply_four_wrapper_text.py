"""Prepare/verify/apply four reviewed source-wrapper text corrections only.

Default verifies the frozen plan read-only. --prepare creates the plan once.
Mutation requires exact caller plan, independent review and script hashes.
No vote/result/actor/agenda/enrichment fields, summaries or transcripts are set.
"""
from pathlib import Path
from datetime import datetime,timezone,date
from collections import defaultdict
from urllib.parse import urlparse
import argparse,hashlib,json,os,tempfile
import psycopg2
from psycopg2.extras import RealDictCursor,Json
from pipeline import config
from pipeline.ingestion.official_ballots import load_official_minutes
from pipeline.ingestion.vote_evidence import normalize_text
from pipeline.ingestion.matter_lifecycle import lifecycle_evidence

ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
IDS=[750,2699,2766,3735]
PLAN=OUT/'four-wrapper-text-only-plan.json'
PRIMARY=OUT/'four-wrapper-source-correction-review.json'
REVIEW=OUT/'four-wrapper-text-only-independent-review.json'
PENDING=OUT/'four-wrapper-text-only-pending-receipt.json'
RECEIPT=OUT/'four-wrapper-text-only-applied-receipt.json'
ROLLBACK_PENDING=OUT/'four-wrapper-text-only-rollback-pending.json'
ROLLBACK_RECEIPT=OUT/'four-wrapper-text-only-rollback-receipt.json'
CODE=['apps/pipeline/pipeline/ingestion/'+f for f in ['official_ballots.py','canonical_motions.py','vote_evidence.py','ballot_reconstruction.py','native_header_ocr.py','native_header_vision.swift','matter_lifecycle.py']]
MC='m.*,m.meta IS NULL AS __meta_is_sql_null'
CATALOG='m.id,m.organization_id,m.municipality_id,m.meeting_date,m.title,m.type,m.archive_path,m.minutes_url,o.name AS organization_name,o.classification,u.slug AS municipality_slug'
serial=lambda v:json.loads(json.dumps(v,default=str))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def require(ok,message):
    if not ok:raise RuntimeError(message)


def durable_save(path,obj,*,exclusive=False):
    """Fsync payload and directory before committing; never replace uncertainty."""
    with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,prefix=path.name+'.',delete=False) as stream:
        temporary=Path(stream.name)
        json.dump(serial(obj),stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    try:
        if exclusive:os.link(temporary,path);temporary.unlink()
        else:temporary.replace(path)
        descriptor=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)
    finally:
        if temporary.exists():temporary.unlink()


def rows(cur,lock):
    cur.execute(f'SELECT {MC} FROM motions m WHERE m.id=ANY(%s) ORDER BY m.id'+(' FOR UPDATE OF m' if lock else ''),(IDS,))
    motions=serial(cur.fetchall())
    cur.execute('SELECT * FROM votes WHERE motion_id=ANY(%s) ORDER BY id'+(' FOR UPDATE' if lock else ''),(IDS,))
    votes=serial(cur.fetchall())
    require([r['id'] for r in motions]==IDS,'exact_four_motion_ids_required')
    return motions,votes


def catalog(cur,meetingids,lock):
    cur.execute(f'SELECT {CATALOG} FROM meetings m JOIN organizations o ON o.id=m.organization_id JOIN municipalities u ON u.id=m.municipality_id WHERE m.id=ANY(%s) ORDER BY m.id'+(' FOR SHARE OF m,o,u' if lock else ''),(meetingids,))
    return serial(cur.fetchall())


def schema(cur):
    cur.execute("SELECT table_name,column_name,data_type,is_generated FROM information_schema.columns WHERE table_schema='public' AND table_name IN ('motions','votes','meetings','organizations','municipalities','agenda_items','matters') ORDER BY table_name,ordinal_position")
    result=serial(cur.fetchall());columns=defaultdict(set)
    for row in result:columns[row['table_name']].add(row['column_name'])
    for table,required in {'motions':{'id','meeting_id','agenda_item_id','text_content','result','meta','updated_at'},'votes':{'id','motion_id','person_id','vote'},'meetings':{'id','organization_id','municipality_id','meeting_date','title','type','archive_path','minutes_url'},'organizations':{'id','name','classification'},'municipalities':{'id','slug'},'agenda_items':{'id','matter_id'},'matters':{'id','status','meta'}}.items():
        require(required<=columns[table],'actual_schema_missing_required_'+table)
    return result


def load_source(change,meeting):
    proof=change['source'];review=change['primary_review']
    require(sha(ROOT/proof['source_file'])==proof['source_sha256'],'original_source_binary_changed')
    source=load_official_minutes(meeting,root=ROOT,people=[],cache_dir=Path('/private/tmp/four-wrapper-text-native'))
    require(not source.get('error'),'original_native_source_unavailable')
    for key in ['source_file','source_url','source_sha256','source_classification','local_date']:
        require(source.get(key)==proof[key],'reviewed_native_'+key+'_changed')
    url=urlparse(source['source_url'])
    require(url.scheme=='https' and url.hostname in {'langford.ca','www.langford.ca','pub-langford.escribemeetings.com'},'official_source_url_scope_not_proven')
    require(source['source_classification']==meeting['classification']=='Council' and meeting['municipality_slug']=='langford','native_catalog_council_scope_not_bound')
    require(source['local_date'] and abs((date.fromisoformat(source['local_date'])-date.fromisoformat(meeting['meeting_date'][:10])).days)<=1,'native_date_not_bound_to_catalog')
    blocks=source['index'].get(normalize_text(review['official_motion_text']),[])
    require(len(blocks)==1,'official_entire_body_not_unique')
    block=blocks[0]
    witness=block['source_block'].split(block['outcome_quote'],1)[0]+block['outcome_quote']
    require(normalize_text(witness)==normalize_text(review['whole_formal_witness']),'whole_formal_actors_body_result_changed')
    require(block['motion_text']==review['official_motion_text'],'literal_official_body_changed')
    require(block['result']==review['official_result']==change['before_motion']['result'],'outcome_change_not_authorized')
    return source,block


def unchanged_other_fields(before,after,*,rolling_back=False):
    # text_search is verified live-generated, recomputed by PostgreSQL from text.
    allowed={'text_content','meta','updated_at','text_search','__meta_is_sql_null'}
    require({k:v for k,v in before.items() if k not in allowed}=={k:v for k,v in after.items() if k not in allowed},'unrelated_motion_field_changed')
    if rolling_back:
        require(after['text_content']==before['text_content'] and after['meta']==before['meta'] and after['__meta_is_sql_null']==before['__meta_is_sql_null'] and after['text_search']==before['text_search'],'rollback_before_content_not_restored')


def prepare(cur):
    require(not any(p.exists() for p in [PLAN,PENDING,RECEIPT]),'preserve_existing_frozen_plan_or_receipts')
    actual_schema=schema(cur)
    require([r['column_name'] for r in actual_schema if r['table_name']=='motions' and r['is_generated']=='ALWAYS']==['text_search'],'unexpected_motion_generated_fields')
    primary_bytes=PRIMARY.read_bytes();primary=json.loads(primary_bytes)
    require(sorted(r['motion_id'] for r in primary['reviews'])==IDS,'exact_four_primary_reviews_required')
    before,votes=rows(cur,False);byid={r['id']:r for r in before}
    meetings=catalog(cur,sorted({r['meeting_id'] for r in before}),False);meetingmap={m['id']:m for m in meetings}
    changes=[]
    for review in sorted(primary['reviews'],key=lambda r:r['motion_id']):
        old=byid[review['motion_id']];meeting=meetingmap[old['meeting_id']]
        require(old['meeting_id']==review['meeting_id'] and old['agenda_item_id']==review['agenda_item_id'],'old_source_identity_changed')
        require(old['text_content']==review['original_motion_text'] and old['result']==review['stored_result'],'old_text_or_result_changed_since_primary_review')
        require((old['meta'] or {}).get('individual_vote_coverage')!='reconstructed_complete','complete_ballot_body_requires_separate_proof_review')
        require('source_wrapper_correction' not in (old['meta'] or {}),'wrapper_correction_already_present')
        source=load_official_minutes(meeting,root=ROOT,people=[],cache_dir=Path('/private/tmp/four-wrapper-text-native'))
        proof={key:source.get(key) for key in ['source_file','source_url','source_sha256','source_classification','local_date']}
        require(proof['source_file']==review['source_file'] and proof['source_url']==review['source_url'] and proof['source_sha256']==review['source_sha256'],'primary_original_source_changed')
        change={'motion_id':old['id'],'before_motion':old,'before_votes':[v for v in votes if v['motion_id']==old['id']], 'meeting':meeting,'primary_review':review,'source':proof}
        source,block=load_source(change,meeting)
        provenance={'correction_kind':'official_council_wrapper_and_leading_list_ordinal_restoration','original_motion_text':old['text_content'],'official_motion_text':block['motion_text'],'original_result':old['result'],
            'source_file':source['source_file'],'source_url':source['source_url'],'source_sha256':source['source_sha256'],'source_date':source['local_date'],'source_date_evidence':source.get('source_date_evidence'),
            'source_classification':source['source_classification'],'source_block':block['source_block'],'primary_review_file':PRIMARY.name,'primary_review_sha256':hashlib.sha256(primary_bytes).hexdigest(),
            'agenda_item_id_preserved':old['agenda_item_id'],'ballot_eligibility_claim':False,'canonical_source_key_published':False}
        change.update({'after_text':block['motion_text'],'after_meta':{**(old['meta'] or {}),'source_wrapper_correction':provenance}})
        require({k:v for k,v in change['after_meta'].items() if k!='source_wrapper_correction'}==(old['meta'] or {}),'unrelated_metadata_change')
        changes.append(change)
    cur.execute('SELECT DISTINCT a.matter_id FROM agenda_items a JOIN motions m ON m.agenda_item_id=a.id WHERE m.id=ANY(%s) AND a.matter_id IS NOT NULL',(IDS,));matterids=[r['matter_id'] for r in cur.fetchall()]
    cur.execute('SELECT * FROM matters WHERE id=ANY(%s) ORDER BY id',(matterids,));matters=serial(cur.fetchall())
    for matter in matters:
        mid=(matter['meta'] or {}).get('lifecycle_evidence',{}).get('motion_id')
        if mid in IDS:
            change=next(c for c in changes if c['motion_id']==mid)
            before_evidence=lifecycle_evidence(matter,change['before_motion']);after_evidence=lifecycle_evidence(matter,{**change['before_motion'],'text_content':change['after_text']})
            require(bool(before_evidence)==bool(after_evidence) and (not before_evidence or before_evidence['status']==after_evidence['status']),'source_wrapper_changes_matter_lifecycle_requires_separate_review')
    plan={'mode':'read_only_prepared','at':datetime.now(timezone.utc).isoformat(),'apply_script_sha256':sha(Path(__file__)),
        'primary_review_sha256':hashlib.sha256(primary_bytes).hexdigest(),'code_sha256':{f:sha(ROOT/f) for f in CODE},'actual_schema':actual_schema,
        'meetings':meetings,'affected_matters':matters,'changes':changes,
        'summary':{'motion_text_corrections':4,'vote_rows_preserved':len(votes),'vote_mutations':0,'results_changed':0,'actor_changes':0,'agenda_relinks':0,'enrichment_changes':0,'canonical_source_keys_published':0,'new_ballot_claims':0}}
    durable_save(PLAN,plan,exclusive=True);print(json.dumps(plan['summary']))


def main():
    cli=argparse.ArgumentParser(description=__doc__);mode=cli.add_mutually_exclusive_group()
    for option in ['prepare','apply','rollback']:mode.add_argument('--'+option,action='store_true')
    for item in ['plan','review','script','receipt']:cli.add_argument('--expected-'+item+'-sha256')
    args=cli.parse_args();script_hash=sha(Path(__file__))
    mutation=args.apply or args.rollback
    if args.rollback:
        receipt_bytes=RECEIPT.read_bytes();receipt=json.loads(receipt_bytes)
        require(args.expected_receipt_sha256==hashlib.sha256(receipt_bytes).hexdigest() and args.expected_script_sha256==script_hash,'exact_receipt_and_script_hash_required')
        require(receipt['mode']=='applied' and receipt['apply_script_sha256']==script_hash and not ROLLBACK_PENDING.exists() and not ROLLBACK_RECEIPT.exists(),'rollback_receipt_or_script_not_current')
        plan=receipt
    elif not args.prepare:
        plan_bytes=PLAN.read_bytes();plan_hash=hashlib.sha256(plan_bytes).hexdigest();plan=json.loads(plan_bytes)
        require(plan['apply_script_sha256']==script_hash,'plan_applier_changed')
        require(sha(PRIMARY)==plan['primary_review_sha256'],'primary_source_review_changed')
        require(sorted(c['motion_id'] for c in plan['changes'])==IDS and len(plan['changes'])==4,'exact_four_scope_required')
        for filename,digest in plan['code_sha256'].items():require(sha(ROOT/filename)==digest,'production_source_guards_changed')
        if args.apply:
            review_bytes=REVIEW.read_bytes();review=json.loads(review_bytes);review_hash=hashlib.sha256(review_bytes).hexdigest()
            require((args.expected_plan_sha256,args.expected_review_sha256,args.expected_script_sha256)==(plan_hash,review_hash,script_hash),'caller_exact_plan_review_script_hashes_required')
            require(review.get('verdict')=='PASS' and review.get('candidate_plan_sha256')==plan_hash and review.get('apply_script_sha256')==script_hash and sorted(review.get('reviewed_candidate_ids',[]))==IDS,'independent_exact_four_review_required')
            require(not PENDING.exists() and not RECEIPT.exists(),'existing_or_uncertain_commit_receipt_requires_readback')
    db=psycopg2.connect(config.DATABASE_URL,connect_timeout=15)
    db.set_session(isolation_level='SERIALIZABLE',readonly=not mutation)
    try:
        with db.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SET LOCAL statement_timeout='45s'");cur.execute("SET LOCAL lock_timeout='8s'")
            if args.prepare:prepare(cur);db.rollback();return
            require(schema(cur)==plan['actual_schema'],'actual_schema_changed')
            current,votes=rows(cur,mutation)
            expected='after_motion' if args.rollback else 'before_motion'
            require(current==[c[expected] for c in plan['changes']],'full_motion_row_CAS_changed')
            require(votes==sorted([v for c in plan['changes'] for v in c['before_votes']],key=lambda r:r['id']),'full_vote_rows_CAS_changed')
            if args.rollback:
                changes=[]
                for change in plan['changes']:
                    old=change['before_motion']
                    cur.execute(f'UPDATE motions m SET text_content=%s,meta=%s WHERE m.id=%s RETURNING {MC}',(old['text_content'],None if old['__meta_is_sql_null'] else Json(old['meta']),old['id']))
                    restored=serial(cur.fetchone());unchanged_other_fields(old,restored,rolling_back=True)
                    changes.append({'motion_id':old['id'],'before_rollback':change['after_motion'],'after_rollback':restored,'before_votes':change['before_votes']})
                rollback={'mode':'pending_rollback_commit','receipt_sha256':hashlib.sha256(receipt_bytes).hexdigest(),'at':datetime.now(timezone.utc).isoformat(),'apply_script_sha256':script_hash,'changes':changes}
                durable_save(ROLLBACK_PENDING,rollback,exclusive=True);db.commit();rollback['mode']='rolled_back';durable_save(ROLLBACK_RECEIPT,rollback,exclusive=True)
                print('Guarded four-motion text-only rollback committed');return
            live_meetings=catalog(cur,sorted(m['id'] for m in plan['meetings']),mutation)
            require(live_meetings==plan['meetings'],'catalog_source_identity_changed')
            for change in plan['changes']:load_source(change,change['meeting'])
            matterids=[m['id'] for m in plan['affected_matters']]
            cur.execute('SELECT * FROM matters WHERE id=ANY(%s) ORDER BY id'+(' FOR SHARE' if mutation else ''),(matterids,))
            require(serial(cur.fetchall())==plan['affected_matters'],'affected_matter_changed_since_review')
            changes=[]
            for change in plan['changes']:
                after=change['before_motion']
                if args.apply:
                    cur.execute(f'UPDATE motions m SET text_content=%s,meta=%s WHERE m.id=%s RETURNING {MC}',(change['after_text'],Json(change['after_meta']),change['motion_id']))
                    after=serial(cur.fetchone());unchanged_other_fields(change['before_motion'],after)
                    require(after['text_content']==change['after_text'] and after['meta']==change['after_meta'],'published_text_or_provenance_differs')
                changes.append({**change,'after_motion':after})
            _,after_votes=rows(cur,False)
            require(after_votes==votes,'vote_rows_changed_during_text_only_operation')
            result={**plan,'mode':'pending_commit' if args.apply else 'verified_read_only','plan_sha256':plan_hash,'apply_script_sha256':script_hash,'at':datetime.now(timezone.utc).isoformat(),'changes':changes}
            if args.apply:
                result['review_sha256']=review_hash;durable_save(PENDING,result,exclusive=True);db.commit();result['mode']='applied';durable_save(RECEIPT,result,exclusive=True)
            else:durable_save(OUT/'four-wrapper-text-only-preflight.json',result);db.rollback()
            print(json.dumps(result['summary']))
    except BaseException:db.rollback();raise
    finally:db.close()


if __name__=='__main__':main()
