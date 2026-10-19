"""Story links between matters, and mentions in mixed-topic agenda items.

Merging is for duplicates. Many matters are distinct steps of one initiative
(a notice of motion, an options report, a procurement scope, then the bylaw),
and showing the bylaw alone makes it look like the subject came out of nowhere.

- related_matter: two matters are steps of the same policy, program or project.
- mention: a mixed-topic item (notice of motion, presentation, delegation,
  public participation, correspondence) discussed a matter.

Candidates come from embeddings of the matters' plain-English summaries (titles
are too terse to compare); the Decisions API answers one yes/no question per
candidate, so an item can mention several matters.
"""
from __future__ import annotations

import re
from datetime import date

import numpy as np
from supabase import Client

from pipeline import decisions
from pipeline.embeddings import get_embedding_client

RELATED_SIM = 0.55
MENTION_SIM = 0.45
TOP_K = 5
MIN_PROBABILITY = 0.7
MAX_YEARS_APART = 4
MIXED_ITEM = re.compile(
    r"notice of motion|presentation|delegation|public participation|correspondence|petition|"
    r"question period|public input|mayor'?s report|council(?:lor)? reports?",
    re.I,
)


def _paginate(build, page: int = 1000) -> list[dict]:
    rows, start = [], 0
    while True:
        chunk = build().range(start, start + page - 1).execute().data or []
        rows.extend(chunk)
        if len(chunk) < page:
            return rows
        start += page


def _years_apart(a: str | None, b: str | None) -> float:
    try:
        return abs((date.fromisoformat(str(a)[:10]) - date.fromisoformat(str(b)[:10])).days) / 365.25
    except (TypeError, ValueError):
        return 0.0


def _matter_text(m: dict) -> str:
    meta = m.get("meta") or {}
    return f"{meta.get('display_title') or m['title']}. {m.get('plain_english_summary') or ''}".strip()


def _embed(texts: list[str]) -> np.ndarray:
    client = get_embedding_client()
    vecs: list[list[float]] = []
    for start in range(0, len(texts), 100):
        vecs.extend(client.embed_batch(texts[start : start + 100]))
    mat = np.array(vecs, dtype=np.float32)
    return mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)


def load_matters(supabase: Client, since: str | None) -> list[dict]:
    def q():
        query = (
            supabase.table("matters")
            .select("id, title, plain_english_summary, meta, first_seen, last_seen")
            .is_("meta->>canonical_matter_id", "null")
            .not_.is_("plain_english_summary", "null")
            .order("id")
        )
        return query.gte("last_seen", since) if since else query

    return _paginate(q)


def link_related(supabase: Client, matters: list[dict], vecs: np.ndarray, *, dry_run: bool = False) -> list[dict]:
    sims = vecs @ vecs.T
    pairs: set[tuple[int, int]] = set()
    for i in range(len(matters)):
        order = np.argsort(-sims[i])
        picked = 0
        for j in order:
            if j == i or sims[i, j] < RELATED_SIM or picked >= TOP_K:
                if sims[i, j] < RELATED_SIM:
                    break
                continue
            if _years_apart(matters[i]["first_seen"], matters[j]["first_seen"]) > MAX_YEARS_APART:
                continue
            pairs.add((min(i, j), max(i, j)))
            picked += 1

    def describe(m: dict) -> str:
        meta = m.get("meta") or {}
        return (
            f"{meta.get('display_title') or m['title']} ({m.get('first_seen')} to {m.get('last_seen')}): "
            f"{m.get('plain_english_summary') or ''} Latest: {meta.get('status_line') or '-'}"
        )

    question = {
        "type": "predicate",
        "name": "same_initiative",
        "instructions": "Are A and B steps of the same specific policy, program or project in this city — for example "
                        "a notice of motion, the options report it asked for, a procurement scope, and the bylaw that "
                        "implements it? Merely sharing a broad topic (housing, parks, traffic) is NOT enough, and "
                        "two different properties or applications are never the same initiative.",
    }
    pair_list = sorted(pairs)
    jobs = [(f"A: {describe(matters[i])}\n\nB: {describe(matters[j])}", [question]) for i, j in pair_list]
    links = []
    for start in range(0, len(jobs), 200):
        for (i, j), res in zip(pair_list[start : start + 200], decisions.decide_many(jobs[start : start + 200])):
            if isinstance(res, Exception):
                continue
            ans = res.get("same_initiative")
            prob = getattr(ans, "probability", 0) or 0
            if prob >= MIN_PROBABILITY:
                links.append(
                    {"matter_id": matters[i]["id"], "related_matter_id": matters[j]["id"], "kind": "related_matter", "confidence": prob}
                )
        print(f"  [Links] related {min(start + 200, len(jobs))}/{len(jobs)} — {len(links)} linked")
    if not dry_run:
        for link in links:
            try:
                supabase.table("matter_links").insert(link).execute()
            except Exception:
                pass  # already linked (unique pair index)
    return links


