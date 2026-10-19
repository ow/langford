"""ai_usage sink: batching, flush, failure isolation, context labels."""

from unittest.mock import MagicMock

from pipeline.ai import usage
from pipeline.ai.usage import UsageRecord, usage_context
from pipeline.ai.usage_sink import SupabaseUsageSink, to_row


def _record(**kw):
    base = dict(stage="extraction", model="gpt-6-luna", operation="json", input_tokens=10,
                output_tokens=2, latency_ms=50, ok=True)
    base.update(kw)
    return UsageRecord(**base)


def _client():
    client = MagicMock()
    return client, client.table.return_value.insert


def test_batches_by_size_and_flushes_the_rest():
    client, insert = _client()
    sink = SupabaseUsageSink(lambda: client, batch_size=3, background=False)
    for _ in range(7):
        sink(_record())
    assert [len(c.args[0]) for c in insert.call_args_list] == [3, 3]
    sink.flush()
    assert [len(c.args[0]) for c in insert.call_args_list] == [3, 3, 1]
    client.table.assert_called_with("ai_usage")
    assert sink.written == 7


def test_background_writer_flushes_on_close():
    client, insert = _client()
    sink = SupabaseUsageSink(lambda: client, batch_size=2)
    for _ in range(5):
        sink(_record())
    sink.close(timeout=5)
    assert sum(len(c.args[0]) for c in insert.call_args_list) == 5


def test_insert_failure_never_raises():
    client, insert = _client()
    insert.return_value.execute.side_effect = RuntimeError("db down")
    sink = SupabaseUsageSink(lambda: client, batch_size=1, background=False)
    sink(_record())  # must not raise
    sink.flush()
    assert sink.dropped == 1 and sink.written == 0


def test_client_factory_failure_never_raises():
    def factory():
        raise RuntimeError("no creds")

    sink = SupabaseUsageSink(factory, batch_size=1, background=False)
    sink(_record())
    assert sink.dropped == 1


def test_row_shape_and_failure_text():
    row = to_row(_record(ok=False, error="AIRequestError: 500", job="matter-summaries", meeting_id=9))
    assert row["source"] == "pipeline"
    assert row["ok"] is False and row["error"] == "AIRequestError: 500"
    assert (row["job"], row["meeting_id"], row["stage"], row["model"]) == ("matter-summaries", 9, "extraction", "gpt-6-luna")
    assert row["created_at"].endswith("+00:00")


def test_usage_context_labels_records_through_the_hook():
    seen = []
    previous = usage.set_usage_hook(seen.append)
    try:
        with usage_context(job="outer"):
            with usage_context(meeting_id=5):
                usage.record_usage(_record())
        usage.record_usage(_record())
    finally:
        usage.set_usage_hook(previous)
    assert (seen[0].job, seen[0].meeting_id) == ("outer", 5)
    assert (seen[1].job, seen[1].meeting_id) == (None, None)


def test_usage_context_reaches_worker_threads():
    from concurrent.futures import ThreadPoolExecutor

    with usage_context(job="threaded"):
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = list(pool.map(lambda _: usage.current_context().get("job"), range(2)))
    assert jobs == ["threaded", "threaded"]
