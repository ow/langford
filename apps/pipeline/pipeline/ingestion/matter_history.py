"""Reconcile missed agenda ownership without fuzzy merges or new matters.

The same title on a different year's recurring item is not proof of identity.
Only a unique, substantive title inside the matter's existing dated interval is
eligible for automatic repair. Other plausible matches remain review findings.
"""
from collections import defaultdict
import re

from .matter_matching import bylaw_identifiers, is_matter_eligible, matter_identifiers


def _pages(build):
    rows, start = [], 0
    while True:
        chunk = build().range(start, start + 499).execute().data or []
        rows.extend(chunk)
        if len(chunk) < 500:
            return rows
        start += 500


def _title(value):
    # Agenda time estimates do not change identity. Keep years, bylaw numbers,
    # application references and reading stages: do not normalize those away.
    value = re.sub(r"\s*\(\s*(?:approx\.?\s*)?\d+\s*(?:min(?:ute)?s?)\s*\)\s*$", "", value or "", flags=re.I)
    return " ".join(value.casefold().split())


def plan_history(matters, items, *, focus_ids=None):
    titles = defaultdict(list)
    for matter in matters:
        if not matter.get("canonical_matter_id") and matter.get("hidden") != "container":
            titles[(matter["municipality_id"], _title(matter["title"]))].append(matter)
    assignments, review, unmatched = [], [], []
    for item in items:
        if item.get("matter_id") is not None:
            continue
        meeting = item.get("meetings") or {}
        city, day = meeting.get("municipality_id"), str(meeting.get("meeting_date") or "")[:10]
        eligible, _ = is_matter_eligible(identifier=None, title=item.get("title"), category=item.get("category"), summary=item.get("plain_english_summary"))
        if not eligible:
            continue
        exact = titles.get((city, _title(item.get("title"))), [])
        # Ambiguity is assessed against ALL canonical matters in this city,
        # before focus filtering, so a targeted run cannot make a tie disappear.
        candidates = [m for m in exact if focus_ids is None or m["id"] in focus_ids]
        if not candidates:
            unmatched.append({"agenda_item_id": item["id"], "meeting_id": item["meeting_id"], "meeting_date": day, "title": item["title"], "reason": "no_exact_candidate_in_scope"})
            continue
        candidate = candidates[0]
        in_interval = bool(day and candidate.get("first_seen") and candidate.get("last_seen")
                           and str(candidate["first_seen"])[:10] <= day <= str(candidate["last_seen"])[:10])
        item_bylaws = bylaw_identifiers(item.get("title"))
        identifiers = matter_identifiers(candidate)
        target_bylaws = {key for key in identifiers if key.startswith("Bylaw ")}
        safe = len(exact) == 1 and in_interval and item_bylaws == target_bylaws and identifiers == target_bylaws
        finding = {"agenda_item_id": item["id"], "meeting_id": item["meeting_id"], "meeting_date": day,
                   "title": item["title"], "candidate_matter_ids": [m["id"] for m in candidates]}
        if safe:
            assignments.append({**finding, "matter_id": candidate["id"], "reason": "unique_exact_title_within_existing_dates"})
        else:
            review.append({**finding, "reason": "ambiguous_title" if len(exact) != 1 else "date_or_identifier_requires_review"})
    return {"assignments": assignments, "review": review, "unmatched_eligible": len(unmatched), "unmatched": unmatched}


def reconcile_history(supabase, *, municipality_ids=None, focus_ids=None, since=None, dry_run=True):
    """A dry run reads only; apply uses a still-unassigned ownership guard.

    Focus includes existing one-hop same-initiative neighbours, not recursively
    related topics. No matter is merged and no existing item owner is replaced.
    """
    if focus_ids is not None and not focus_ids:
        return {"assignments": [], "review": [], "unmatched_eligible": 0, "unmatched": [], "applied": [], "dry_run": dry_run}
    matters = _pages(lambda: supabase.table("matters")
                    .select("id, municipality_id, title, identifier, first_seen, last_seen, canonical_matter_id:meta->>canonical_matter_id, hidden:meta->>hidden")
                    .order("id"))
    if focus_ids is not None:
        focus = set(focus_ids)
        links = _pages(lambda: supabase.table("matter_links").select("matter_id,related_matter_id")
                       .eq("kind", "related_matter").eq("hidden", False).order("id"))
        original = set(focus)
        for link in links:
            if link["matter_id"] in original or link["related_matter_id"] in original:
                focus.update((link["matter_id"], link["related_matter_id"]))
        cities = {m["municipality_id"] for m in matters if m["id"] in original}
    else:
        focus = None
        cities = set(municipality_ids or [m["municipality_id"] for m in matters])
    if municipality_ids is not None:
        cities &= set(municipality_ids)
    matters = [m for m in matters if m["municipality_id"] in cities]
    items = []
    for city in sorted(cities):
        def build():
            q = supabase.table("agenda_items").select("id,meeting_id,matter_id,title,category,plain_english_summary,meetings!inner(municipality_id,meeting_date)") \
                .is_("matter_id", "null").eq("meetings.municipality_id", city).order("id")
            return q.gte("meetings.meeting_date", since) if since else q
        items.extend(_pages(build))
    plan = plan_history(matters, items, focus_ids=focus)
    applied = []
    if not dry_run:
        for assignment in plan["assignments"]:
            result = supabase.table("agenda_items").update({"matter_id": assignment["matter_id"]}) \
                .eq("id", assignment["agenda_item_id"]).eq("title", assignment["title"]) \
                .eq("meeting_id", assignment["meeting_id"]).is_("matter_id", "null").execute()
            if result.data:
                applied.append(assignment)
    return {**plan, "applied": applied, "dry_run": dry_run}
