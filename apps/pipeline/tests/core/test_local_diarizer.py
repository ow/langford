"""Public diarization output contracts, independent of the acoustic model backend."""
import json
from types import SimpleNamespace

import numpy as np

from pipeline.local_diarizer import LocalDiarizer


def test_saved_transcript_preserves_voice_identity_and_aggregates_split_turns(tmp_path, monkeypatch):
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
            for start, end in [(0, 2), (2, 5), (5, 8), (8, 10), (0, 2)]
        ],
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
    assert segment["speaker_confidence"] == 1.0
    assert saved["diarization_segments"][0]["speaker"] == "SPEAKER_00"
    assert saved["attribution_policy"]["timing_method"] == "union_overlap_by_speaker_v1"
