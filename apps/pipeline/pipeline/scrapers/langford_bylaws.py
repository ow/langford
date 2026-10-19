"""Langford bylaw sources.

Two sources, both plain WordPress (no bot protection):

1. The bylaws directory page — the City's list of current bylaws, one link
   per bylaw with the number in the link text ("Board of Variance (Bylaw No.
   1413)") and a ``categories`` attribute ("land-use, ").
2. The WordPress media API — every uploaded PDF whose title mentions
   "bylaw": amendment and rezoning bylaws mixed with notices, ads, postcards
   and permit forms, which are filtered out here.

The directory wins when both list the same number. Nothing here touches the
database; ``pipeline.ingestion.langford_bylaws`` does that.

    uv run python -m pipeline.scrapers.langford_bylaws --list
    uv run python -m pipeline.scrapers.langford_bylaws --bylaw 1819
"""

from __future__ import annotations

import argparse
import html
import os
import re
import time
from dataclasses import asdict, dataclass, field
from urllib.parse import unquote, urlparse

import requests

from pipeline import utils
from pipeline.bylaw_numbers import find_bylaw_numbers, normalize_number, parse_year

DIRECTORY_URL = "https://langford.ca/city-hall/bylaws-directory/"
MEDIA_API_URL = "https://langford.ca/wp-json/wp/v2/media"
USER_AGENT = "LangfordCivicRecords/1.0 (+https://github.com/; civic archive)"
TIMEOUT = 60

CATEGORY_LABELS = {
    "administration": "Administration",
    "business": "Business",
    "community-standards": "Community standards",
    "environmental": "Environment",
    "finance": "Finance",
    "land-use": "Land use",
    "services": "Services",
}

# Documents that mention a bylaw but are not one.
_NOT_A_BYLAW = re.compile(
    r"\b(application|form|faqs?|log|summary sheet|atlas|flow chart|notice|postcard|"
    r"ph ad|ad|gazette|guidelines|evidence|policy|report|correspondence|submissions?|"
    r"public hearing|draft|jd|job description|posting|release|staff report|late submission)\b",
    re.IGNORECASE,
)

_DIRECTORY_LINK = re.compile(
    r'<a href="(?P<href>[^"]+)"[^>]*>\s*<div class="bylaw-cell[^"]*"\s+categories="(?P<cats>[^"]*)">\s*'
    r'<span class="bylaw-title">(?P<title>.*?)</span>',
    re.DOTALL,
)


@dataclass
class BylawSource:
    title: str
    source_url: str
    bylaw_number: str | None = None
    year: int | None = None
    categories: list[str] = field(default_factory=list)
    source: str = "directory"  # "directory" | "media"
    listed_current: bool = False  # on the City's directory of current bylaws
    consolidated: bool = False
    uploaded: str | None = None  # media date (ISO)
    # True when the number came only from a loose "Bylaw 2019" title read
    # (could be a year); bulk ingestion keeps it only if the PDF header agrees.
    number_unconfirmed: bool = False

    @property
    def category(self) -> str | None:
        labels = [CATEGORY_LABELS.get(c, c.replace("-", " ").capitalize()) for c in self.categories]
        return ", ".join(labels) if labels else None

    @property
    def filename(self) -> str:
        name = os.path.basename(unquote(urlparse(self.source_url).path)) or "bylaw.pdf"
        prefix = f"Bylaw {self.bylaw_number} - " if self.bylaw_number else ""
        return utils.sanitize_filename(prefix + name)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category
        return d


def _filename_stem(url: str) -> str:
    stem = os.path.splitext(os.path.basename(unquote(urlparse(url).path)))[0]
    return re.sub(r"[-_]+", " ", stem)


def number_from_filename(url: str) -> str | None:
    """'1160-Building-Bylaw-2008-...' -> '1160'; 'Tree-Protection-Bylaw-No.-2269' -> '2269'."""
    stem = _filename_stem(url)
    lead = re.match(r"^(\d{3,4})\s+.*\bbylaw\b", stem, re.IGNORECASE)
    if lead:
        return normalize_number(lead.group(1))
    nums = find_bylaw_numbers(stem)
    return nums[0] if nums else None


_LOOSE_TITLE_NUMBER = re.compile(r"\bby-?law\s*(?:no\.?\s*)?(\d{3,4})\b(?![.,]\d)", re.IGNORECASE)


def loose_title_number(title: str) -> str | None:
    """'Bylaw 2019 Z22-0025' -> '2019'. ``find_bylaw_numbers`` refuses bare
    year-like numbers ("Tax Rate Bylaw 2026"); this does not, so callers must
    confirm the result against the PDF header."""
    from pipeline.bylaw_numbers import _is_address

    for m in _LOOSE_TITLE_NUMBER.finditer(title or ""):
        if not _is_address(title, m.end()):
            return normalize_number(m.group(1))
    return None


def is_bylaw_document(title: str) -> bool:
    return bool(re.search(r"\bby-?laws?\b", title, re.IGNORECASE)) and not _NOT_A_BYLAW.search(title)


