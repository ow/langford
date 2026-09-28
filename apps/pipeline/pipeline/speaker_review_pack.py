"""Create a local listening pack for provisional speaker identifications."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import subprocess
from pathlib import Path

from dotenv import load_dotenv
import psycopg2

from .speaker_research import PROJECT_ROOT, name_aliases, research_rows


def review_segment(segments: list[dict], labels: set[str], windows: list[list[float]]) -> dict | None:
    for segment in segments:
        if segment.get("speaker") not in labels:
            continue
        start, end = float(segment["start"]), float(segment["end"])
        if windows and not any(start >= lower and end <= upper for lower, upper in windows):
            continue
        return segment
    return None


def write_review_pack(rows: list[dict], manifest: dict, output: Path) -> int:
    output.mkdir(parents=True, exist_ok=True)
    clips = output / "clips"
    clips.mkdir(exist_ok=True)
    by_meeting = {str(row["meeting_id"]): row for row in rows}
    reviews = []
    for meeting_id, review in manifest.get("meetings", {}).items():
        meeting = by_meeting.get(meeting_id)
        if not meeting or not meeting.get("audio_path"):
            continue
        transcript_path = Path(meeting["audio_path"]).with_suffix(".json")
        if not transcript_path.exists():
            continue
        transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
        segment = review_segment(
            transcript.get("segments", []),
            set(review.get("speaker_labels", [])),
            review.get("include_windows", []),
        )
        if not segment:
            continue

        start = max(0, float(segment["start"]) - 2)
        end = max(start + 1, min(float(segment["end"]) + 3, start + 18))
        clip = clips / f"meeting-{meeting_id}.mp3"
        if not clip.exists():
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-ss", str(start), "-t", str(end - start),
                 "-i", meeting["audio_path"], "-vn", "-ac", "1",
                 "-ar", "16000", "-b:a", "32k", str(clip)],
                check=True,
            )
        reviews.append({
            "meeting_id": meeting_id,
            "date": meeting["date"],
            "speaker_label": segment["speaker"],
            "clip_start_seconds": round(start, 2),
            "clip_end_seconds": round(end, 2),
            "clip_path": f"clips/{clip.name}",
            "transcript_opening": " ".join(segment["text"].split())[:500],
            "minutes_url": meeting.get("minutes_url") or "",
            "official_recording_url": meeting.get("video_url") or "",
            "evidence": review.get("evidence", ""),
            "review_status": "pending_audio_review",
        })

    reviews.sort(key=lambda row: (row["date"], int(row["meeting_id"])))
    fields = list(reviews[0]) if reviews else [
        "meeting_id", "date", "speaker_label", "clip_start_seconds",
        "clip_end_seconds", "clip_path", "transcript_opening", "minutes_url",
        "official_recording_url", "evidence", "review_status",
    ]
    with (output / "review.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(reviews)

    cards = []
    for row in reviews:
        links = " ".join(
            f'<a href="{html.escape(row[key], quote=True)}" target="_blank" rel="noopener noreferrer">{label}</a>'
            for key, label in [("minutes_url", "Minutes"), ("official_recording_url", "Full recording")]
            if row[key]
        )
        cards.append(
            f'<article><h2>{html.escape(row["date"])} · Meeting {row["meeting_id"]}</h2>'
            f'<p><strong>{html.escape(row["speaker_label"])}</strong> · '
            f'{row["clip_start_seconds"]:.1f}–{row["clip_end_seconds"]:.1f} seconds · '
            f'{html.escape(row["review_status"])}</p>'
            f'<audio controls preload="none" src="{html.escape(row["clip_path"], quote=True)}"></audio>'
            f'<blockquote>{html.escape(row["transcript_opening"])}</blockquote>'
            f'<p>{links}</p></article>'
        )
    page = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Speaker audio review</title>'
        '<style>body{font:16px/1.5 system-ui,sans-serif;max-width:850px;margin:2rem auto;padding:0 1rem;color:#18181b}'
        'article{border:1px solid #ddd;border-radius:12px;padding:1rem 1.25rem;margin:1rem 0}'
        'h2{font-size:1.15rem;margin:.25rem 0}audio{width:100%}blockquote{margin:1rem 0;padding-left:1rem;border-left:3px solid #aaa}'
        'a{margin-right:1rem}</style><main><h1>Speaker audio review</h1>'
        '<p>Listen for the self-introduction and compare it with the transcript and official minutes. '
        'These clips are research leads; the full recording is the source for final attribution and timing.</p>'
        + "".join(cards) + '</main></html>'
    )
    (output / "index.html").write_text(page, encoding="utf-8")
    return len(reviews)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--alias", action="append", default=[])
    parser.add_argument("--municipality", default="langford")
    parser.add_argument("--review-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    load_dotenv(PROJECT_ROOT / ".env")
    import os
    if not os.environ.get("DATABASE_URL"):
        parser.error("DATABASE_URL is required")
    slug = re.sub(r"[^a-z0-9]+", "-", args.name.lower()).strip("-")
    output = args.output or PROJECT_ROOT / "research" / f"{slug}-audio-review"
    with psycopg2.connect(os.environ["DATABASE_URL"]) as connection:
        rows = research_rows(connection, args.municipality, name_aliases(args.name, args.alias))
    manifest = json.loads(args.review_manifest.read_text(encoding="utf-8"))
    print(json.dumps({"clips": write_review_pack(rows, manifest, output), "index": str(output / "index.html")}))


if __name__ == "__main__":
    main()
