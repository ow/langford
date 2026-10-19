"""Link extracted documents to agenda items where the extractor's guess failed.

The extractor matched the model's item-number guess ("6.1a") against agenda
numbering and almost always missed, so ~99% of extracted reports had no
agenda item and were invisible to matters, summaries and search context.
For each unlinked document, the Decisions API picks which of its meeting's
agenda items it belongs to (or none).
"""
from __future__ import annotations

from collections import defaultdict

from supabase import Client

from pipeline import decisions

MIN_PROBABILITY = 0.75
PROCEDURAL = ("call to order", "adjourn", "approval of the agenda", "territorial acknowledgement",
              "meeting conduct", "in camera", "closed meeting")


def _paginate(build, page: int = 1000) -> list[dict]:
    rows, start = [], 0
    while True:
        chunk = build().range(start, start + page - 1).execute().data or []
        rows.extend(chunk)
        if len(chunk) < page:
            return rows
        start += page


def relink(supabase: Client, *, dry_run: bool = False, limit: int | None = None) -> dict:
    docs = _paginate(
        lambda: supabase.table("extracted_documents")
        .select("id, document_id, title, document_type, summary, documents(meeting_id)")
        .is_("agenda_item_id", "null")
        .order("id")
    )
    if limit:
        docs = docs[:limit]
    meeting_ids = sorted({(d.get("documents") or {}).get("meeting_id") for d in docs} - {None})
    items_by_meeting: dict[int, list[dict]] = defaultdict(list)
    for start in range(0, len(meeting_ids), 50):
        for it in (
            supabase.table("agenda_items")
            .select("id, meeting_id, item_order, title, plain_english_summary")
            .in_("meeting_id", meeting_ids[start : start + 50])
            .execute()
            .data
            or []
        ):
            if not any(p in (it.get("title") or "").lower() for p in PROCEDURAL):
                items_by_meeting[it["meeting_id"]].append(it)

    jobs, job_docs = [], []
    for d in docs:
        items = items_by_meeting.get((d.get("documents") or {}).get("meeting_id")) or []
        if not items:
            continue
        question = decisions.choice(
            "item",
            "A document was attached to a council meeting agenda. Which agenda item does it belong to? "
            "Choose 'none' if it is the agenda itself, minutes of this meeting, or fits no item.",
            [(f"i{it['id']}", f"{it.get('item_order') or ''} {it.get('title') or ''} — {(it.get('plain_english_summary') or '')[:160]}".strip())
             for it in items[:60]]
            + [("none", "Not about any single agenda item.")],
        )
        jobs.append((f"DOCUMENT: {d['title']} ({d.get('document_type')})\n{(d.get('summary') or '')[:800]}", [question]))
        job_docs.append(d)

    linked = skipped = failed = 0
    for start in range(0, len(jobs), 200):
        for d, res in zip(job_docs[start : start + 200], decisions.decide_many(jobs[start : start + 200])):
            if isinstance(res, Exception):
                failed += 1
                continue
            ans = res.get("item")
            if ans is None or ans.type != "choice" or ans.choice == "none":
                skipped += 1
                continue
            prob = {p.value: p.probability for p in ans.probabilities}.get(ans.choice, 0)
            if prob < MIN_PROBABILITY:
                skipped += 1
                continue
            item_id = int(ans.choice[1:])
            if not dry_run:
                supabase.table("extracted_documents").update({"agenda_item_id": item_id}).eq("id", d["id"]).execute()
                supabase.table("document_sections").update({"agenda_item_id": item_id}).eq("extracted_document_id", d["id"]).execute()
            linked += 1
        print(f"  [Relink] {min(start + 200, len(jobs))}/{len(jobs)} — linked {linked}, skipped {skipped}, failed {failed}")
    return {"documents": len(docs), "judged": len(jobs), "linked": linked, "skipped": skipped, "failed": failed}
