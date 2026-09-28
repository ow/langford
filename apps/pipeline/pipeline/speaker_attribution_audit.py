"""Cross-check a person-specific speaker manifest against local ASR and minutes.

This is an evidence screen, not an audio verification or identity classifier.
Run after speaker_research to produce a CSV for human investigation.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np


def unit(values: list[float]) -> np.ndarray:
    vector = np.asarray(values, dtype=np.float32)
    return vector / np.linalg.norm(vector)


def probable_self_id(text: str, name: str) -> bool:
    """Allow small ASR spelling variations; this is only a screening signal."""
    parts = name.lower().split()
    if len(parts) < 2:
        return False
    words = re.findall(r"[a-z]+", text[:1000].lower())
    for index, word in enumerate(words):
        if SequenceMatcher(None, word, parts[0]).ratio() < 0.8:
            continue
        if any(
            SequenceMatcher(None, next_word, parts[-1]).ratio() >= 0.6
            for next_word in words[index + 1 : index + 4]
        ):
            return True
    return False


def audit(
    name: str, manifest_path: Path, inventory_path: Path, turns_path: Path
) -> list[dict]:
    reviews = json.loads(manifest_path.read_text(encoding="utf-8"))["meetings"]
    inventory = {row["meeting_id"]: row for row in csv.DictReader(inventory_path.open())}
    turns: dict[str, list[dict]] = {}
    for row in csv.DictReader(turns_path.open()):
        turns.setdefault(row["meeting_id"], []).append(row)

    transcripts = {}
    for meeting_id, review in reviews.items():
        meeting = inventory.get(meeting_id)
        if not meeting or not meeting.get("audio_path"):
            continue
        path = Path(meeting["audio_path"]).with_suffix(".json")
        if path.exists():
            transcripts[meeting_id] = json.loads(path.read_text(encoding="utf-8"))

    reference_vectors = {}
    for meeting_id, data in transcripts.items():
        centroids = data.get("speaker_centroids", {})
        labels = reviews[meeting_id]["speaker_labels"]
        vectors = [
            unit(centroids[key])
            for label in labels
            if (key := f"SPEAKER_{int(label.split('_')[-1]):02d}") in centroids
        ]
        if vectors:
            reference_vectors[meeting_id] = np.mean(vectors, axis=0)

    output = []
    for meeting_id, data in sorted(transcripts.items(), key=lambda pair: inventory[pair[0]]["date"]):
        meeting = inventory[meeting_id]
        labels = set(reviews[meeting_id]["speaker_labels"])
        selected = [s for s in data.get("segments", []) if s.get("speaker") in labels]
        selected_text = " ".join(s["text"] for s in selected)
        selected_seconds = sum(max(0, s["end"] - s["start"]) for s in selected)
        included = [
            row for row in turns.get(meeting_id, [])
            if row["source_kind"] in {
                "provisional_local_speaker_manifest", "provisional_service_diarization"
            }
        ]
        included_seconds = sum(float(row["speech_seconds"]) for row in included)
        rank = None
        similarity = None
        margin = None
        if meeting_id in reference_vectors and len(reference_vectors) > 1:
            others = [vector for key, vector in reference_vectors.items() if key != meeting_id]
            reference = unit(np.mean(others, axis=0).tolist())
            scores = sorted(
                (
                    (float(np.dot(reference, unit(values))), key)
                    for key, values in data.get("speaker_centroids", {}).items()
                ),
                reverse=True,
            )
            selected_keys = {f"SPEAKER_{int(label.split('_')[-1]):02d}" for label in labels}
            selected_ranks = [i + 1 for i, (_, key) in enumerate(scores) if key in selected_keys]
            if selected_ranks:
                rank = min(selected_ranks)
                similarity = scores[rank - 1][0]
                if rank == 1 and len(scores) > 1:
                    margin = similarity - scores[1][0]
        minutes_match = int(meeting.get("name_mentions") or 0) > 0
        self_id = probable_self_id(selected_text, name)
        flags = []
        if not minutes_match:
            flags.append("no_minutes_name_match")
        if not self_id:
            flags.append("self_identification_not_detected")
        if rank != 1:
            flags.append("selected_voice_not_top_match")
        if margin is not None and margin < 0.1:
            flags.append("small_voice_margin")
        has_local_turns = bool(included)
        if has_local_turns and selected_seconds - included_seconds > 10:
            flags.append("selected_voice_has_excluded_audio")
        if any(s["end"] - s["start"] > 45 for s in selected):
            flags.append("long_asr_segment_check_boundary")
        output.append({
            "meeting_id": meeting_id,
            "date": meeting["date"],
            "speaker_labels": " | ".join(sorted(labels)),
            "timing_source": included[0]["source_kind"] if included else "archive_transcript_name_match",
            "minutes_name_mentions": meeting.get("name_mentions", ""),
            "self_identification_detected": self_id,
            "leave_one_out_voice_rank": rank or "",
            "leave_one_out_similarity": round(similarity, 3) if similarity is not None else "",
            "margin_over_next_voice": round(margin, 3) if margin is not None else "",
            "included_speech_seconds": round(included_seconds, 2) if has_local_turns else "",
            "excluded_same_label_seconds": (
                round(max(0, selected_seconds - included_seconds), 2) if has_local_turns else ""
            ),
            "flags": " | ".join(flags),
            "minutes_url": meeting.get("minutes_url", ""),
            "official_recording_url": meeting.get("video_url", ""),
        })
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--review-manifest", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--turns", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = audit(args.name, args.review_manifest, args.inventory, args.turns)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    print(json.dumps({"meetings": len(rows), "output": str(args.output)}))


if __name__ == "__main__":
    main()
