from pipeline.ingestion.summary_format import normalize_meeting_summary


def test_keeps_bullets_and_unifies_markers():
    raw = "```markdown\n* **Adopted** new fees (Bylaw 2275).\n\n1. Approved the budget.\n• Deferred the plan.\n```"
    assert normalize_meeting_summary(raw) == (
        "- Adopted new fees (Bylaw 2275).\n- Approved the budget.\n- Deferred the plan."
    )


def test_leaves_prose_unchanged():
    raw = "Council approved the plan. It also deferred a vote."
    assert normalize_meeting_summary(raw) == raw
