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

import re

from supabase import Client

from .participation_validation import load_name_evidence, load_streets

PARTICIPATION_TITLE = re.compile(r"public participation|delegations?|public input|question period|public hearing", re.I)
# Bump when the prompt/schema changes; stamped in agenda_items.meta.participation_version.
PARTICIPATION_VERSION = "2"


def summarize_participation(supabase: Client, agenda_item_id: int, *, dry_run: bool = False) -> dict | None:
    """Generate only from complete, reviewed source windows; preserve concurrent edits."""
    from . import participation_evidence as evidence
    item = supabase.table("agenda_items").select("id,meeting_id,title,meta,discussion_start_time,discussion_end_time").eq("id", agenda_item_id).single().execute().data
    start, end = item.get("discussion_start_time"), item.get("discussion_end_time")
    if start is None or end is None or end <= start:
        return None
    segments = []
    while True:
        rows = (supabase.table("transcript_segments")
                .select("id,meeting_id,start_time,end_time,speaker_name,text_content")
                .eq("meeting_id", item["meeting_id"]).lt("start_time", end).gt("end_time", start)
                .order("start_time").order("id").range(len(segments), len(segments) + 999).execute().data or [])
        segments.extend(rows)
        if len(rows) < 1000 or len(segments) > 2000:
            break
    window = evidence.source_window(item, segments)
    chunk_plan = None
    if window.get("reason") == "source_window_requires_reviewed_chunking":
        chunk_plan = evidence.chunk_source_window(item, segments)
        if chunk_plan["status"] == "ready":
            window = chunk_plan["window"]
    if window["status"] != "ready":
        return None
    people, statements = load_name_evidence(supabase)
    streets = load_streets()
    meeting = supabase.table("meetings").select("meeting_date,meta").eq("id", item["meeting_id"]).single().execute().data
    dated = meeting["meeting_date"]
    memberships = []
    while True:
        rows = supabase.table("memberships").select("id,person_id,role,start_date,end_date").order("id").range(len(memberships), len(memberships) + 999).execute().data or []
        memberships.extend(rows)
        if len(rows) < 1000:
            break
    registry = {p["id"]: p["name"] for p in people}
    excluded = {registry[m["person_id"]] for m in memberships if m["person_id"] in registry and
                (not m.get("start_date") or m["start_date"] <= dated) and
                (not m.get("end_date") or m["end_date"] >= dated) and
                m.get("role", "").lower() in {"mayor", "councillor", "councilor", "staff"}}
    for role in ((meeting.get("meta") or {}).get("participant_roles") or {}).values():
        if role.get("classification") in {"government_staff", "committee_service"} and role.get("person_id") in registry:
            excluded.add(registry[role["person_id"]])
    fingerprint = evidence.digest({"title": item["title"], "window": window["fingerprint"], "people": people,
                                   "statements": statements, "streets": streets, "excluded": sorted(excluded), "version": evidence.VERSION})
    oldmeta = item.get("meta") or {}
    old = oldmeta.get("participation") or {}
    if old.get("validation", {}).get("input_fingerprint") == fingerprint:
        return old
    if oldmeta.get("participation_review_hold", {}).get("input_fingerprint") == fingerprint:
        return None
    try:
        if chunk_plan:
            parts = []
            for chunk in chunk_plan["chunks"]:
                proposal = evidence.generate(item, chunk, excluded)
                candidate = evidence.prepare_candidate(proposal, window=chunk, people=people, statement_names=statements,
                                                       streets=streets, excluded_names=excluded)
                checked = evidence.review(item, chunk, candidate, excluded)
                if not evidence.review_passed(checked, candidate):
                    raise ValueError("independent_chunk_review_rejected: " + "; ".join(checked["issues"]))
                parts.append({"candidate": candidate, "review": checked})
            result = evidence.merge_reviewed_chunks(chunk_plan, parts)
            review = {"all_chunk_reviews_passed": True, "chunk_count": len(parts)}
        else:
            proposal = evidence.generate(item, window, excluded)
            result = evidence.prepare_candidate(proposal, window=window, people=people, statement_names=statements,
                                                streets=streets, excluded_names=excluded)
            review = evidence.review(item, window, result, excluded)
            if not evidence.review_passed(review, result):
                raise ValueError("independent_source_review_rejected: " + "; ".join(review["issues"]))
    except ValueError as error:
        if not dry_run:
            meta = dict(oldmeta)
            reason = str(error).split(":", 1)[0]
            if not re.fullmatch(r"[a-z_]+", reason):
                reason = "source_review_rejected"
            meta["participation_review_hold"] = {"version": evidence.VERSION, "input_fingerprint": fingerprint,
                                                  "reason": reason, "details_sha256": evidence.digest(str(error))}
            supabase.rpc("apply_public_participation_summary", {"p_item_id": agenda_item_id, "p_expected_item": item,
                         "p_expected_segments": segments, "p_after_meta": meta}).execute()
        return None
    result["validation"]["input_fingerprint"] = fingerprint
    result["validation"]["independent_review"] = review
    if not dry_run:
        meta = dict(oldmeta)
        meta["participation"] = result
        meta["participation_version"] = PARTICIPATION_VERSION
        meta.pop("participation_review_hold", None)
        if not supabase.rpc("apply_public_participation_summary", {"p_item_id": agenda_item_id, "p_expected_item": item,
                            "p_expected_segments": segments, "p_after_meta": meta}).execute().data:
            return None
    return result
