from __future__ import annotations

import json
import os

from supabase import Client

from pipeline import config
from pipeline.ai_provider import generate_text
from pipeline.ingestion.ingester import MeetingIngester
from pipeline.paths import BASE_DIR


SUMMARY_SYSTEM = """You write concise municipal meeting summaries for residents.
Focus on what changed, what was decided, what was controversial, and what follow-up was directed.
Do not include attendance roll calls, procedural housekeeping, or filler conclusions."""


def _absolute_archive_path(archive_path: str) -> str:
    if os.path.isabs(archive_path):
        return archive_path
    return os.path.join(BASE_DIR, archive_path)


def _trim(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[TRUNCATED]"


def build_summary_prompt(meeting: dict, agenda_text: str, minutes_text: str, transcript_text: str) -> str:
    return f"""
Regenerate ONLY the public-facing meeting summary.

Meeting:
- Title: {meeting.get("title") or "Meeting"}
- Date: {meeting.get("meeting_date") or "Unknown"}
- Type: {meeting.get("type") or meeting.get("meeting_type") or "Unknown"}

Output rules:
- Return Markdown only. No JSON. No heading.
- Start with one short sentence naming the meeting type and date.
- Then provide 3-6 bullets.
- Each bullet should capture one substantive decision, direction, notable controversy, financial commitment, bylaw action, or land-use outcome.
- Prefer short, direct outcome language.
- Do not list attendees, chair names, call-to-order details, consent agenda housekeeping, adjournment, or generic final wrap-up.
- Keep the whole summary under 120 words unless the meeting had unusually many major outcomes.

Official minutes are the source of truth for decisions and vote outcomes.

MINUTES:
{_trim(minutes_text, 25000)}

AGENDA:
{_trim(agenda_text, 12000)}

TRANSCRIPT EXCERPT:
{_trim(transcript_text, 12000)}
""".strip()


def regenerate_meeting_summary(
    supabase: Client,
    meeting_id: int,
    *,
    municipality_id: int,
    update_refinement_file: bool = True,
) -> dict:
    meeting_res = (
        supabase.table("meetings")
        .select("id, title, type, meeting_date, archive_path")
        .eq("id", meeting_id)
        .eq("municipality_id", municipality_id)
        .single()
        .execute()
    )
    meeting = meeting_res.data
    if not meeting:
        raise ValueError(f"meeting_id not found: {meeting_id}")
    if not meeting.get("archive_path"):
        raise ValueError(f"meeting_id {meeting_id} has no archive_path")

    folder_path = _absolute_archive_path(meeting["archive_path"])
    if not os.path.isdir(folder_path):
        raise ValueError(f"archive path does not exist: {folder_path}")

    supabase_key = config.SUPABASE_SECRET_KEY or config.SUPABASE_KEY
    ingester = MeetingIngester(
        config.SUPABASE_URL,
        supabase_key,
        config.GEMINI_API_KEY,
        municipality_id=municipality_id,
    )
    agenda_text, minutes_text, transcript_text = ingester.get_raw_texts(folder_path)
    if len((minutes_text or "").strip()) < 100 and len((agenda_text or "").strip()) < 100:
        raise ValueError(f"meeting_id {meeting_id} has no usable agenda or minutes text")

    prompt = build_summary_prompt(meeting, agenda_text or "", minutes_text or "", transcript_text or "")
    summary = generate_text(
        prompt,
        scope="extraction",
        system=SUMMARY_SYSTEM,
        retries=3,
    )
    if not summary or len(summary.strip()) < 20:
        raise RuntimeError("summary generation returned an empty response")

    summary = summary.strip()
    supabase.table("meetings").update({"summary": summary}).eq("id", meeting_id).execute()

    refinement_updated = False
    if update_refinement_file:
        refinement_path = os.path.join(folder_path, "refinement.json")
        if os.path.exists(refinement_path):
            try:
                with open(refinement_path, "r", encoding="utf-8") as handle:
                    refinement = json.load(handle)
                refinement["summary"] = summary
                with open(refinement_path, "w", encoding="utf-8") as handle:
                    json.dump(refinement, handle, indent=2, ensure_ascii=False)
                    handle.write("\n")
                refinement_updated = True
            except Exception as exc:
                print(f"  [!] Failed to update refinement.json summary: {exc}")

    return {
        "meeting_id": meeting_id,
        "archive_path": meeting["archive_path"],
        "summary_chars": len(summary),
        "refinement_updated": refinement_updated,
    }
