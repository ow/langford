"""Native minutes layout must preserve dates and account for every voter name."""
import fitz
import pytest

from pipeline.ingestion.official_ballots import load_official_minutes


PEOPLE = [
    {"id": 143, "name": "Stew Young"},
    {"id": 133, "name": "Denise Blackwell"},
    {"id": 134, "name": "Matt Sahlstrom"},
    {"id": 135, "name": "Lanny Seaton"},
    {"id": 136, "name": "Norma Stewart"},
    {"id": 137, "name": "Roger Wade"},
    {"id": 35, "name": "Lillian Szpak"},
]


def _native_source(tmp_path, date_line, roster, body=''):
    folder = tmp_path / "archive/meeting/Minutes"
    folder.mkdir(parents=True)
    source = folder / "Minutes.pdf"
    document = fitz.open()
    document.new_page().insert_text(
        (40, 40),
        "CITY OF LANGFORD\nMINUTES OF THE REGULAR MEETING OF COUNCIL\n"
        + date_line + " @ 5:30 p.m.\nPRESENT:\n" + roster
        + "\nATTENDING: Staff\n1. CALL TO ORDER\nThe Chair called the meeting to order.\n" + body,
        fontsize=9,
    )
    document.save(source)
    document.close()
    return load_official_minutes(
        {"archive_path": "archive/meeting", "meeting_date": "2020-07-20"},
        root=tmp_path, people=PEOPLE, cache_dir=tmp_path / "native-cache",
    )


@pytest.mark.parametrize(
    ("date_line", "expected"),
    [
        ("Monday, July 20^ 2020", "2020-07-20"),
        ("Monday, March 4t^ 2019", "2019-03-04"),
        ("Tuesday, September 3'^'', 2019", "2019-09-03"),
        ("Monday, November 7t\", 2016", "2016-11-07"),
        # A lost day digit must not be reconstructed from the catalogue date.
        ("Thursday, May 2V\\ 2020", None),
        ("Monday, July 21^ 2020", None),
        ("Monday, October 2019", None),
    ],
)
def test_native_pdf_header_date_preserves_digits_and_checks_noisy_ordinal_weekday(
    tmp_path, date_line, expected
):
    result = _native_source(
        tmp_path, date_line, "Mayor S. Young\nCouncillors: D. Blackwell, L. Szpak"
    )
    assert "error" not in result
    assert result["local_date"] == expected
    if expected is not None:
        assert result["source_date_evidence"]["method"] == "native_weekday_with_ordinal_ocr_noise"
        assert result["source_date_evidence"]["weekday_verified"] is True


@pytest.mark.parametrize(
    ("roster", "expected_ids"),
    [
        ("Mayors. Young     Councillor M. Sahlstrom - Remote\nCouncillor D. Blackwell     Councillor L. Szpak", {143, 134, 133, 35}),
        ("Councillor L. Szpak - Acting Mayor     Councillor D. Blackwell\nCouncillor M. Sahlstrom - Remote     Councillor R. Wade", {35, 133, 134, 137}),
        ("Mayor S. Young     Councillor N. Stewart\nCouncillor M. Sahlstrom-Remote     Councillor L. Szpak", {143, 136, 134, 35}),
        ("Mayor S. Young\nCouncillor D. Blackwell\nCouncillor X. Unknown", None),
        ("Mayor S. Young\nCouncillor D. Blackwell\nCouncillor X. Szpak", None),
    ],
)
def test_native_roster_roles_and_remote_suffixes_do_not_create_unknown_voters(
    tmp_path, roster, expected_ids
):
    result = _native_source(tmp_path, "Monday, July 20, 2020", roster)
    assert "error" not in result
    if expected_ids is None:
        assert result["roster_unknown"] or result["ambiguous_names"]
        assert 35 not in {p["id"] for p in result["present"]}
    else:
        assert result["roster_unknown"] == []
        assert result["ambiguous_names"] == []
        assert {p["id"] for p in result["present"]} == expected_ids


@pytest.mark.parametrize(
    ("header", "expected"),
    [("Monday, May 2\", 2016", "2016-05-02"), ("Monday, December Z\"'', 2019", None)],
)
def test_native_meeting_date_never_comes_from_a_prior_minutes_reference(tmp_path, header, expected):
    result = _native_source(
        tmp_path, header, "Mayor S. Young\nCouncillors: D. Blackwell, L. Szpak",
        body="3. ADOPTION OF MINUTES\nThat Council adopt the minutes of April 18, 2016.\n",
    )
    assert result['local_date'] == expected
