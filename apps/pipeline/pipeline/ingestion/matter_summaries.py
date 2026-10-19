"""Roll each matter's agenda items and motions up into resident-facing context.

Matters are created during ingestion with only a title and identifier, so the
matter page had nothing to say about what the matter is or where it stands.
This writes, per matter:

- ``plain_english_summary``: 1-2 sentences on what the matter is about.
- ``meta.status_line``: where it stands now, with the latest step and date.
- ``meta.display_title``: a short human title (the raw ``title`` is kept as-is
  because the matcher uses it to link future agenda items).
- ``category``: a topic, replacing the catch-all "General".
- ``status``: derived from the latest decision when it is clear.
"""
from __future__ import annotations

import json
import re
from typing import Iterable

from supabase import Client

from pipeline.ai_provider import generate_text

TOPICS = [
    "Development",
    "Housing",
    "Transportation",
    "Environment",
    "Parks & Recreation",
    "Finance",
    "Public Safety",
    "Utilities & Infrastructure",
    "Community",
    "Administration",
]
STATUSES = ["Active", "Adopted", "Approved", "Defeated", "Withdrawn", "Completed"]

SYSTEM = f"""You explain city council matters to residents of a small Canadian city.
For each matter you get its raw title and its history (agenda items, motions, and staff reports or
attached documents with their key facts, oldest first). The reports are the best source for what the
matter actually is; use them.
Return for each matter:
- "display_title": a short, plain title (max 8 words) naming the thing itself, e.g. "Solid waste collection bylaw", "854 Latoria Road rezoning". No reading stages, no "(Background report attached)", no years unless essential. Keep a street address when the matter is about a property.
- "summary": 2-3 sentences, max 60 words, saying what the matter actually is and why it matters to residents. Be concrete and lead with the substance: for a development, what would be built (use, units, storeys, tenure) and where; for a bylaw or program, what changes for residents, what it costs them, and why the city is doing it. No bylaw numbers, no "Council" as the opening word, no jargon. Do not mention readings, approval or status here; that belongs in status_line.
- "status_line": max 18 words on where it stands now: the latest step and its date (e.g. "Third reading given Sep 28, 2026; final adoption still to come."). Use the dates provided.
- "timeline": for each history entry, {{"item": <its item id>, "headline": "<max 12 words>"}} — a plain-English headline for that step that says what happened, e.g. "Staff propose city-run curbside garbage and organics pickup" or "Third reading for 120-unit rental building". No agenda numbering, no "(Background report attached)".
- "category": exactly one of {", ".join(TOPICS)}.
- "status": exactly one of {", ".join(STATUSES)}. Adopted = bylaw finally adopted; Approved = non-bylaw item approved; Defeated/Withdrawn when the latest decision says so; Completed = received for information or finished with nothing pending; otherwise Active.
Never invent facts that are not in the inputs. If the history is too thin to say what it is about, base the summary on the title alone and keep it short."""

MAX_HISTORY = 12


def _paginate(query_fn, page: int = 1000) -> list[dict]:
    rows: list[dict] = []
    start = 0
    while True:
        chunk = query_fn().range(start, start + page - 1).execute().data or []
        rows.extend(chunk)
        if len(chunk) < page:
            return rows
        start += page


def _load_context(supabase: Client, matter_ids: list[int]) -> list[dict]:
    matters = (
        supabase.table("matters")
        .select("id, title, identifier, category, status, meta")
        .in_("id", matter_ids)
        .execute()
        .data
        or []
    )
    # Merged duplicates (aliases) keep their agenda items; read them as the canonical's history.
    owner = {m["id"]: m["id"] for m in matters}
    for m in matters:
        for alias_id in (m.get("meta") or {}).get("merged_matter_ids") or []:
            owner[int(alias_id)] = m["id"]
    items = (
        supabase.table("agenda_items")
        .select("id, matter_id, title, plain_english_summary, debate_summary, meetings(meeting_date, type)")
        .in_("matter_id", list(owner))
        .execute()
        .data
        or []
    )
    for item in items:
        item["matter_id"] = owner.get(item["matter_id"], item["matter_id"])
    item_ids = [i["id"] for i in items]
    motions = (
        supabase.table("motions")
        .select("agenda_item_id, plain_english_summary, text_content, result")
        .in_("agenda_item_id", item_ids)
        .execute()
        .data
        or []
    ) if item_ids else []
    docs = (
        supabase.table("extracted_documents")
        .select("agenda_item_id, title, document_type, summary, key_facts")
        .in_("agenda_item_id", item_ids)
        .execute()
        .data
        or []
    ) if item_ids else []
    docs_by_item: dict[int, list[dict]] = {}
    # Staff reports first; drawings, schedules and forms add little.
    rank = lambda d: 0 if "report" in (d.get("document_type") or "").lower() or "report" in (d.get("title") or "").lower() else 1
    for d in sorted(docs, key=rank):
        docs_by_item.setdefault(d["agenda_item_id"], []).append(d)
    motions_by_item: dict[int, list[dict]] = {}
    for m in motions:
        motions_by_item.setdefault(m["agenda_item_id"], []).append(m)

    out = []
    for matter in matters:
        history = []
        for item in items:
            if item["matter_id"] != matter["id"]:
                continue
            meeting = item.get("meetings") or {}
            history.append(
                {
                    "item": item["id"],
                    "date": meeting.get("meeting_date"),
                    "meeting": meeting.get("type"),
                    "agenda_item": item.get("title"),
                    "summary": (item.get("plain_english_summary") or "")[:400],
                    "debate": (item.get("debate_summary") or "")[:300] or None,
                    "motions": [
                        {
                            "decision": m.get("plain_english_summary") or (m.get("text_content") or "")[:300],
                            "result": m.get("result"),
                        }
                        for m in motions_by_item.get(item["id"], [])
                    ],
                    "reports": [
                        {"title": d.get("title"), "summary": (d.get("summary") or "")[:500], "key_facts": (d.get("key_facts") or [])[:10]}
                        for d in docs_by_item.get(item["id"], [])[:3]
                    ],
                }
            )
        history.sort(key=lambda h: h["date"] or "")
        out.append(
            {
                "id": matter["id"],
                "title": matter["title"],
                "identifier": matter.get("identifier"),
                "history": history[-MAX_HISTORY:],
                "_meta": matter.get("meta") or {},
            }
        )
    return out


