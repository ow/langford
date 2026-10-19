"""Link matters to the bylaw they are about (matters.bylaw_id).

A matter links to bylaw X when the first bylaw number in its title (falling
back to its identifier) is X, or is one of X's amending bylaws that has no
bylaw row of its own ("Elections Bylaw No. 1819, Amendment No. 2, Bylaw No.
2267" -> 1819). Numbers are read with ``find_bylaw_numbers``, which refuses
street addresses and bare years. Merged alias matters
(``meta.canonical_matter_id``) resolve to their canonical matter, so only the
canonical gets the link.

Pure planning; the caller writes.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.bylaw_numbers import find_bylaw_numbers, normalize_number, primary_bylaw_number


@dataclass
class PlannedLink:
    matter_id: int
    title: str
    slug: str | None
    via: str  # "direct" | "amendment <n>"
    matched_matter_ids: list[int]  # the matters whose text matched (aliases included)
    current_bylaw_id: int | None = None

    @property
    def conflict(self) -> bool:
        return self.current_bylaw_id is not None


def _match(matter: dict, number: str, amendments: set[str], numbers_with_rows: set[str]) -> str | None:
    primary = primary_bylaw_number(matter.get("title"), matter.get("identifier"))
    if primary is None:
        return None
    if primary == number:
        return "direct"
    if primary in amendments and primary not in numbers_with_rows:
        return f"amendment {primary}"
    return None


def plan_links(
    matters: list[dict],
    *,
    bylaw_id: int | None,
    bylaw_number: str,
    amendment_numbers: list[str] | None = None,
    numbers_with_rows: set[str] | None = None,
) -> list[PlannedLink]:
    """``matters`` rows need id, title, identifier, slug, meta, bylaw_id."""
    number = normalize_number(bylaw_number)
    amendments = {normalize_number(n) for n in (amendment_numbers or []) if normalize_number(n)}
    others = {normalize_number(n) for n in (numbers_with_rows or set())} - {number}
    by_id = {m["id"]: m for m in matters}

    planned: dict[int, PlannedLink] = {}
    for m in matters:
        via = _match(m, number, amendments, others)
        if not via:
            continue
        canonical_id = (m.get("meta") or {}).get("canonical_matter_id")
        target = by_id.get(canonical_id) if canonical_id else m
        if target is None:
            target = m
        link = planned.get(target["id"])
        if link is None:
            current = target.get("bylaw_id")
            link = PlannedLink(
                matter_id=target["id"],
                title=target.get("title") or "",
                slug=target.get("slug"),
                via=via,
                matched_matter_ids=[],
                current_bylaw_id=current if current not in (None, bylaw_id) else None,
            )
            planned[target["id"]] = link
        if m["id"] not in link.matched_matter_ids:
            link.matched_matter_ids.append(m["id"])
        if via == "direct":
            link.via = "direct"
    return sorted(planned.values(), key=lambda l: l.matter_id)


def mentions(matter: dict, number: str) -> bool:
    """True if the matter mentions the bylaw number anywhere (for reporting
    near-misses that the primary-reference rule skipped)."""
    text = f"{matter.get('identifier') or ''} | {matter.get('title') or ''}"
    return normalize_number(number) in find_bylaw_numbers(text)
