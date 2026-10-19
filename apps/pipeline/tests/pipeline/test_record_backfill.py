"""Contracts for source-backed backfill; unidentified or ambiguous evidence stays unknown."""
import pytest


@pytest.mark.parametrize('unsafe_plan,message', [
    ({'meeting_id': 11, 'rows': [], 'votes': [(90, 5, 'No')]}, 'Legacy vote writes are retired'),
    ({'meeting_id': 11, 'rows': [(11, 21, 'Named Person', 0.0, 3.0, 'Speech', 'VOICE_CONSENSUS_BACKFILL')], 'votes': []}, 'Legacy speaker identities are retired'),
])
def test_legacy_identity_or_vote_plan_rejected_before_any_transcript_transaction(unsafe_plan, message):
    """A saved legacy vote plan must never partially apply a mixed batch."""
    from pipeline.backfill.records import apply_plan

    class NoWriteTransaction:
        def __enter__(self):
            raise AssertionError('Legacy apply reached a database write transaction')

        def __exit__(self, *_):
            return False

    cached_transcript = {
        'meeting_id': 10,
        'rows': [(10, None, 'SPEAKER_00', 0.0, 3.0, 'A public statement.', 'CACHED_TRANSCRIPT_BACKFILL')],
        'votes': [],
    }
    with pytest.raises(ValueError, match=message):
        apply_plan(NoWriteTransaction(), [cached_transcript, unsafe_plan])


def test_cached_recovery_keeps_raw_labels_despite_consistent_alias_bank(tmp_path, monkeypatch):
    """Five consistent alias recordings are not independent named identity proof."""
    import json
    from datetime import date
    from pipeline.backfill import records

    vector = [1.0] + [0.0] * 191
    meetings, aliases = [], []
    for mid in range(1, 7):
        folder = tmp_path / 'archive' / 'langford' / f'meeting-{mid}'
        (folder / 'Audio').mkdir(parents=True)
        data = {'speaker_centroids': {'SPEAKER_00': vector}, 'segments': [
            {'speaker': 'SPEAKER_00', 'start': 0.0, 'end': 3.0,
             'text': 'A cached public statement.', 'speaker_confidence': 1.0,
             'competing_speaker_fraction': 0.0},
        ]}
        (folder / 'Audio' / 'transcript.json').write_text(json.dumps(data))
        meetings.append({'id': mid, 'archive_path': str(folder.relative_to(tmp_path)),
                         'meeting_date': date(2025, 1, mid), 'segment_count': int(mid != 6),
                         'video_url': f'https://vimeo.com/{mid}',
                         'meta': {'speaker_centroids': {'SPEAKER_00': vector}}})
        if mid < 6:
            aliases.append({'meeting_id': mid, 'person_id': 21, 'speaker_label': 'SPEAKER_00'})
    members = [{'id': 21, 'name': 'Named Person', 'start_date': date(2022, 1, 1), 'end_date': None}]

    class ReadCursor:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, sql):
            self.rows = aliases if 'meeting_speaker_aliases' in sql else members if 'memberships' in sql else meetings
        def fetchall(self): return self.rows

    class ReadConnection:
        def cursor(self, **_): return ReadCursor()

    monkeypatch.setattr(records, 'ROOT', tmp_path)
    plans, summary = records.plan_backfill(ReadConnection())
    assert len(plans) == 1 and plans[0]['meeting_id'] == 6
    assert plans[0]['rows'] == [(6, None, 'SPEAKER_00', 0.0, 3.0,
                                 'A cached public statement.', 'CACHED_TRANSCRIPT_BACKFILL')]
    assert summary['transcripts'][0]['attributed_segments'] == 0