def _prompt(batch: list[dict]) -> str:
    payload = [{k: v for k, v in m.items() if not k.startswith("_")} for m in batch]
    return (
        "Write context for each matter below. Return ONLY a JSON array of objects with keys "
        '"id", "display_title", "summary", "status_line", "timeline", "category", "status" — one per matter, same ids.\n\n'
        + json.dumps(payload, ensure_ascii=False, default=str)
    )


def _parse(text: str) -> dict[int, dict]:
    match = re.search(r"\[.*\]", text or "", re.S)
    if not match:
        raise ValueError("model did not return a JSON array")
    out: dict[int, dict] = {}
    for item in json.loads(match.group(0)):
        if item.get("id") is None or not (item.get("summary") or "").strip():
            continue
        out[int(item["id"])] = item
    return out


def refresh_matter_summaries(
    supabase: Client,
    matter_ids: Iterable[int],
    *,
    batch_size: int = 8,
    dry_run: bool = False,
) -> dict[int, dict]:
    """Regenerate summaries for the given matters. Returns {matter_id: fields}."""
    ids = sorted({int(i) for i in matter_ids})
    results: dict[int, dict] = {}
    for start in range(0, len(ids), batch_size):
        batch = _load_context(supabase, ids[start : start + batch_size])
        if not batch:
            continue
        try:
            parsed = _parse(generate_text(_prompt(batch), scope="extraction", system=SYSTEM, retries=3) or "")
        except Exception as exc:  # keep going; one bad batch shouldn't stop a backfill
            print(f"  [MatterSummaries] batch {ids[start]}…: {exc}")
            continue
        for matter in batch:
            fields = parsed.get(matter["id"])
            if not fields:
                continue
            meta = dict(matter["_meta"])
            meta["display_title"] = (fields.get("display_title") or "").strip() or None
            meta["status_line"] = (fields.get("status_line") or "").strip() or None
            meta["timeline_headlines"] = {
                str(t["item"]): t["headline"].strip()
                for t in fields.get("timeline") or []
                if isinstance(t, dict) and t.get("item") is not None and (t.get("headline") or "").strip()
            }
            update = {"plain_english_summary": fields["summary"].strip(), "meta": meta}
            if fields.get("category") in TOPICS:
                update["category"] = fields["category"]
            if fields.get("status") in STATUSES:
                update["status"] = fields["status"]
            results[matter["id"]] = update
            if not dry_run:
                supabase.table("matters").update(update).eq("id", matter["id"]).execute()
        print(f"  [MatterSummaries] {min(start + batch_size, len(ids))}/{len(ids)}")
    return results


def matters_for_meetings(supabase: Client, meeting_ids: list[int]) -> list[int]:
    rows = (
        supabase.table("agenda_items")
        .select("matter_id")
        .in_("meeting_id", meeting_ids)
        .not_.is_("matter_id", "null")
        .execute()
        .data
        or []
    )
    return sorted({r["matter_id"] for r in rows})


def all_matter_ids(supabase: Client, only_missing: bool = False, since: str | None = None) -> list[int]:
    def q():
        query = supabase.table("matters").select("id").order("id").is_("meta->>canonical_matter_id", "null")
        if since:
            query = query.gte("last_seen", since)
        return query.is_("plain_english_summary", "null") if only_missing else query

    return [r["id"] for r in _paginate(q)]
