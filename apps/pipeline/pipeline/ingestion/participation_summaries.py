"""Turn public participation / delegation segments into readable bullets.

Those agenda items only had a one-line summary ("many speakers on the
Transportation Master Plan"). The transcript for the item's time window holds
what each person actually said; this writes one bullet per speaker to
``agenda_items.meta.participation``:

    {"overview": str, "speakers": [{"who": str, "position": str, "point": str, "topic": str}]}

Privacy: names require a confident registry spelling match. Unknown people use
a resident label and a verified street, never a house number, phone or email.
"""
from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel
from supabase import Client

from pipeline import ai
from .participation_validation import canonicalize_participation, load_name_evidence, load_streets

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
        .lt("start_time", end)
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
    people, statements = load_name_evidence(supabase)
    result = canonicalize_participation(data, people=people, statement_names=statements,
                                      street_evidence=load_streets(),
                                      source_text=' '.join(seg.get('text_content') or '' for seg in segments))
    if not dry_run:
        meta = dict(item.get("meta") or {})
        meta["participation"] = result
        meta["participation_version"] = PARTICIPATION_VERSION
        # Another worker may be enriching this item's timings or matter links.
        # A slow model response must not overwrite those concurrent changes.
        update = supabase.table("agenda_items").update({"meta": meta}).eq("id", agenda_item_id)
        update = update.is_("meta", "null") if item.get("meta") is None else update.eq("meta", json.dumps(item["meta"]))
        if not update.execute().data:
            print(f"  [!] Participation summary held: agenda item {agenda_item_id} metadata changed concurrently")
            return None
    return result
