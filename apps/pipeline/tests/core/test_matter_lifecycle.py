"""Protect explicit final actions versus interim motions on the same matter."""
import pytest
from pipeline.ingestion.matter_lifecycle import plan_lifecycle_updates


@pytest.mark.parametrize("text,result,expected", [
    ("THAT Council adopt Bylaw No. 2275.", "CARRIED", "Adopted"),
    ("THAT Council adopt Bylaw No. 2275.", "DEFEATED", None),
    ("THAT Council give third reading to Bylaw No. 2275.", "CARRIED", None),
    ("THAT Committee recommend that Council adopt Bylaw No. 2275.", "CARRIED", None),
    ("THAT Council adopt Bylaw No. 2275 subject to provincial approval.", "CARRIED", None),
    ("THAT Council direct staff to prepare Bylaw No. 2275 for adoption.", "CARRIED", None),
    ("THAT Council adopt Bylaw No. 2270.", "CARRIED", None),
    ("THAT Council adopt the report regarding Bylaw No. 2275.", "CARRIED", None),
    ("THAT Council adopt a plan under Bylaw No. 2275.", "CARRIED", None),
    ("THAT Council adopt the policy and direct staff to prepare Bylaw No. 2275.", "CARRIED", None),
    ("THAT Council adopt Bylaw No. 2222 and direct staff to prepare Bylaw No. 2275.", "CARRIED", None),
])
def test_only_completed_final_action_changes_matter(text, result, expected):
    updates = plan_lifecycle_updates(
        [{"id": 1, "title": "Amenity Cost Charge", "identifier": "Bylaw 2275", "status": "Active"}],
        [{"id": 2, "matter_id": 1}],
        [{"id": 3, "agenda_item_id": 2, "meeting_id": 4, "result": result, "text_content": text}],
        [{"id": 4, "meeting_date": "2026-06-29"}],
    )
    assert [u["status"] for u in updates] == ([expected] if expected else [])


def test_old_reingestion_does_not_overwrite_later_repeal():
    updates = plan_lifecycle_updates(
        [{"id": 1, "title": "Bylaw", "identifier": "Bylaw 2275", "status": "Active"}],
        [{"id": 2, "matter_id": 1}],
        [{"id": 3, "agenda_item_id": 2, "meeting_id": 4, "result": "CARRIED", "text_content": "THAT Council repeal Bylaw No. 2275."},
         {"id": 5, "agenda_item_id": 2, "meeting_id": 6, "result": "CARRIED", "text_content": "THAT Council adopt Bylaw No. 2275."}],
        [{"id": 4, "meeting_date": "2026-06-29"}, {"id": 6, "meeting_date": "2025-01-01"}],
    )
    assert updates[0]["status"] == "Repealed"
    assert updates[0]["meta"]["lifecycle_evidence"]["motion_id"] == 3
