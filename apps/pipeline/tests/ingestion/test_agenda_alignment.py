from pipeline.ingestion.agenda_alignment import (
    Candidate,
    FIXED_SCORE,
    ai_fill_gaps,
    align_items,
    assign_monotonic,
    build_windows,
    normalize,
    split_sentences,
)


def seg(start, text, end=None, **kw):
    return {"start_time": start, "end_time": end if end is not None else start + 5, "text_content": text, **kw}


def item(id, order, title, start=None, end=None):
    return {"id": id, "item_order": order, "title": title, "discussion_start_time": start, "discussion_end_time": end}


# --- normalisation ---------------------------------------------------------

def test_normalize_spoken_numbers():
    assert "item 5" in normalize("Moving on to item five")
    assert "10.1" in normalize("ten point one, bylaw number")
    assert "2170" in normalize("bylaw number two one seven zero")
    assert "21" in normalize("item twenty-one")


# --- monotonic assignment --------------------------------------------------

def test_assign_monotonic_drops_out_of_order_mention():
    # Item 2 is mentioned early (a public speaker) with a lower score and announced later.
    cands = [
        [Candidate(100, 4.0, "announcement")],
        [Candidate(50, 3.0, "title_match"), Candidate(400, 3.5, "announcement")],
        [Candidate(300, 4.0, "announcement")],
    ]
    chosen = assign_monotonic(cands)
    # 50 is before item 1; 400 is after item 3. Best chain keeps items 1 and 3 and drops item 2.
    assert [c.time if c else None for c in chosen] == [100, None, 300]


def test_assign_monotonic_prefers_higher_total_score():
    cands = [
        [Candidate(500, 2.5, "title_match")],  # stray late mention
        [Candidate(200, 4.0, "announcement")],
        [Candidate(300, 4.0, "announcement")],
    ]
    chosen = assign_monotonic(cands)
    assert [c.time if c else None for c in chosen] == [None, 200, 300]


def test_assign_monotonic_respects_fixed_anchors_and_threshold():
    cands = [
        [Candidate(10, FIXED_SCORE, "existing")],
        [Candidate(5, 9.0, "announcement"), Candidate(40, 1.0, "title_match")],  # 5 breaks order, 40 below threshold
        [Candidate(90, FIXED_SCORE, "existing")],
    ]
    chosen = assign_monotonic(cands)
    assert chosen[0].time == 10 and chosen[2].time == 90
    assert chosen[1] is None


def test_assign_monotonic_ties_prefer_earlier():
    chosen = assign_monotonic([[Candidate(300, 3.0, "a"), Candidate(100, 3.0, "a")]])
    assert chosen[0].time == 100


def test_build_windows_non_overlapping():
    windows = build_windows([10, None, 50, 50, 120], 200)
    assert windows == [(10, 50), (None, None), (50, 50), (50, 120), (120, 200)]
    starts = [w[0] for w in windows if w[0] is not None]
    assert starts == sorted(starts)
    for (s1, e1), (s2, _) in zip([w for w in windows if w[0] is not None], [w for w in windows if w[0] is not None][1:]):
        assert e1 <= s2


# --- end-to-end on synthetic transcript ------------------------------------

def synthetic_meeting():
    items = [
        item(1, "1.", "CALL TO ORDER"),
        item(2, "2.", "APPROVAL OF THE AGENDA"),
        item(3, "3.", "PUBLIC PARTICIPATION"),
        item(4, "4.", "CONSENT AGENDA"),
        item(5, "5.1", "BYLAW NO. 2144 - Langford Zoning Bylaw, Amendment No. 705 (3405 Happy Valley Rd)"),
        item(6, "5.2", "Disaster Risk Reduction Grant - Misting Stations"),
        item(7, "6.", "ADJOURNMENT"),
    ]
    segments = [
        seg(10, "Good evening, I call this meeting to order."),
        seg(40, "Can I have an approval of the agenda, please?"),
        seg(60, "So moved. All in favour?"),
        seg(90, "Moving on to item three, public participation."),
        seg(120, "My name is Pat, I live on Goldstream and I am speaking to item 5.2 the misting stations."),
        seg(300, "Seeing none, public participation is closed."),
        seg(320, "We are on to item number four, the consent agenda."),
        seg(400, "Next we have 5.1, bylaw number 2144, Happy Valley Road."),
        seg(480, "I move that council adopt bylaw number 2144."),
        seg(600, "We're on to 5.2, the misting stations grant."),
        seg(900, "Thank you all."),
        seg(950, "Can I have a motion to adjourn?"),
    ]
    return items, segments


def test_align_items_end_to_end():
    items, segments = synthetic_meeting()
    ups = {u["id"]: u for u in align_items(items, segments, [])}
    starts = {i: round(ups[i]["start"]) for i in ups}
    assert starts[1] == 10
    assert 40 <= starts[2] < 45
    assert 90 <= starts[3] < 95
    assert 320 <= starts[4] < 325
    assert 400 <= starts[5] < 405
    assert 600 <= starts[6] < 605  # the public speaker's earlier "item 5.2" is ignored
    assert 950 <= starts[7] < 960
    # ends chain to the next start and windows don't overlap
    assert ups[3]["end"] == ups[4]["start"]
    ordered = [ups[i] for i in sorted(ups)]
    for a, b in zip(ordered, ordered[1:]):
        assert a["end"] <= b["start"]


def test_align_items_never_overwrites_existing_times():
    items, segments = synthetic_meeting()
    items[3] = {**items[3], "discussion_start_time": 330.0, "discussion_end_time": 390.0}
    ups = align_items(items, segments, [])
    assert 4 not in {u["id"] for u in ups}
    # existing time is an anchor: the item before it ends there
    by = {u["id"]: u for u in ups}
    assert by[3]["end"] == 330.0


def test_align_items_uses_segment_links_first():
    items, segments = synthetic_meeting()
    segments.append(seg(700, "Some discussion", agenda_item_id=6))
    segments[9] = {**segments[9], "agenda_item_id": 6}
    by = {u["id"]: u for u in align_items(items, segments, [])}
    assert by[6]["method"] == "segment_link" and by[6]["start"] == 600


def test_split_sentences_interpolates_times():
    parts = split_sentences([seg(100, "All in favour? Carried. We are on to item seven.", end=148)])
    assert [p["text_content"] for p in parts] == ["All in favour?", "Carried.", "We are on to item seven."]
    assert parts[0]["start_time"] == 100 and parts[1]["start_time"] > 100 and parts[2]["start_time"] > parts[1]["start_time"]


def test_ai_fill_gaps_only_between_anchors():
    items = [item(1, "1", "A"), item(2, "2", "B"), item(3, "3", "C")]
    segments = [seg(t, f"line {t}") for t in range(0, 400, 20)]
    asked = []

    def chooser(question, context, options):
        asked.append(options)
        return (options[3][0], 0.9)

    filled = ai_fill_gaps(items, [0.0, None, 300.0], segments, chooser=chooser)
    assert len(asked) == 1 and 1 in filled
    assert 0 < filled[1].time < 300
    # Unbounded gap (no later anchor) is not sent to the AI.
    assert ai_fill_gaps(items, [0.0, None, None], segments, chooser=chooser) == {}
