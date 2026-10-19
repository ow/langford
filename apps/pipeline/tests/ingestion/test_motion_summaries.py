from pipeline.ingestion.motion_summaries import MotionSummaries, _clean


def test_clean_strips_quotes_and_drops_empty_summaries():
    result = MotionSummaries.model_validate(
        {"motions": [{"id": 1, "summary": "Approved the agenda."}, {"id": 2, "summary": ' "Adjourned." '}, {"id": 3, "summary": ""}]}
    )
    assert _clean(result) == {1: "Approved the agenda.", 2: "Adjourned."}
