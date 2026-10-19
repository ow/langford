"""Turn public participation / delegation segments into readable bullets.

Those agenda items only had a one-line summary ("many speakers on the
Transportation Master Plan"). The transcript for the item's time window holds
what each person actually said; this writes one bullet per speaker to
``agenda_items.meta.participation``:

    {"overview": str, "speakers": [{"who": str, "position": str, "point": str, "topic": str}]}

Privacy: people are named as they introduced themselves, with at most their
street or neighbourhood, never a house number, phone or email.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel
from supabase import Client

from pipeline import ai

PARTICIPATION_TITLE = re.compile(r"public participation|delegations?|public input|question period|public hearing", re.I)
MAX_CHARS = 60_000
# Bump when the prompt/schema changes; stamped in agenda_items.meta.participation_version.
PARTICIPATION_VERSION = "1"


class ParticipationSpeaker(BaseModel):
    who: str
    position: Literal["supports", "opposes", "concerned", "asks", "mixed", "other"]
    point: str
    topic: str


class Participation(BaseModel):
    overview: str
    speakers: list[ParticipationSpeaker]

SYSTEM = """You summarize the public comment portion of a city council meeting for residents.
You get the transcript of that portion (speaker labels may be generic like "Speaker_12"; the mayor or chair manages the queue).
Return JSON: {"overview": "<one sentence: how many people spoke and on what>", "speakers": [ ... ]}
One entry per member of the public who spoke, in order, each:
- "who": the name as they introduced themselves, optionally with their street or neighbourhood in parentheses, e.g. "Johnny Lang (Hoffman Ave)". Never include house numbers, unit numbers, phone numbers or emails. If they gave no name, use "A resident" (plus street/neighbourhood if stated) or the organization they represent.
- "position": one of "supports", "opposes", "concerned", "asks", "mixed", "other".
- "point": one plain sentence, max 25 words, with their main argument or request. Start with the verb ("Opposes the connector, citing ...", "Asks council to ..."). Never use pronouns (he/she/they) for the speaker. Concrete, no filler.
- "topic": the agenda item or subject they addressed, in a few words (e.g. "Transportation Master Plan", "Hoffman Ave connector").
Skip council members, staff and the chair. Skip procedural back-and-forth. Do not invent anything not in the transcript."""


def summarize_participation(supabase: Client, agenda_item_id: int, *, dry_run: bool = False) -> dict | None:
    item = (
        supabase.table("agenda_items")
        .select("id, meeting_id, title, meta, discussion_start_time, discussion_end_time")
        .eq("id", agenda_item_id)
        .single()
        .execute()
        .data
    )
    start, end = item.get("discussion_start_time"), item.get("discussion_end_time")
    if start is None or end is None or end <= start:
        return None
    segments = (
        supabase.table("transcript_segments")
        .select("start_time, speaker_name, text_content")
        .eq("meeting_id", item["meeting_id"])
        .gte("start_time", start)
        .lte("start_time", end)
        .order("start_time")
        .limit(2000)
        .execute()
        .data
        or []
    )
    if not segments:
        return None
    lines, last = [], None
    for seg in segments:
        who = seg.get("speaker_name") or "Unknown"
        text = (seg.get("text_content") or "").strip()
        if not text:
            continue
        if who == last:
            lines[-1] += " " + text
        else:
            lines.append(f"{who}: {text}")
            last = who
    transcript = "\n".join(lines)[:MAX_CHARS]
    data = ai.json(
        f"Agenda item: {item['title']}\n\nTRANSCRIPT:\n{transcript}",
        stage="extraction",
        system=SYSTEM,
        schema=Participation,
    ).model_dump()
    speakers = [
        {
            "who": re.sub(r"\b\d{1,5}\s+(?=[A-Z])", "", (s.get("who") or "A resident")).strip(),  # belt and braces: no house numbers
            "position": s.get("position") or "other",
            "point": (s.get("point") or "").strip(),
            "topic": (s.get("topic") or "").strip(),
        }
        for s in data.get("speakers") or []
        if (s.get("point") or "").strip()
    ]
    result = {"overview": (data.get("overview") or "").strip(), "speakers": speakers}
    if not dry_run:
        meta = dict(item.get("meta") or {})
        meta["participation"] = result
        meta["participation_version"] = PARTICIPATION_VERSION
        supabase.table("agenda_items").update({"meta": meta}).eq("id", agenda_item_id).execute()
    return result
