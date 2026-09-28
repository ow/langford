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
    aliases = name_aliases("Lisa Foxall", [])
    pattern = name_pattern(aliases)

    assert aliases == ["Lisa Foxall", "L. Foxall"]
    assert pattern.search("L. Foxall, Langford Resident - spoke to item 5.1")
    assert not pattern.search("C. Foxall, Langford Resident - spoke to item 5.1")


def test_minute_excerpt_stops_before_next_speaker_and_address():
    pattern = name_pattern(name_aliases("Lisa Foxall", []))
    text = (
        "L. Foxall, Players Dr - Expressed concern about taxes and the budget. "
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
            "turns": [{"id": 42, "speaker": "L. Foxall", "start": 10, "end": 20, "text": "Budget remarks"}],
            "local_reviewed_turns": [{"speaker": "Speaker_2", "start": 10, "end": 20, "speech_seconds": 10, "text": "Duplicate"}],
        },
        {
            **shared,
            "meeting_id": 2,
            "turns": [],
            "local_reviewed_turns": [{"speaker": "Speaker_3", "start": 30, "end": 42, "speech_seconds": 9, "text": "Another topic"}],
        },
    ]

    turns = build_turn_rows(rows, "Lisa Foxall", "https://example.org",)

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
    assert probable_self_id("Hi, Lisa Foxhall from Langford", "Lisa Foxall")
    assert probable_self_id("Lisa Foxall, speaking to item 6", "Lisa Foxall")
    assert not probable_self_id("Lisa spoke after Mr. Foxall", "Lisa Foxall")


def test_service_check_replaces_a_mixed_local_diarization_segment(tmp_path):
    (tmp_path / "audio.json").write_text(json.dumps({"segments": [
        {"speaker": "Speaker_1", "start": 10, "end": 20, "text": "Earlier turn"},
    ]}))
    service = tmp_path / "service.json"
    service.write_text(json.dumps({
        "clip_start_seconds": 100,
        "response": {"segments": [
            {"speaker": "other", "start": 0, "end": 5, "text": "Previous speaker"},
            {"speaker": "Lisa Foxall", "start": 6, "end": 12, "text": "Lisa Foxall"},
            {"speaker": "Lisa Foxall", "start": 11, "end": 15, "text": "My remarks"},
        ]},
    }))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"meetings": {"1": {
        "speaker_labels": ["Speaker_1"],
        "service_check": {
            "path": str(service), "speaker_name": "Lisa Foxall",
            "include_local_windows": [[10, 20]],
        },
    }}}))
    rows = [{
        "meeting_id": 1, "audio_path": str(tmp_path / "audio.m4a"), "turns": [],
    }]

    attach_reviewed_local_turns(rows, manifest)

    assert rows[0]["review_source_kind"] == "provisional_service_diarization"
    assert [turn["source_kind"] for turn in rows[0]["local_reviewed_turns"]] == [
        "provisional_local_speaker_manifest", "provisional_service_diarization"
    ]
    assert rows[0]["local_reviewed_turns"][1]["start"] == 106
    assert rows[0]["local_reviewed_turns"][1]["end"] == 115
    assert rows[0]["local_reviewed_turns"][1]["speech_seconds"] == 9
