"""Bylaw-number parsing shared by the bylaw scrapers, ingestion and matter linking.

Pure functions, no I/O. The hard part is not finding digits next to the word
"bylaw" but refusing the ones that are not bylaw numbers:

* street addresses  ("Rezoning Bylaw 1234 Goldstream Avenue")
* years             ("Tax Rate Bylaw 2026", "Bylaw No. 1925, 2020")
* dates in filenames ("Consolidated-to-20260601")
"""

from __future__ import annotations

import datetime as _dt
import re

# Words that, right after a number, mean the number is a street address.
STREET_WORDS = (
    "avenue|ave|road|rd|street|st|drive|dr|way|place|pl|crescent|cres|lane|ln|"
    "boulevard|blvd|court|ct|terrace|terr|parkway|pkwy|highway|hwy|close|trail|"
    "circle|gate|grove|heights|hts|view|ridge|rise|square|sq|mews|walk|loop"
)
# After the number: optional further house numbers ("3084, 3088"), then a
# capitalised street name and a street word ("Goldstream Avenue", "Jacklin Rd").
_STREET_AFTER = re.compile(
    rf"^(?:[\s,/&-]+\d+[A-Za-z]?)*\s+(?:[A-Z][a-z'.-]+\s+){{1,3}}(?i:{STREET_WORDS})\b"
)

# "Bylaw No. 1413", "Bylaw No 2233", "Bylaw 1800", "BYLAW NO. 2299",
# "Bylaw Nos. 2181 & 2233", "(No. 2255)", "Bylaw No.1160".
_REF = re.compile(
    r"\b(?:by-?law\s*(?P<nos>nos?\.?|numbers?|#)?|(?<![a-z])(?P<bare>nos?\.)(?=\s*\d))\s*"
    r"(?P<num>\d{1,4})(?!\d)(?![.,]\d)",
    re.IGNORECASE,
)
_LIST_TAIL = re.compile(r"^\s*(?:,|&|and)\s*(?:no\.?\s*)?(\d{1,4})(?!\d)", re.IGNORECASE)

_YEAR_AFTER_COMMA = re.compile(r"^\s*,\s*((?:19|20)\d{2})\b")


def normalize_number(raw: str | int | None) -> str | None:
    """'0113' -> '113'; None/'' -> None."""
    if raw is None:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if not digits:
        return None
    return str(int(digits))


def _plausible_year(n: int, today: _dt.date | None = None) -> bool:
    year = (today or _dt.date.today()).year
    return 1990 <= n <= year + 1


def _is_address(text: str, end: int) -> bool:
    return bool(_STREET_AFTER.match(text[end:end + 80]))


def find_bylaw_numbers(text: str | None, *, today: _dt.date | None = None) -> list[str]:
    """Every bylaw number referenced in ``text``, in order of first mention.

    A bare "Bylaw NNNN" (no "No.") that looks like a recent year is treated as
    a year ("Tax Rate Bylaw 2026"); with "No." it is trusted ("Bylaw No. 2021").
    Numbers followed by a street name are addresses and are skipped.
    """
    if not text:
        return []
    found: list[str] = []

    def add(raw: str):
        n = normalize_number(raw)
        if n and n != "0" and n not in found:
            found.append(n)

    for m in _REF.finditer(text):
        num = m.group("num")
        has_no = bool(m.group("nos") or m.group("bare"))
        prefix = text[max(0, m.start() - 12):m.start()]
        if m.group("bare") and not re.search(r"(?:by-?law\s*\(?|\()\s*$", prefix, re.I):
            # A lone "No. 12" ("Amendment No. 12", "Omnibus No. 68") is not a
            # bylaw number; "Community Standards Bylaw (No. 2255)" is.
            continue
        if _is_address(text, m.end()):
            continue
        if not has_no and _plausible_year(int(num), today) and len(num) == 4:
            continue
        add(num)
        if m.group("nos") and m.group("nos").lower().startswith("nos"):
            pos = m.end()
            while True:
                t = _LIST_TAIL.match(text[pos:])
                if not t:
                    break
                if not _is_address(text, pos + t.end()):
                    add(t.group(1))
                pos += t.end()
    return found


def primary_bylaw_number(title: str | None, identifier: str | None = None) -> str | None:
    """The bylaw a matter is principally about: first mention in the title,
    falling back to the identifier."""
    for source in (title, identifier):
        nums = find_bylaw_numbers(source)
        if nums:
            return nums[0]
    return None


def parse_year(text: str | None) -> int | None:
    """Enactment year from a title like "Building Bylaw (Bylaw No. 1160, 2008)"
    or "Freedom of Information Bylaw No. 1925, 2020". Ignores "consolidated to"
    dates and bare years elsewhere in the string."""
    if not text:
        return None
    for m in _REF.finditer(text):
        y = _YEAR_AFTER_COMMA.match(text[m.end():])
        if y:
            return int(y.group(1))
    return None


_ADOPTED = re.compile(
    r"ADOPTED\s+(?:THIS|ON|the)?\s*[\w\s]{0,30}?(?:DAY\s+OF\s+)?[A-Z]+\s*,?\s*((?:19|20)\d{2})",
    re.IGNORECASE,
)


def adoption_year_from_text(text: str | None) -> int | None:
    """Year from the adoption line at the end of a bylaw ("ADOPTED THIS 19TH
    DAY OF FEBRUARY, 2019."). The last such line wins: consolidations repeat
    the amendment adoptions before the principal bylaw's own signature block,
    but the principal's adoption line closes the document."""
    if not text:
        return None
    hits = _ADOPTED.findall(text)
    return int(hits[-1]) if hits else None


_HEADER_NUMBER = re.compile(r"\bBY-?LAW\s+NO\.?\s*(\d{1,4})\b", re.IGNORECASE)


def number_from_text(text: str | None) -> str | None:
    """Bylaw number from the PDF header ("BYLAW NO. 1819"), first page only."""
    if not text:
        return None
    m = _HEADER_NUMBER.search(text[:4000])
    return normalize_number(m.group(1)) if m else None


_AMENDMENT_ROW = re.compile(
    r"Amendment\s*#?\s*\d+[^\n]*\n\s*(\d{3,4})\s*\n\s*([A-Z][a-z]+\.?\s+\d{1,2},\s*(?:19|20)\d{2})",
)


def amendments_from_consolidation(text: str | None) -> list[dict]:
    """Amending bylaws listed in a consolidation's "List of Amendments" table.

    Returns [{"bylaw_number": "2057", "adopted": "May 16, 2022"}, ...].
    """
    if not text or "consolidat" not in text[:3000].lower():
        return []
    out: list[dict] = []
    for m in _AMENDMENT_ROW.finditer(text[:6000]):
        n = normalize_number(m.group(1))
        if n and all(a["bylaw_number"] != n for a in out):
            out.append({"bylaw_number": n, "adopted": " ".join(m.group(2).split())})
    return out
