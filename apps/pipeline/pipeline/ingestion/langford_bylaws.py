"""Ingest Langford bylaws: PDF -> bylaws row + bylaw_chunks, then link matters.

Upserts by (municipality_id, bylaw_number). Nothing is written without
``--write``; without it the record and the matter-link plan are printed.

    # one bylaw, dry run (downloads the PDF and calls the AI, writes nothing)
    uv run python -m pipeline.ingestion.langford_bylaws --bylaw 1819 --link
    # write it
    uv run python -m pipeline.ingestion.langford_bylaws --bylaw 1819 --link --write
"""

from __future__ import annotations

import argparse
import os
import re
import sys

from pydantic import BaseModel, Field

from pipeline import ai
from pipeline.bylaw_numbers import (
    adoption_year_from_text,
    amendments_from_consolidation,
    normalize_number,
    number_from_text,
)
from pipeline.ingestion.bylaw_matter_links import mentions, plan_links
from pipeline.ingestion.bylaw_text import chunk_text, extract_text_from_pdf
from pipeline.paths import get_municipality_archive_root
from pipeline.scrapers.langford_bylaws import BylawSource, download, fetch_sources

MUNICIPALITY_SLUG = "langford"

STATUS_IN_FORCE = "In force"
STATUS_AMENDED = "Amended"  # in force, as amended (a consolidation lists amendments)
STATUS_REPEALED = "Repealed"

SYSTEM = (
    "You explain municipal bylaws to residents of Langford, BC in plain, concrete English. "
    "Only state what the bylaw text says. Keep numbers, fees, distances and deadlines exactly as written. "
    "No legal advice, no speculation, no filler."
)


class BylawSummary(BaseModel):
    summary: str = Field(
        description="2-3 sentences: what this bylaw does for residents, in plain English. "
        "Lead with the practical effect, not 'This bylaw...'."
    )
    key_rules: list[str] = Field(
        description="3-6 short items (under 20 words each): the specific rules, fees, fines, "
        "limits or deadlines a resident is most likely to run into. Quote figures exactly."
    )
    who_it_affects: str = Field(description="One short sentence naming who this bylaw applies to.")


# ── derivation ───────────────────────────────────────────────────────────


def display_title(title: str) -> str:
    """'Elections (Bylaw No. 1819) – Consolidated' -> 'Elections Bylaw'."""
    t = re.sub(r"\s*\((?:bylaw\s*)?no\.?\s*\d+[^)]*\)", "", title, flags=re.IGNORECASE)
    t = re.sub(r"\s*[–-]\s*consolidated\b.*$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*\bconsolidated\b.*$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*\bbylaw\s+no\.?\s*\d+(?:,\s*\d{4})?", " Bylaw", t, flags=re.IGNORECASE)
    t = " ".join(t.split()).strip(" –-,")
    if not re.search(r"\bbylaw\b", t, re.IGNORECASE):
        t = f"{t} Bylaw"
    return re.sub(r"\bBylaw\s+Bylaw\b", "Bylaw", t)


_ANNUAL = re.compile(r"\b(financial plan|tax rates?)\b", re.IGNORECASE)


def derive_status(src: BylawSource, text: str, amendments: list[dict]) -> str | None:
    """Only what the source supports; None when unsure.

    * On the City's directory of current bylaws -> in force (amended if the
      PDF is a consolidation listing amendments).
    * Annual financial-plan / tax-rate bylaws are listed historically, so the
      directory says nothing about whether they are "in force" -> None.
    * Media-library uploads (amendments, rezonings) -> None: an amending
      bylaw is spent once consolidated, and we can't tell from the upload.
    """
    head = (text or "")[:3000].lower()
    if "this bylaw is repealed" in head or re.search(r"\brepealed\s+by\s+bylaw", head):
        return STATUS_REPEALED
    if not src.listed_current or _ANNUAL.search(src.title):
        return None
    if amendments or src.consolidated:
        return STATUS_AMENDED
    return STATUS_IN_FORCE


