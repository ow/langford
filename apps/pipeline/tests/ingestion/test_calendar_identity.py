from types import SimpleNamespace
import pytest
from pipeline.ingestion.calendar_identity import find_scheduled_meeting


class Records:
    def __init__(self, rows): self.rows = rows
    def select(self, _): return self
    def eq(self, key, value): self.rows = [r for r in self.rows if r.get(key) == value]; return self
    def is_(self, key, _): self.rows = [r for r in self.rows if r.get(key) is None]; return self
    def execute(self): return SimpleNamespace(data=self.rows)


class Database:
    def __init__(self, sources, meetings): self.tables = {'source_meetings':sources,'meetings':meetings}
    def table(self, name): return Records(self.tables[name].copy())


def test_published_archive_uses_explicit_source_identity_even_if_date_or_type_changed():
    db = Database([dict(municipality_id=1,archive_path='archive/published',ingested_meeting_id=7)],
                  [dict(id=7,municipality_id=1,calendar_source_id=4,organization_id=1,meta={'calendar':{'start_time':None}})])
    row = find_scheduled_meeting(db,1,'archive/published','2026-11-03','Special Council')
    assert row['id'] == 7
    assert row['meta']['calendar']['start_time'] is None


def test_unmapped_calendar_is_not_guessed_from_date_and_other_municipalities_are_excluded():
    db=Database([], [dict(id=7,municipality_id=1,meeting_date='2026-11-02',type='Inauguration',archive_path=None,calendar_source_id=4),
                    dict(id=8,municipality_id=2,meeting_date='2026-11-02',type='Inauguration',archive_path=None,calendar_source_id=None)])
    assert find_scheduled_meeting(db,1,'archive/new','2026-11-02','Inauguration') is None


def test_ambiguous_legacy_placeholders_are_not_arbitrarily_merged():
    db=Database([], [dict(id=i,municipality_id=1,meeting_date='2026-11-02',type='Special Council',archive_path=None,calendar_source_id=None) for i in [7,8]])
    with pytest.raises(RuntimeError,match='Ambiguous legacy'):
        find_scheduled_meeting(db,1,'archive/new','2026-11-02','Special Council')