def link_mentions(supabase: Client, matters: list[dict], vecs: np.ndarray, since: str | None, *, dry_run: bool = False) -> list[dict]:
    def q():
        query = (
            supabase.table("agenda_items")
            .select("id, title, plain_english_summary, meetings!inner(meeting_date)")
            .not_.is_("plain_english_summary", "null")
            .order("id")
        )
        return query.gte("meetings.meeting_date", since) if since else query

    items = [it for it in _paginate(q) if MIXED_ITEM.search(it.get("title") or "")]
    if not items:
        return []
    item_vecs = _embed([f"{it['title']}. {it['plain_english_summary']}" for it in items])
    sims = item_vecs @ vecs.T
    jobs, meta = [], []
    for i, it in enumerate(items):
        cands = [j for j in np.argsort(-sims[i])[:TOP_K] if sims[i, j] >= MENTION_SIM]
        cands = [j for j in cands if _years_apart(it["meetings"]["meeting_date"], matters[j]["last_seen"]) <= 2]
        if not cands:
            continue
        questions = [
            {
                "type": "predicate",
                "name": f"m{matters[j]['id']}",
                "instructions": f"Does this agenda item discuss this specific matter: "
                                f"\"{(matters[j].get('meta') or {}).get('display_title') or matters[j]['title']}\" — "
                                f"{(matters[j].get('plain_english_summary') or '')[:300]}? A passing mention of the same broad topic is not enough.",
            }
            for j in cands
        ]
        jobs.append((f"AGENDA ITEM ({it['meetings']['meeting_date']}): {it['title']}\n{it['plain_english_summary']}", questions))
        meta.append(it)
    links = []
    for start in range(0, len(jobs), 200):
        for it, res in zip(meta[start : start + 200], decisions.decide_many(jobs[start : start + 200])):
            if isinstance(res, Exception):
                continue
            for name, ans in res.items():
                prob = getattr(ans, "probability", 0) or 0
                if prob >= MIN_PROBABILITY:
                    links.append({"matter_id": int(name[1:]), "agenda_item_id": it["id"], "kind": "mention", "confidence": prob})
        print(f"  [Links] mentions {min(start + 200, len(jobs))}/{len(jobs)} — {len(links)} linked")
    if not dry_run:
        for link in links:
            try:
                supabase.table("matter_links").insert(link).execute()
            except Exception:
                pass
    return links


def build_links(supabase: Client, *, since: str | None = None, dry_run: bool = False) -> dict:
    matters = load_matters(supabase, since)
    print(f"  [Links] {len(matters)} summarized matters")
    if len(matters) < 2:
        return {"related": 0, "mentions": 0}
    vecs = _embed([_matter_text(m) for m in matters])
    related = link_related(supabase, matters, vecs, dry_run=dry_run)
    mentions = link_mentions(supabase, matters, vecs, since, dry_run=dry_run)
    return {"related": related, "mentions": mentions}
