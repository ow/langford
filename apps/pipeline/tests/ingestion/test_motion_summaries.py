from pipeline.ingestion.motion_summaries import _parse


def test_parse_extracts_json_array_from_model_text():
    text = 'Here you go:\n[{"id": 1, "summary": "Approved the agenda."}, {"id": "2", "summary": " \\"Adjourned.\\" "}, {"id": 3, "summary": ""}]'
    assert _parse(text) == {1: "Approved the agenda.", 2: "Adjourned."}