def summarize(title: str, number: str | None, text: str, amendments: list[dict]) -> BylawSummary:
    amend = "; ".join(f"Bylaw {a['bylaw_number']} (adopted {a['adopted']})" for a in amendments) or "none listed"
    prompt = (
        f"Bylaw: {title}" + (f" (No. {number})" if number else "") + "\n"
        f"Amendments included in this version: {amend}\n\n"
        "Summarize this bylaw for residents.\n\n"
        f"BYLAW TEXT:\n{text[:60000]}"
    )
    return ai.json(prompt, stage="extraction", schema=BylawSummary, system=SYSTEM)


def build_record(src: BylawSource, path: str, *, archive_root: str, municipality_id: int, use_ai: bool = True) -> dict:
    text = extract_text_from_pdf(path) or ""
    if not text.strip():
        raise RuntimeError(f"No text layer in {path}")
    number = src.bylaw_number or number_from_text(text)
    amendments = amendments_from_consolidation(text)
    title = display_title(src.title)
    rel_path = os.path.join("archive", os.path.basename(archive_root.rstrip("/")), "Bylaws", os.path.basename(path))

    summary = summarize(title, number, text, amendments) if use_ai else None
    return {
        "municipality_id": municipality_id,
        "title": title,
        "bylaw_number": number,
        "year": src.year or adoption_year_from_text(text),
        "category": src.category,
        "status": derive_status(src, text, amendments),
        "source_url": src.source_url,
        "file_path": rel_path,
        "full_text": text,
        "plain_english_summary": format_summary(summary) if summary else None,
    }


def format_summary(s: BylawSummary) -> str:
    """Store the structured summary in the one text column the table has
    (no schema change). The first paragraph is the 2-3 sentence summary, which
    list rows and the matter card show; the web app's ``parseBylawSummary``
    reads the rest::

        <summary>

        Key rules:
        - <rule>

        Who it affects: <sentence>
    """
    parts = [" ".join(s.summary.split())]
    rules = [" ".join(r.split()) for r in s.key_rules if r.strip()]
    if rules:
        parts.append("Key rules:\n" + "\n".join(f"- {r}" for r in rules))
    if s.who_it_affects.strip():
        parts.append(f"Who it affects: {' '.join(s.who_it_affects.split())}")
    return "\n\n".join(parts)


# ── database ─────────────────────────────────────────────────────────────


def _client():
    from dotenv import load_dotenv
    from supabase import create_client

    load_dotenv()
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SECRET_KEY")
    if not url or not key:
        sys.exit("SUPABASE_URL and SUPABASE_SECRET_KEY must be set")
    return create_client(url, key)


def municipality_id_for(sb, slug: str = MUNICIPALITY_SLUG) -> int:
    rows = sb.table("municipalities").select("id").eq("slug", slug).execute().data
    if not rows:
        sys.exit(f"No municipality with slug {slug!r}")
    return rows[0]["id"]


def upsert_bylaw(sb, record: dict) -> tuple[int, int]:
    """Insert or update by (municipality_id, bylaw_number); replace chunks.
    Returns (bylaw_id, chunk_count)."""
    text = record["full_text"]
    doc_context = f"{record['title']}\n{record.get('plain_english_summary') or ''}\n{text[:1000]}"
    row = dict(record, embedding=ai.embed([doc_context])[0])

    q = sb.table("bylaws").select("id").eq("municipality_id", record["municipality_id"])
    q = q.eq("bylaw_number", record["bylaw_number"]) if record["bylaw_number"] else q.eq("file_path", record["file_path"])
    existing = q.execute().data
    if existing:
        bylaw_id = existing[0]["id"]
        sb.table("bylaws").update(row).eq("id", bylaw_id).execute()
        sb.table("bylaw_chunks").delete().eq("bylaw_id", bylaw_id).execute()
    else:
        bylaw_id = sb.table("bylaws").insert(row).execute().data[0]["id"]

    chunks = [c for c in chunk_text(text) if c.strip()]
    embeddings = ai.embed(chunks) if chunks else []
    rows = [
        {"bylaw_id": bylaw_id, "chunk_index": i, "text_content": c, "embedding": e}
        for i, (c, e) in enumerate(zip(chunks, embeddings))
    ]
    for i in range(0, len(rows), 50):
        sb.table("bylaw_chunks").insert(rows[i : i + 50]).execute()
    return bylaw_id, len(rows)


