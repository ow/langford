"""Receipt reuse follows complete semantic claims, including intended writes."""
from copy import deepcopy

from ingestion.ballot_fixture import official_context
from pipeline.ingestion.canonical_motions import source_validation_inputs, source_receipt_current
from pipeline.ingestion.source_claims import build_claim_inventory, intended_claim_transition


def test_incomplete_claim_inventory_cannot_be_a_reusable_complete_receipt(tmp_path):
    context = official_context(tmp_path)
    context['meeting_claim_inventory'] = build_claim_inventory([], meeting_id=context['meeting']['id'], expected_count=1)
    inputs = source_validation_inputs(context, [])
    receipt = {'motion_source_ingestion': {'status': 'source_authoritative',
                'source_file': context['source']['source_file'], 'source_sha256': context['source']['source_sha256'],
                'validation_inputs': inputs}}
    assert not source_receipt_current(tmp_path, receipt, inputs)


def test_context_reads_every_page_twice_and_rejects_same_count_concurrent_claim_change():
    from types import SimpleNamespace
    from pipeline.ingestion.source_claims import load_claim_inventory
    rows = [{'id': number, 'meeting_id': 77, 'text_content': f'Formal resolution {number}',
             'result': 'CARRIED', 'meta': {}} for number in range(1001)]

    class MotionTable:
        def __init__(self, concurrent_change=False):
            self.calls = 0
            self.concurrent_change = concurrent_change

        def table(self, name):
            assert name == 'motions'
            return self

        def select(self, *args, **kwargs):
            return self

        def eq(self, *args):
            return self

        def order(self, *args):
            return self

        def range(self, start, stop):
            self.bounds = (start, stop)
            return self

        def execute(self):
            self.calls += 1
            data = deepcopy(rows)
            if self.concurrent_change and self.calls > 2:
                data[0]['text_content'] = 'Concurrent competing source claim'
            start, stop = self.bounds
            return SimpleNamespace(data=data[start:stop+1], count=len(data))

    stable = load_claim_inventory(MotionTable(), 77)
    assert stable['status'] == 'complete'
    assert len(stable['claims']) == 1001
    assert load_claim_inventory(MotionTable(concurrent_change=True), 77)['status'] == 'meeting_claim_inventory_incomplete'


def test_receipt_transition_accepts_only_the_intended_persisted_claim_payload():
    import pytest
    from pipeline.ingestion.source_claims import record_intended_claim_write
    row = {'id': 41, 'meeting_id': 77, 'text_content': 'Original complete resolution',
           'result': 'CARRIED', 'meta': {}}
    before = build_claim_inventory([row], meeting_id=77, expected_count=1)
    payload = {'id': 41, 'meta': {'canonical_source_motion': {'key': 'proved-key'}}}
    persisted = {**row, **payload}
    writes = []
    record_intended_claim_write(before, writes, payload, [persisted])
    assert intended_claim_transition(before, build_claim_inventory([persisted], meeting_id=77, expected_count=1), writes)
    unexpected = {**persisted, 'text_content': 'Trigger or concurrent replacement'}
    with pytest.raises(RuntimeError, match='differs from intended write'):
        record_intended_claim_write(before, [], payload, [unexpected])
    assert not intended_claim_transition(before, build_claim_inventory([unexpected], meeting_id=77, expected_count=1), writes)


def test_repeated_transport_page_cannot_loop_or_claim_completeness():
    from types import SimpleNamespace
    from pipeline.ingestion.source_claims import load_claim_inventory
    rows = [{'id': number, 'meeting_id': 77, 'text_content': 'Formal motion', 'meta': {}}
            for number in range(1000)]

    class RepeatingTransport:
        def table(self, *args): return self
        def select(self, *args, **kwargs): return self
        def eq(self, *args): return self
        def order(self, *args): return self
        def range(self, *args): return self
        def execute(self): return SimpleNamespace(data=rows, count=1001)

    assert load_claim_inventory(RepeatingTransport(), 77)['status'] == 'meeting_claim_inventory_incomplete'
