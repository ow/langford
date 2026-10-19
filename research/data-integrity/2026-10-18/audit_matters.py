"""Read-only matter repair proposal. Run with PYTHONPATH=apps/pipeline.

No apply mode: merges require an atomic, reviewed relink retaining source IDs.
Input can be an offline snapshot or live persisted source rows (admin credential).
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path
from pipeline.ingestion.matter_lifecycle import plan_lifecycle_updates
from pipeline.ingestion.matter_matching import matter_identifiers


def analyze(data):
    groups = defaultdict(list)
    for matter in data["matters"]:
        if (matter.get("meta") or {}).get("canonical_matter_id"):
            continue
        bylaws = sorted(p for p in matter_identifiers(matter) if p.startswith("Bylaw "))
        if bylaws:
            groups[(matter.get("municipality_id"), tuple(bylaws))].append(matter)
    duplicate_groups = []
    for (municipality, bylaws), matters in groups.items():
        if len(matters) < 2:
            continue
        ids = sorted(m["id"] for m in matters)
        links = [a for a in data["agenda_items"] if a.get("matter_id") in ids]
        duplicate_groups.append({"municipality_id": municipality, "bylaws": bylaws,
            "candidate_canonical_id": ids[0], "matter_ids": ids,
            "titles": [m["title"] for m in matters], "agenda_item_count": len(links),
            "hold": "Check full title/scope, other foreign keys and bylaw links before atomic relink; retain source IDs as aliases."})
    updates = plan_lifecycle_updates(data["matters"], data["agenda_items"], data["motions"], data["meetings"])
    return {"mode": "read-only", "counts": {"matters": len(data["matters"]),
        "active_before": sum(m.get("status") == "Active" for m in data["matters"]),
        "status_changes": len(updates), "duplicate_identity_groups": len(duplicate_groups),
        "duplicate_excess_records": sum(len(g["matter_ids"])-1 for g in duplicate_groups)},
        "lifecycle_updates": updates, "duplicate_groups": duplicate_groups}


def fetch_all(client, table, columns):
    rows = []
    while True:
        batch = client.table(table).select(columns).order("id").range(len(rows), len(rows)+999).execute().data
        rows.extend(batch)
        if len(batch) < 1000:
            return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.snapshot:
        data = json.loads(args.snapshot.read_text())
    else:
        from supabase import create_client
        from pipeline.config import SUPABASE_URL, SUPABASE_SECRET_KEY
        client = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)
        data = {table: fetch_all(client, table, columns) for table, columns in {
            "matters": "id,title,identifier,status,meta,municipality_id,bylaw_id",
            "agenda_items": "id,matter_id,meeting_id,title",
            "motions": "id,agenda_item_id,meeting_id,text_content,result,disposition",
            "meetings": "id,meeting_date"}.items()}
    result = analyze(data)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["counts"]))
