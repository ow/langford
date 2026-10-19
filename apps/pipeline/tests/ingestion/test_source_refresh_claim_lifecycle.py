"""Actual source-refresh orchestration with an independent in-memory transport."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from ingestion.ballot_fixture import official_context, PEOPLE, TEXT
from pipeline.ingestion.ingester import MeetingIngester
from pipeline.ingestion.source_claims import load_claim_inventory
from pipeline.ingestion.canonical_motions import source_receipt_current, source_validation_inputs, source_candidate_inventory

# Transport fixture stores and filters rows; it implements no receipt or cache logic.
class Database:

    def __init__(self, meeting):
        self.rows = {'meetings': [deepcopy(meeting)], 'agenda_items': [{'id': 51, 'meeting_id': 77, 'item_order': 'official-recorded-motions', 'title': 'Official recorded motions', 'meta': {}, 'updated_at': '0'}], 'motions': [{'id': 41, 'meeting_id': 77, 'agenda_item_id': 51, 'text_content': TEXT, 'result': 'CARRIED', 'mover_id': 21, 'seconder_id': 23, 'meta': {}, 'updated_at': '0'}], 'votes': []}
        self.writes = []
        self.revision = 0

    def table(self, name):
        return Query(self, name)

class Query:

    def __init__(self, db, name):
        self.db = db
        self.name = name
        self.filters = []
        self.payload = None
        self.mode = 'select'
        self.bounds = None
        self.one = False

    def select(self, *args, **kwargs):
        return self

    def eq(self, k, v):
        self.filters.append(lambda row, k=k, v=v: row.get(k) == v)
        return self

    def in_(self, k, v):
        self.filters.append(lambda row, k=k, v=v: row.get(k) in v)
        return self

    def order(self, *a, **kw):
        return self

    def range(self, a, b):
        self.bounds = (a, b)
        return self

    def single(self):
        self.one = True
        return self

    def update(self, payload):
        self.payload = deepcopy(payload)
        self.mode = 'update'
        return self

    def insert(self, payload):
        self.payload = deepcopy(payload)
        self.mode = 'insert'
        return self

    def execute(self):
        rows = [row for row in self.db.rows[self.name] if all((f(row) for f in self.filters))]
        if self.mode == 'update':
            for row in rows:
                self.db.revision += 1
                row.update(deepcopy(self.payload))
                row['updated_at'] = str(self.db.revision)
            self.db.writes.append((self.name, self.mode, deepcopy(self.payload)))
        elif self.mode == 'insert':
            row = deepcopy(self.payload)
            row['id'] = max([r['id'] for r in self.db.rows[self.name]] or [0]) + 1
            self.db.rows[self.name].append(row)
            rows = [row]
            self.db.writes.append((self.name, self.mode, deepcopy(self.payload)))
        count = len(rows)
        if self.bounds:
            rows = rows[self.bounds[0]:self.bounds[1] + 1]
        return SimpleNamespace(data=deepcopy(rows[0] if self.one else rows), count=count)

@pytest.mark.parametrize('unrelated_drift', ['none', 'text', 'pending'])
def test_actual_source_refresh_finishes_intended_claims_and_reuses_receipt(tmp_path, monkeypatch, unrelated_drift):
    import pipeline.ingestion.ingester as owner
    import pipeline.ingestion.matter_lifecycle as lifecycle
    context = official_context(tmp_path)
    destination = tmp_path / 'archive/langford/meeting'
    destination.parent.mkdir(parents=True)
    (tmp_path / 'archive/meeting').rename(destination)
    context['meeting'].update(archive_path='archive/langford/meeting', title='Council Meeting', type='Regular', organization_id=10)
    from pipeline.ingestion.official_ballots import load_official_minutes
    context['source'] = load_official_minutes(context['meeting'], root=tmp_path, people=PEOPLE, cache_dir=tmp_path / 'cache')
    db = Database({**context['meeting'], 'municipality_id': 2, 'has_agenda': True, 'has_minutes': True, 'has_transcript': False, 'status': 'Completed', 'organization': {'classification': 'Council'}, 'meta': {}, 'updated_at': '0'})
    db.rows['motions'].append({'id': 42, 'meeting_id': 77, 'agenda_item_id': 51, 'text_content': 'An unrelated unresolved legacy claim', 'result': 'CARRIED', 'meta': {}, 'updated_at': '0'})
    ingester = MeetingIngester.__new__(MeetingIngester)
    ingester.supabase = db
    ingester.municipality_id = 2
    monkeypatch.setattr(owner, 'BASE_DIR', tmp_path)
    context_reads = []

    # The actual orchestrator requests initial and final authoritative contexts.
    # Inject drift only at its final read, after its own intended writes.
    def load_context(client, *, municipality_id, meeting, root):
        context_reads.append(1)
        if unrelated_drift != 'none' and len(context_reads) == 2:
            db.rows['motions'][1]['meta']['pending_ballot_proof'] = {'source_motion_identity': {'key': 'concurrent-competing-source-claim'}}
            if unrelated_drift == 'text':
                db.rows['motions'][1]['text_content'] = 'Unexpected concurrent legacy replacement'
        return {**deepcopy(context), 'meeting': {**meeting, 'municipality_slug': 'langford'}, 'meeting_claim_inventory': load_claim_inventory(client, meeting['id'])}
    monkeypatch.setattr(owner, 'prepare_ballot_context', load_context)
    for name in ('persist_participant_role_observations', '_ingest_documents', '_ingest_document_sections', 'reconcile_transcript_identities'):
        monkeypatch.setattr(ingester, name, lambda *a, **kw: None)
    monkeypatch.setattr(ingester, 'get_raw_texts', lambda *a, **kw: ('# Agenda\n' + 'Agenda text. ' * 20, '# Minutes\n' + 'Minutes text. ' * 20, ''))
    monkeypatch.setattr(ingester, '_read_archived_player_url', lambda *a: None)
    monkeypatch.setattr(ingester, '_should_search_vimeo', lambda: False)
    monkeypatch.setattr(ingester, 'find_transcript', lambda *a: None)
    monkeypatch.setattr(ingester, '_get_canonical_names', lambda: [p['name'] for p in PEOPLE])
    monkeypatch.setattr(ingester, 'get_or_create_person', lambda name, *a: next((p['id'] for p in PEOPLE if p['name'] == name)))
    monkeypatch.setattr(lifecycle, 'refresh_meeting_matter_lifecycles', lambda *a: None)
    monkeypatch.setattr(owner, 'refine_meeting_data', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('No model path permitted')))
    if unrelated_drift != 'none':
        with pytest.raises(RuntimeError, match='Unexpected semantic claim change'):
            ingester.process_meeting(str(destination))
        assert db.rows['meetings'][0]['meta']['motion_source_ingestion']['status'] == 'in_progress'
        return
    result = ingester.process_meeting(str(destination))
    assert result['source_only_refresh'] is True
    assert len(db.rows['votes']) == 6
    receipt = db.rows['meetings'][0]['meta']['motion_source_ingestion']
    assert receipt['status'] == 'source_authoritative'
    final_context = load_context(db, municipality_id=2, meeting=context['meeting'], root=tmp_path)
    final_inputs = source_validation_inputs(final_context, source_candidate_inventory(tmp_path, 'archive/langford/meeting'))
    assert source_receipt_current(tmp_path, db.rows['meetings'][0]['meta'], final_inputs)
    writes = len(db.writes)
    assert ingester.process_meeting(str(destination)) is None
    assert len(db.writes) == writes