def clean_title(title: str) -> str:
    title = html.unescape(title)
    title = re.sub(r"\s*\((?:\d+)\)\s*$", "", title)  # "SIGNED (1)"
    title = re.sub(r"\s*[–-]\s*SIGNED\b.*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^\d+_", "", title)  # "2_Bylaw 2229"
    title = re.sub(r"^\d{8}\s*[–-]\s*", "", title)  # "20250616 – Bylaw No. 2227"
    return " ".join(title.split())


def _source_from(title: str, url: str, *, cats: list[str], source: str, uploaded: str | None = None) -> BylawSource:
    nums = find_bylaw_numbers(title)
    number = nums[0] if nums else number_from_filename(url)
    consolidated = bool(re.search(r"consolidat", f"{title} {url}", re.IGNORECASE))
    return BylawSource(
        title=title,
        source_url=url,
        bylaw_number=number,
        year=parse_year(title),
        categories=cats,
        source=source,
        listed_current=source == "directory",
        consolidated=consolidated,
        uploaded=uploaded,
    )


def parse_directory(page_html: str) -> list[BylawSource]:
    out: list[BylawSource] = []
    for m in _DIRECTORY_LINK.finditer(page_html):
        href = m.group("href").strip()
        title = clean_title(m.group("title"))
        if not href.lower().endswith(".pdf") or not is_bylaw_document(title):
            continue
        cats = [c.strip() for c in m.group("cats").split(",") if c.strip()]
        out.append(_source_from(title, href, cats=cats, source="directory"))
    return out


def parse_media(items: list[dict]) -> list[BylawSource]:
    out: list[BylawSource] = []
    for item in items:
        url = item.get("source_url") or ""
        title = clean_title((item.get("title") or {}).get("rendered") or _filename_stem(url))
        if not url.lower().endswith(".pdf") or not is_bylaw_document(title):
            continue
        src = _source_from(title, url, cats=[], source="media", uploaded=(item.get("date") or "")[:10] or None)
        if not src.bylaw_number and not re.search(r"\b(?:tax rates?|financial plan)\b", title, re.IGNORECASE):
            src.bylaw_number = loose_title_number(title)
            src.number_unconfirmed = bool(src.bylaw_number)
        if src.bylaw_number:  # an unnumbered media upload can't be matched to anything
            out.append(src)
    return out


def merge_sources(directory: list[BylawSource], media: list[BylawSource]) -> list[BylawSource]:
    """One entry per bylaw number: directory first, else the newest media upload
    (consolidations preferred). Unnumbered directory entries are kept as-is."""
    by_number: dict[str, BylawSource] = {}
    unnumbered: list[BylawSource] = []
    for src in directory:
        if not src.bylaw_number:
            unnumbered.append(src)
        elif src.bylaw_number not in by_number:
            by_number[src.bylaw_number] = src
    ranked = sorted(media, key=lambda s: (s.consolidated, s.uploaded or ""), reverse=True)
    for src in ranked:
        if src.bylaw_number not in by_number:
            by_number[src.bylaw_number] = src
    return list(by_number.values()) + unnumbered


def _get(url: str, **kw) -> requests.Response:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, **kw)
    resp.raise_for_status()
    return resp


def fetch_directory() -> list[BylawSource]:
    return parse_directory(_get(DIRECTORY_URL).text)


def fetch_media(search: str = "bylaw") -> list[BylawSource]:
    return parse_media(fetch_media_items(search))


def fetch_media_items(search: str = "bylaw") -> list[dict]:
    items: list[dict] = []
    page = 1
    while True:
        resp = _get(
            MEDIA_API_URL,
            params={
                "search": search,
                "mime_type": "application/pdf",
                "per_page": 100,
                "page": page,
                "_fields": "id,date,title,source_url",
            },
        )
        batch = resp.json()
        items.extend(batch)
        if page >= int(resp.headers.get("X-WP-TotalPages", "1")) or not batch:
            break
        page += 1
    return items


def fetch_sources(bylaw: str | None = None) -> list[BylawSource]:
    directory = fetch_directory()
    number = normalize_number(bylaw) if bylaw else None
    if number and any(s.bylaw_number == number for s in directory):
        return [s for s in directory if s.bylaw_number == number][:1]
    media = fetch_media(number or "bylaw")
    merged = merge_sources(directory, media)
    if number:
        return [s for s in merged if s.bylaw_number == number]
    return merged


def download(src: BylawSource, folder: str, name: str | None = None, *, delay: float = 0.0) -> str:
    """Download the PDF into ``folder`` (skips if present). Returns the path.
    ``delay`` seconds are slept before a real download (politeness)."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name or src.filename)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    if delay:
        time.sleep(delay)
    resp = _get(src.source_url, stream=True)
    tmp = path + ".part"
    with open(tmp, "wb") as fh:
        for chunk in resp.iter_content(chunk_size=65536):
            fh.write(chunk)
    os.replace(tmp, path)
    return path


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="List Langford bylaw PDFs")
    parser.add_argument("--bylaw", help="Only this bylaw number")
    parser.add_argument("--list", action="store_true", help="Print every source found")
    args = parser.parse_args(argv)
    sources = fetch_sources(args.bylaw)
    for s in sources:
        print(f"{s.bylaw_number or '-':>5}  {s.source:<9} {s.category or '':<22} {s.title}  <{s.source_url}>")
    print(f"{len(sources)} bylaw source(s)")


if __name__ == "__main__":
    main()
