"""Public diarization output contracts, independent of the acoustic model backend."""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from pipeline.local_diarizer import LocalDiarizer


@pytest.mark.parametrize('coverage_end,competitors,competition', [
    (10., [], 0.),
    (10., [(0., .6, 'B'), (.6, 1.2, 'C'), (0., .6, 'B')], .12),
    (10., [(0., .8, 'B'), (0., .8, 'C')], .08),
    (10., [(0., 1.004, 'B')], .1004),
    (8.996, [], 0.),
])
def test_saved_transcript_preserves_voice_identity_and_aggregates_split_turns(
    tmp_path, monkeypatch, coverage_end, competitors, competition
):
    audio = tmp_path / "meeting.wav"
    audio.touch()
    voice = np.array([1.] + [0.] * 191)
    diarizer = LocalDiarizer()
    diarizer._known_fingerprints = {"reference": {
        "person_id": 21, "person_name": "Colby Harder", "embedding": voice,
    }}
    # One speaker across four separate VAD regions in the same ASR sentence.
    # The repeated region must not be counted twice.
    diarizer._senko_diarizer = SimpleNamespace(diarize=lambda _: {
        "merged_segments": [
            {"speaker": "SPEAKER_00", "start": start, "end": end}
            for start, end in [(0, 2), (2, 5), (5, 8), (8, coverage_end), (0, 2)]
        ] + [{'start': start, 'end': end, 'speaker': label} for start, end, label in competitors],
        "speaker_centroids": {"SPEAKER_00": voice},
    })
    monkeypatch.setattr(diarizer, "_prepare_audio", lambda *_: str(audio))
    diarizer.diarize_audio(str(audio), existing_transcript=[
        {"start": 0., "end": 10., "text": "A complete statement across multiple voice regions."},
    ])
    saved = json.loads(audio.with_suffix(".json").read_text())
    segment = saved["segments"][0]
    assert segment["speaker"] == "Speaker_0"
    assert segment["speaker_name"] == "Colby Harder"
    assert segment["speaker_confidence"] == pytest.approx(coverage_end / 10.)
    assert segment['competing_speaker_fraction'] == pytest.approx(competition)
    assert saved["diarization_segments"][0]["speaker"] == "SPEAKER_00"
    assert saved["attribution_policy"]["timing_method"] == "unrounded_union_all_competitors_v2"


def test_transcription_token_timing_survives_saved_output_and_cached_rediarization(tmp_path, monkeypatch):
    audio = tmp_path / "meeting.wav"
    audio.touch()
    # Parakeet's CLI JSON contains timed subword tokens, not just sentences.
    tokens = [
        {"id": 5, "text": "Hello", "start": 0.1, "end": 0.5, "duration": 0.4, "confidence": 0.98},
        {"id": 8, "text": " there.", "start": 0.6, "end": 1.2, "duration": 0.6, "confidence": 0.94},
    ]
    cli_calls = []

    def run_cli(arguments, **kwargs):
        cli_calls.append(arguments)
        output = Path(arguments[arguments.index("--output-dir") + 1]) / "meeting.json"
        output.write_text(json.dumps({"sentences": [
            {"start": 0.1, "end": 1.2, "text": "Hello there.", "tokens": tokens},
        ]}))
        return SimpleNamespace(poll=lambda: 0, communicate=lambda: ("", ""), returncode=0)

    diarizer = LocalDiarizer()
    diarizer._senko_diarizer = SimpleNamespace(diarize=lambda _: {
        "merged_segments": [{"speaker": "SPEAKER_00", "start": 0., "end": 2.}],
        "speaker_centroids": {},
    })
    monkeypatch.setattr(diarizer, "_prepare_audio", lambda *_: str(audio))
    monkeypatch.setattr(diarizer, "_get_audio_duration", lambda *_: 2.)
    monkeypatch.setattr("pipeline.local_diarizer.subprocess.Popen", run_cli)

    diarizer.diarize_audio(str(audio))
    raw = json.loads((tmp_path / "meeting_raw_transcript.json").read_text())
    assert raw[0]["tokens"] == tokens
    assert json.loads(audio.with_suffix(".json").read_text())["segments"][0]["tokens"] == tokens

    diarizer.diarize_audio(str(audio), rediarize=True)
    replay = json.loads(audio.with_suffix(".json").read_text())["segments"][0]
    assert replay["tokens"] == tokens
    assert (replay["start"], replay["end"], replay["text"], replay["speaker"]) == (0.1, 1.2, "Hello there.", "Speaker_0")
    assert len(cli_calls) == 1
