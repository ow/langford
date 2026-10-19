"""Read-only census of native outcome markers outside the canonical parser.

Outcome markers are discovery leads, not certified motions. In particular a
main motion can be voted on after an amendment without a second MOVED BY line.
This audit deliberately reports those cases without creating database rows.
"""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re

from pipeline.ingestion.official_ballots import html_minutes_text

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
INVENTORY = OUT / "canonical-official-motion-inventory.json"
CACHE = Path("/private/tmp/remaining-source-reconciliation")
inventory = json.loads(INVENTORY.read_text())
outcome_pattern = re.compile(
    r"(?im)^[ \t]*(?:Motion[ \t]+)?"
    r"(NOT CARRIED|CARRIED(?:[ \t]+UNANIMOUSLY)?|DEFEATED|WITHDRAWN|TABLED)\b[^\n]*"
)
mover_pattern = re.compile(r"(?im)^[ \t]*MOVED[ \t]+BY\b\s*[:;]?")
records = []
for source in inventory["sources"]:
    mid = source["meeting_id"]
    if source.get("error"):
        records.append({"meeting_id": mid, "status": "source_unavailable", "source_error": source["error"]})
        continue
    path = ROOT / source["source_file"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == source["source_sha256"]
    if source["source_format"] == "official_html_structural":
        raw = html_minutes_text(path)
    else:
        raw = (CACHE / (source["source_sha256"] + ".txt")).read_text()
    assert hashlib.sha256(raw.encode()).hexdigest() == source["native_text_sha256"]
    text = "\n".join(
        line for line in raw.splitlines()
        if not re.match(r"^\s*Minutes of[^\n]*$", line, re.I)
        and not re.match(r"^\s*\d+\s*$", line)
    ).replace("\f", "\n")
    movers = list(mover_pattern.finditer(text))
    outcomes = list(outcome_pattern.finditer(text))
    intervals = [(m.start(), movers[i + 1].start() if i + 1 < len(movers) else len(text)) for i, m in enumerate(movers)]
    issues = []
    for hit in outcomes:
        containing = [i for i, (start, end) in enumerate(intervals) if start <= hit.start() < end]
        if not containing:
            reason = "outcome_without_preceding_moved_by"
        else:
            start, end = intervals[containing[0]]
            earlier = [o for o in outcomes if start <= o.start() < hit.start()]
            if not earlier:
                continue
            reason = "additional_outcome_in_one_mover_block"
        issues.append({
            "status": reason,
            "outcome": hit[1],
            "native_offset": hit.start(),
            "source_context": text[max(0, hit.start() - 850): min(len(text), hit.end() + 300)],
        })
    records.append({
        "meeting_id": mid, "source_file": source["source_file"],
        "source_sha256": source["source_sha256"], "source_url": source["source_url"],
        "status": "native_marker_census", "moved_by_markers": len(movers),
        "outcome_markers": len(outcomes), "canonical_decisions": source["formal_decisions"],
        "issues": issues,
    })
summary = {
    "source_meetings": len(records),
    "source_errors": sum(r["status"] == "source_unavailable" for r in records),
    "native_outcome_markers": sum(r.get("outcome_markers", 0) for r in records),
    "canonical_decisions": sum(r.get("canonical_decisions", 0) for r in records),
    "unparsed_marker_leads": dict(Counter(i["status"] for r in records for i in r.get("issues", []))),
    "marker_leads_are_not_certified_new_motions": True,
    "database_writes": 0,
}
result = {
    "at": datetime.now(timezone.utc).isoformat(), "summary": summary,
    "inventory_sha256": hashlib.sha256(INVENTORY.read_bytes()).hexdigest(),
    "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "sources": records,
}
(OUT / "native-decision-boundary-audit.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(summary, indent=2))