def load_matters(sb, municipality_id: int) -> list[dict]:
    out, off = [], 0
    while True:
        batch = (
            sb.table("matters")
            .select("id, title, identifier, slug, meta, bylaw_id")
            .eq("municipality_id", municipality_id)
            .order("id")
            .range(off, off + 999)
            .execute()
            .data
        )
        out.extend(batch)
        if len(batch) < 1000:
            return out
        off += 1000


def link_matters(sb, *, municipality_id: int, bylaw_id: int | None, number: str, amendments: list[dict], write: bool):
    matters = load_matters(sb, municipality_id)
    with_rows = {
        normalize_number(r["bylaw_number"])
        for r in sb.table("bylaws").select("bylaw_number").eq("municipality_id", municipality_id).execute().data
        if r.get("bylaw_number")
    }
    links = plan_links(
        matters,
        bylaw_id=bylaw_id,
        bylaw_number=number,
        amendment_numbers=[a["bylaw_number"] for a in amendments],
        numbers_with_rows=with_rows,
    )
    linked_ids = {mid for l in links for mid in l.matched_matter_ids}
    print(f"\nMatter links for Bylaw {number} ({'WRITE' if write else 'dry run'}):")
    for l in links:
        aliases = [i for i in l.matched_matter_ids if i != l.matter_id]
        flag = f"  [skip: already linked to bylaw {l.current_bylaw_id}]" if l.conflict else ""
        print(f"  matter {l.matter_id:>5}  {l.via:<16} {l.title[:80]}"
              + (f"  (via aliases {aliases})" if aliases else "") + flag)
    misses = [m for m in matters if m["id"] not in linked_ids and mentions(m, number)]
    for m in misses:
        print(f"  not linked {m['id']:>5}  (mentions {number}, not its main bylaw) {m['title'][:80]}")
    targets = [l.matter_id for l in links if not l.conflict]
    if write and bylaw_id and targets:
        sb.table("matters").update({"bylaw_id": bylaw_id}).in_("id", targets).execute()
        print(f"  -> linked {len(targets)} matter(s): {targets}")
    return links


# ── CLI ──────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None):
    p = argparse.ArgumentParser(description="Ingest Langford bylaws")
    p.add_argument("--bylaw", help="Only this bylaw number (required for now)")
    p.add_argument("--write", action="store_true", help="Write to the database (default: dry run)")
    p.add_argument("--link", action="store_true", help="Plan (and with --write, set) matters.bylaw_id")
    p.add_argument("--no-ai", action="store_true", help="Skip the AI summary (dry runs)")
    p.add_argument("--archive-dir", help="Municipality archive root (default: <repo>/archive/langford)")
    args = p.parse_args(argv)

    if not args.bylaw:
        sys.exit("Pass --bylaw <number>. Bulk ingestion is deliberately not enabled yet.")

    archive_root = args.archive_dir or os.environ.get("LANGFORD_ARCHIVE_ROOT") or get_municipality_archive_root(MUNICIPALITY_SLUG)
    sources = fetch_sources(args.bylaw)
    if not sources:
        sys.exit(f"No PDF found for Bylaw {args.bylaw} on the directory or in the media library")
    src = sources[0]
    print(f"Source: {src.title} <{src.source_url}> ({src.source})")
    path = download(src, os.path.join(archive_root, "Bylaws"))
    print(f"PDF: {path}")

    sb = _client()
    muni = municipality_id_for(sb)
    record = build_record(src, path, archive_root=archive_root, municipality_id=muni, use_ai=not args.no_ai)
    preview = {k: v for k, v in record.items() if k != "full_text"}
    preview["full_text_chars"] = len(record["full_text"])
    import json as _json

    print(_json.dumps(preview, indent=2, ensure_ascii=False))

    bylaw_id = None
    if args.write:
        bylaw_id, n_chunks = upsert_bylaw(sb, record)
        print(f"-> bylaws.id={bylaw_id}, {n_chunks} chunks")
    else:
        existing = (
            sb.table("bylaws").select("id").eq("municipality_id", muni).eq("bylaw_number", record["bylaw_number"]).execute().data
        )
        bylaw_id = existing[0]["id"] if existing else None

    if args.link and record["bylaw_number"]:
        link_matters(
            sb,
            municipality_id=muni,
            bylaw_id=bylaw_id,
            number=record["bylaw_number"],
            amendments=amendments_from_consolidation(record["full_text"]),
            write=args.write,
        )


if __name__ == "__main__":
    main()
