"""Operational bookkeeping for pipeline discovery and worker jobs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from supabase import Client

from pipeline.scrapers.base import MunicipalityConfig, ScrapedMeeting


def meeting_source_record(
    municipality: MunicipalityConfig,
    source_type: str,
    meeting: ScrapedMeeting,
    archive_path: str | None = None,
    status: str = "discovered",
) -> dict[str, Any]:
    source_id = meeting.source_id or f"{meeting.date.isoformat()}:{meeting.title}"
    raw = dict(meeting.meta or {})
    raw.setdefault("documents", [doc.__dict__ for doc in meeting.documents])

    return {
        "municipality_id": municipality.id,
        "source_type": source_type,
        "source_id": source_id,
        "meeting_date": meeting.date.isoformat(),
        "title": meeting.title,
        "meeting_type": meeting.meeting_type,
        "source_url": meeting.agenda_url or meeting.minutes_url or meeting.video_url,
        "video_url": meeting.video_url,
        "archive_path": archive_path,
        "raw": raw,
        "status": status,
        "last_seen_at": datetime.now(timezone.utc).isoformat(),
    }


def upsert_source_meetings(
    supabase: Client,
    municipality: MunicipalityConfig,
    source_type: str,
    records: list[dict[str, Any]],
) -> int:
    if not records:
        return 0

    archive_paths = sorted(
        {
            record["archive_path"]
            for record in records
            if record.get("archive_path")
        }
    )
    if archive_paths:
        meetings = (
            supabase.table("meetings")
            .select("id, archive_path")
            .eq("municipality_id", municipality.id)
            .in_("archive_path", archive_paths)
            .execute()
            .data
            or []
        )
        meetings_by_path = {meeting["archive_path"]: meeting["id"] for meeting in meetings}
        for record in records:
            meeting_id = meetings_by_path.get(record.get("archive_path"))
            if meeting_id:
                record["ingested_meeting_id"] = meeting_id

    result = (
        supabase.table("source_meetings")
        .upsert(records, on_conflict="municipality_id,source_type,source_id")
        .execute()
    )
    return len(result.data or records)


def record_job_event(
    supabase: Client,
    job_id: int,
    message: str,
    level: str = "info",
    data: dict[str, Any] | None = None,
) -> None:
    supabase.table("pipeline_run_events").insert(
        {
            "job_id": job_id,
            "level": level,
            "message": message,
            "data": data or {},
        }
    ).execute()
