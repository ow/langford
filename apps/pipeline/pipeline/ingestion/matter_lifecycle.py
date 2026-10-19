"""Conservative matter lifecycle evidence from persisted substantive resolutions.

A carried motion is not completion. Only an explicit final action on *all* of a
matter's bylaw identifiers changes its status. This deliberately leaves general
projects, readings, committee recommendations and failed adoption unresolved.
"""
import re
from .matter_matching import bylaw_identifiers, parse_compound_identifier

RULE_VERSION = "bylaw-final-action-v1"


def lifecycle_evidence(matter: dict, motion: dict) -> dict | None:
    if (motion.get("result") or "").strip().upper() not in {"CARRIED", "PASSED", "ADOPTED"}:
        return None
    if (motion.get("disposition") or "").lower() in {"procedural", "amended", "amendment"}:
        return None
    identifiers = {p for p in parse_compound_identifier(matter.get("identifier")) if p.startswith("Bylaw ")}
    if not identifiers:
        identifiers = bylaw_identifiers(matter.get("title"))
    if not identifiers:
        return None
    text = " ".join((motion.get("text_content") or "").split())
    # Recommendations and conditional/future actions do not establish adoption.
    if re.search(r"\b(recommend\w*|subject to|if|once|prior to|upon|after|not adopt|not be adopted)\b", text, re.I):
        return None
    # Scope the final action to its clause, rather than any bylaw cited elsewhere.
    acted_on = set()
    status = None
    clauses = []
    for clause in re.split(r";|\bAND THAT\b", text, flags=re.I):
        # Read only the direct object of an explicit final Council action.
        # A resolution adopting a report *about* a bylaw is not bylaw adoption.
        action = re.search(r"\bCouncil\s+(adopt|repeal)\s+(.+)", clause, re.I)
        if not action:
            continue
        verb, direct_object = action.groups()
        direct_object = re.split(r"\b(?:and (?:further )?that|and direct|and authorize|and approve)\b", direct_object, maxsplit=1, flags=re.I)[0]
        first_bylaw = re.search(r"\bBylaws?\b", direct_object, re.I)
        if not first_bylaw:
            continue
        prefix = direct_object[:first_bylaw.start()]
        if re.search(r"\b(report|resolution|recommendation|pursuant|under|regarding|concerning|direct|prepare|draft|consider|refer|authorize|approve|with respect|in accordance|in relation)\b", prefix, re.I):
            continue
        # Reject a second verb that could attach an unrelated bylaw reference.
        if re.search(r"\b(?:and|to)\s+(?:direct|prepare|draft|consider|refer|authorize|approve|adopt|repeal)\b", direct_object, re.I):
            continue
        candidate = "Repealed" if verb.lower() == "repeal" else "Adopted"
        if status and candidate != status:
            return None
        object_ids = bylaw_identifiers(direct_object)
        status = candidate
        acted_on.update(object_ids)
        clauses.append({"action": verb.lower(), "direct_object": direct_object.strip(), "bylaws": sorted(object_ids)})
    if not status or not identifiers.issubset(acted_on):
        return None
    return {"status": status, "motion_id": motion.get("id"), "meeting_id": motion.get("meeting_id"),
            "rule": RULE_VERSION, "validation_status": "persisted_motion_only", "bylaws": sorted(identifiers), "source_text": text, "clauses": clauses}


def plan_lifecycle_updates(matters: list[dict], agenda_items: list[dict], motions: list[dict], meetings: list[dict]) -> list[dict]:
    by_id = {m["id"]: m for m in matters}
    dates = {m["id"]: m.get("meeting_date") for m in meetings}
    item_matters = {a["id"]: a.get("matter_id") for a in agenda_items}
    latest = {}
    for motion in motions:
        mid = item_matters.get(motion.get("agenda_item_id"))
        if mid not in by_id:
            continue
        evidence = lifecycle_evidence(by_id[mid], motion)
        if evidence:
            evidence["meeting_date"] = dates.get(motion.get("meeting_id"))
            previous = latest.get(mid)
            if not previous or (str(evidence["meeting_date"] or ""), evidence["motion_id"] or 0) > (str(previous["meeting_date"] or ""), previous["motion_id"] or 0):
                latest[mid] = evidence
    updates = []
    for mid, evidence in sorted(latest.items()):
        matter = by_id[mid]
        if matter.get("status") != evidence["status"]:
            updates.append({"id": mid, "title": matter["title"], "old_status": matter.get("status"),
                            "status": evidence["status"], "meta": {**(matter.get("meta") or {}), "lifecycle_evidence": evidence}})
    return updates


def refresh_meeting_matter_lifecycles(supabase, meeting_id: int):
    """Refresh affected matters from their complete history, even on old reingests."""
    items = supabase.table("agenda_items").select("id,matter_id").eq("meeting_id", meeting_id).execute().data
    for mid in sorted({item["matter_id"] for item in items if item.get("matter_id")}):
        matter = supabase.table("matters").select("id,title,identifier,status,meta").eq("id", mid).single().execute().data
        all_items = supabase.table("agenda_items").select("id,matter_id,meeting_id").eq("matter_id", mid).execute().data
        item_ids = [item["id"] for item in all_items]
        motions = supabase.table("motions").select("id,agenda_item_id,meeting_id,text_content,result,disposition").in_("agenda_item_id", item_ids).execute().data
        meeting_ids = list({item["meeting_id"] for item in all_items})
        meetings = supabase.table("meetings").select("id,meeting_date").in_("id", meeting_ids).execute().data
        for update in plan_lifecycle_updates([matter], all_items, motions, meetings):
            supabase.table("matters").update({"status": update["status"], "meta": update["meta"]}).eq("id", mid).execute()
