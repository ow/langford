import json

from pipeline.speaker_research import (
    attach_reviewed_local_turns,
    build_turn_rows,
    minute_excerpt,
    name_aliases,
    name_pattern,
)
from pipeline.speaker_review_pack import review_segment
from pipeline.speaker_attribution_audit import probable_self_id


def test_name_aliases_include_initial_without_matching_another_first_name():
    aliases = name_aliases("Jane Doe", [])
    pattern = name_pattern(aliases)

    assert aliases == ["Jane Doe", "J. Doe"]
    assert pattern.search("J. Doe, Langford Resident - spoke to item 5.1")
    assert not pattern.search("C. Roe, Langford Resident - spoke to item 5.1")


def test_minute_excerpt_stops_before_next_speaker_and_address():
    pattern = name_pattern(name_aliases("Jane Doe", []))
    text = (
        "J. Doe, Players Dr - Expressed concern about taxes and the budget. "
        "B.Armstrong, 2813 Rodney Rd - Supported the motion."
    )

    assert minute_excerpt(text, pattern) == "Expressed concern about taxes and the budget."


def test_turn_export_keeps_provisional_sources_distinct_without_double_counting():
    shared = {
        "date": "2026-01-01",
        "meeting_type": "Council",
        "minutes_url": "https://example.org/minutes",
        "video_url": "https://example.org/video",
        "audio_path": "/archive/audio.m4a",
        "review_topics": ["budget"],
        "review_evidence": "Self-identification in transcript",
    }
    rows = [
        {
            **shared,
            "meeting_id": 1,
            "turns": [{"id": 42, "speaker": "J. Doe", "start": 10, "end": 20, "text": "Budget remarks"}],
            "local_reviewed_turns": [{"speaker": "Speaker_2", "start": 10, "end": 20, "speech_seconds": 10, "text": "Duplicate"}],
        },
        {
            **shared,
            "meeting_id": 2,
            "turns": [],
            "local_reviewed_turns": [{"speaker": "Speaker_3", "start": 30, "end": 42, "speech_seconds": 9, "text": "Another topic"}],
        },
    ]

    turns = build_turn_rows(rows, "Jane Doe", "https://example.org",)

    assert len(turns) == 2
    assert turns[0]["transcript_url"] == "https://example.org/meetings/1#transcript=42"
    assert turns[0]["source_kind"] == "archive_transcript_name_match"
    assert turns[1]["source_kind"] == "provisional_local_speaker_manifest"
    assert turns[1]["speech_seconds"] == 9
    assert all(turn["review_status"] == "needs_audio_review" for turn in turns)


def test_review_clip_respects_selected_voice_and_review_window():
    segments = [
        {"speaker": "Speaker_1", "start": 1, "end": 5},
        {"speaker": "Speaker_2", "start": 8, "end": 11},
        {"speaker": "Speaker_1", "start": 20, "end": 24},
    ]
    assert review_segment(segments, {"Speaker_1"}, [[19, 25]]) == segments[2]


def test_probable_self_id_is_only_a_name_screen():
    assert probable_self_id("Hi, Lisa Doeball from Langford", "Jane Doe")
    assert probable_self_id("Jane Doe, speaking to item 6", "Jane Doe")
    assert not probable_self_id("Lisa spoke after Mr. Doe", "Jane Doe")


def test_service_check_replaces_a_mixed_local_diarization_segment(tmp_path):
    service = tmp_path / "service.json"
    service.write_text(json.dumps({
        "clip_start_seconds": 100,
        "response": {"segments": [
            {"speaker": "other", "start": 0, "end": 5, "text": "Previous speaker"},
            {"speaker": "Jane Doe", "start": 6, "end": 12, "text": "Jane Doe"},
            {"speaker": "Jane Doe", "start": 11, "end": 15, "text": "My remarks"},
        ]},
    }))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"meetings": {"1": {
        "speaker_labels": ["Speaker_1"],
        "service_check": {"path": str(service), "speaker_name": "Jane Doe"},
    }}}))
    rows = [{
        "meeting_id": 1, "audio_path": str(tmp_path / "audio.m4a"), "turns": [],
    }]

    attach_reviewed_local_turns(rows, manifest)

    assert rows[0]["review_source_kind"] == "provisional_service_diarization"
    assert rows[0]["local_reviewed_turns"][0]["start"] == 106
    assert rows[0]["local_reviewed_turns"][0]["end"] == 115
    assert rows[0]["local_reviewed_turns"][0]["speech_seconds"] == 9
