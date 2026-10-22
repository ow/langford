"""Run with HISTORY_TEST_DATABASE_URL pointing only at a disposable PostgreSQL DB."""
import os
from copy import deepcopy

import psycopg2
import pytest

from ingestion.ballot_fixture import official_context, PEOPLE
from pipeline.backfill.history_coverage import (apply_manifest, verify_manifest, plan_meeting,
                                               read_meeting, query, digest)


@pytest.fixture
def database():
    url = os.environ.get('HISTORY_TEST_DATABASE_URL')
    if not url:
        pytest.skip('disposable PostgreSQL not configured')
    connection = psycopg2.connect(url)
    # All DDL is transactional and rolled back, including on a test failure.
    query(connection, 'CREATE SCHEMA history_coverage_test')
    query(connection, 'SET LOCAL search_path=history_coverage_test')
    query(connection, 'CREATE TABLE organizations(id int primary key,classification text)')
    query(connection, 'CREATE TABLE people(id int primary key,name text)')
    query(connection, '''CREATE TABLE meetings(id int primary key,title text,type text,meeting_date date,
        archive_path text,minutes_url text,meta jsonb,updated_at timestamptz,organization_id int,municipality_id int)''')
    query(connection, '''CREATE TABLE agenda_items(id serial primary key,meeting_id int REFERENCES meetings(id),
        item_order text,title text,category text,slug text)''')
    query(connection, '''CREATE TABLE motions(id serial primary key,meeting_id int REFERENCES meetings(id),
        agenda_item_id int REFERENCES agenda_items(id),text_content text,result text,mover text,seconder text,
        mover_id int,seconder_id int,meta jsonb)''')
    query(connection, "INSERT INTO organizations VALUES(1,'Council')")
    for person in PEOPLE:
        query(connection, 'INSERT INTO people VALUES(%s,%s)', (person['id'], person['name']))
    for mid in (77,78):
        query(connection, "INSERT INTO meetings(id,title,meeting_date,archive_path,organization_id,municipality_id) VALUES(%s,'Council','2026-01-08','archive/meeting',1,1)", (mid,))
    yield connection
    connection.rollback()
    connection.close()


def manifest_for(database, tmp_path):
    context = official_context(tmp_path)
    meeting, motions, items = read_meeting(database,77,1)
    plan = plan_meeting(meeting,motions,items,context['source'])
    meeting, motions, items = read_meeting(database,78,1)
    held = plan_meeting(meeting,motions,items,{'error':'pdf_requires_ocr'})
    return {'version':1,'municipality_id':1,'people_sha256':digest(query(database,'SELECT id,name FROM people ORDER BY id')),
            'meetings':[plan,held]}


def test_mixed_batch_receipts_retry_and_parent_actor_drift(database,tmp_path):
    manifest = manifest_for(database,tmp_path)
    result = apply_manifest(database,manifest,lambda:deepcopy(manifest),tmp_path)
    assert result['status']=='applied'
    assert [p['coverage'] for p in result['meetings']]==['source_occurrences_accounted_for','source_unavailable']
    assert len(query(database,'SELECT * FROM motions'))==1
    assert verify_manifest(database,manifest)['inserted_motions']==1
    # Retry acknowledges its receipt without repeating parsing or insertion.
    def must_not_parse():
        raise AssertionError('already committed receipt must be checked first')
    assert apply_manifest(database,manifest,must_not_parse,tmp_path)['status']=='already_applied'
    for change in ('mover_id=123','agenda_item_id=NULL'):
        query(database,'SAVEPOINT drift')
        query(database,'UPDATE motions SET '+change)
        with pytest.raises(ValueError,match='claims changed'):
            verify_manifest(database,manifest)
        query(database,'ROLLBACK TO SAVEPOINT drift')


def test_concurrent_claim_or_source_change_rejects_before_inserts(database,tmp_path):
    manifest = manifest_for(database,tmp_path)
    query(database,"UPDATE meetings SET title='Corrected title' WHERE id=77")
    with pytest.raises(ValueError,match='database claims changed'):
        apply_manifest(database,manifest,lambda:deepcopy(manifest),tmp_path)
    assert query(database,'SELECT * FROM motions')==[]


def test_changed_original_and_late_failure_leave_no_partial_batch(database,tmp_path):
    manifest = manifest_for(database,tmp_path)
    source = tmp_path/manifest['meetings'][0]['source_file']
    original = source.read_bytes()
    source.write_bytes(original+b'changed')
    with pytest.raises(ValueError,match='Original source changed'):
        apply_manifest(database,manifest,lambda:deepcopy(manifest),tmp_path)
    assert query(database,'SELECT * FROM motions')==[]
    source.write_bytes(original)
    query(database,'SAVEPOINT apply_batch')
    # A database constraint failure after the first insertion must rollback it.
    query(database,"ALTER TABLE meetings ADD CONSTRAINT receipt_rejected CHECK (id<>78 OR meta IS NULL)")
    with pytest.raises(psycopg2.IntegrityError):
        apply_manifest(database,manifest,lambda:deepcopy(manifest),tmp_path)
    query(database,'ROLLBACK TO SAVEPOINT apply_batch')
    assert query(database,'SELECT * FROM motions')==[]
    assert verify_manifest(database,manifest) is None
