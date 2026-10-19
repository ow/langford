import datetime as dt

import pytest

from pipeline.bylaw_numbers import (
    adoption_year_from_text,
    amendments_from_consolidation,
    find_bylaw_numbers,
    normalize_number,
    number_from_text,
    parse_year,
    primary_bylaw_number,
)

TODAY = dt.date(2026, 10, 19)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Board of Variance (Bylaw No. 1413)", ["1413"]),
        ("Building Bylaw (Bylaw No. 1160, 2008) – Consolidated", ["1160"]),
        ("Soil Deposit and Removal Permit (Bylaw 1800)", ["1800"]),
        ("Community Standards Bylaw (No. 2255)", ["2255"]),
        ("Fees and Charges Bylaw No. 0113 – Consolidated", ["113"]),
        ("BYLAW NO. 2299", ["2299"]),
        ("Bylaw Nos. 2181 & 2233", ["2181", "2233"]),
        ("Bylaw Nos 2239 & 2212", ["2239", "2212"]),
        ("Bylaw Nos. 2255 and 2262", ["2255", "2262"]),
        ("Bylaw No. 1989; Bylaw No. 1990", ["1989", "1990"]),
        ("Langford Building Bylaw No.1160, Amendment No 8, 2016", ["1160"]),
        ("Elections Bylaw No. 1819, Amendment No. 2, Bylaw No. 2267, 2026 (Adoption)", ["1819", "2267"]),
        # "Omnibus No." / "Amendment No." are not bylaw numbers
        ("Langford Zoning Bylaw No. 300, Amendment No. 761 (Omnibus No. 68)", ["300"]),
        ("Langford Zoning Bylaw Amendment No. 562 (4365 West Shore Pkwy)", []),
        # the "No." is explicit, so a year-like number is still a bylaw number
        ("Roads Bylaw No. 2021", ["2021"]),
        ("Bylaw 2246", ["2246"]),
        ("Bylaw 1819 Elections CONSOLIDATED to May 19 2026", ["1819"]),
        ("Bylaw No 2233 Street Use Permit Application", ["2233"]),
        ("Bylaw No. 2246 | Road Closure (portion of Aldwynd Road)", ["2246"]),
    ],
)
def test_find_bylaw_numbers(text, expected):
    assert find_bylaw_numbers(text, today=TODAY) == expected


@pytest.mark.parametrize(
    "text",
    [
        # street addresses, not bylaw numbers
        "Notice of Rezoning Bylaw 1234 Goldstream Avenue Z25-0008",
        "Rezoning Bylaw 1029 Marwood Avenue",
        "Rezoning Bylaw 3084, 3088 Jacklin Rd",
        "Notice of Rezoning Bylaw 2614, 2616 Peatt Road",
        # bare year after "Bylaw"
        "Tax Rate Bylaw 2026",
        "Root Bylaw 2014",
        # filename dates
        "Bylaw Consideration Postcard 20250915",
        "Amendment No. 12",
        "",
        None,
    ],
)
def test_find_bylaw_numbers_rejects_false_positives(text):
    assert find_bylaw_numbers(text, today=TODAY) == []


def test_address_guard_keeps_real_number_before_address():
    text = "BYLAW NO. 2248 | Langford Zoning Bylaw No. 300, Amendment No. 750 (1234 Goldstream Avenue)"
    assert find_bylaw_numbers(text, today=TODAY) == ["2248", "300"]


def test_primary_bylaw_number_prefers_title():
    assert primary_bylaw_number("Election Bylaw No. 1819, Amendment No. 1", "BYLAW 2057") == "1819"
    assert primary_bylaw_number("Review of elections", "Bylaw No. 1819") == "1819"
    assert primary_bylaw_number("Rezoning 1234 Goldstream Avenue", "1234 Goldstream Avenue") is None


def test_parse_year():
    assert parse_year("Building Bylaw (Bylaw No. 1160, 2008) – Consolidated") == 2008
    assert parse_year("Freedom of Information Bylaw No. 1925, 2020") == 2020
    assert parse_year("Elections (Bylaw No. 1819) – Consolidated to May 19, 2026") is None
    assert parse_year("Tax Rate Bylaw 2026") is None


def test_normalize_number():
    assert normalize_number("0113") == "113"
    assert normalize_number("No. 1819") == "1819"
    assert normalize_number("") is None


CONSOLIDATION = """CONSOLIDATED
ELECTIONS BYLAW NO. 1819
List of Amendments
Consolidated for Convenience Only
Amendment
Bylaw Number
Date Adopted
Amendment #1 2022 (Elections Bylaw)
2057
May 16, 2022
Amendment #2 2026 (Elections Bylaw)
2267
May 19, 2026
City of Langford
BYLAW NO. 1819
...
READ A THIRD TIME THIS 4TH DAY OF FEBRUARY, 2019.
ADOPTED THIS 19TH DAY OF FEBRUARY, 2019.
"""


def test_consolidation_parsing():
    assert number_from_text(CONSOLIDATION) == "1819"
    assert adoption_year_from_text(CONSOLIDATION) == 2019
    assert amendments_from_consolidation(CONSOLIDATION) == [
        {"bylaw_number": "2057", "adopted": "May 16, 2022"},
        {"bylaw_number": "2267", "adopted": "May 19, 2026"},
    ]
    assert amendments_from_consolidation("BYLAW NO. 2239\nADOPTED THIS 16TH DAY OF MARCH, 2026") == []
