"""Unit tests for pipeline.ai: config resolution, retry policy, house rules,
structured output, embeddings, decisions, usage hook, and the OpenAI adapter."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import openai
import pytest
from pydantic import BaseModel

from pipeline import ai
from pipeline.ai import config as ai_config
from pipeline.ai.providers.base import DecideResult, EmbedResult, GenerateResult, TextPart, Usage
from pipeline.ai.providers.openai import OpenAIProvider

AI_ENV = [
    "AI_PROVIDER", "AI_MODEL", "OPENAI_MODEL", "EXTRACTION_AI_PROVIDER", "EXTRACTION_AI_MODEL",
    "DOCUMENT_AI_MODEL", "PROFILE_AI_MODEL", "PROFILE_AI_PROVIDER", "EMBEDDING_PROVIDER",
    "EMBEDDING_MODEL", "EMBEDDING_DIMENSIONS", "DECISIONS_MODEL", "AI_TIMEOUT_SECONDS",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in AI_ENV:
        monkeypatch.delenv(name, raising=False)


class Summary(BaseModel):
    title: str
    note: str | None = None


# ── config ───────────────────────────────────────────────────────────────


class TestConfig:
    def test_defaults(self):
        cfg = ai.resolve("extraction")
        assert (cfg.provider, cfg.model, cfg.timeout) == ("openai", "gpt-6-luna", 600.0)

    def test_stage_model_beats_global(self, monkeypatch):
        monkeypatch.setenv("AI_MODEL", "global-model")
        monkeypatch.setenv("PROFILE_AI_MODEL", "profile-model")
        assert ai.resolve("profile").model == "profile-model"
        assert ai.resolve("extraction").model == "global-model"

    def test_global_model_beats_legacy_openai_model(self, monkeypatch):
        monkeypatch.setenv("OPENAI_MODEL", "legacy")
        assert ai.resolve("document").model == "legacy"
        monkeypatch.setenv("AI_MODEL", "global-model")
        assert ai.resolve("document").model == "global-model"

    def test_embedding_defaults_match_stored_vectors(self):
        cfg = ai.resolve("embedding")
        assert (cfg.model, cfg.dimensions) == ("text-embedding-3-small", 384)

    def test_embedding_env(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-large")
        monkeypatch.setenv("EMBEDDING_DIMENSIONS", "1024")
        cfg = ai.resolve("embedding")
        assert (cfg.model, cfg.dimensions) == ("text-embedding-3-large", 1024)

    def test_decisions_model(self, monkeypatch):
        monkeypatch.setenv("AI_MODEL", "ignored-for-decisions")
        assert ai.resolve("decisions").model == "gpt-6-luna"
        monkeypatch.setenv("DECISIONS_MODEL", "decider")
        assert ai.resolve("decisions").model == "decider"

    def test_unsupported_provider_is_a_config_error(self, monkeypatch):
        monkeypatch.setenv("EXTRACTION_AI_PROVIDER", "gemini")
        with pytest.raises(ai.AIConfigError, match="gemini"):
            ai.resolve("extraction")
        assert ai.resolve("profile").provider == "openai"

    def test_bad_number_is_a_config_error(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_DIMENSIONS", "lots")
        with pytest.raises(ai.AIConfigError):
            ai.resolve("embedding")

    def test_is_configured_needs_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert not ai_config.is_configured("extraction")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        assert ai_config.is_configured("extraction")


# ── house rules ──────────────────────────────────────────────────────────


class TestHouseRules:
    def test_text_call_gets_house_rules(self, fake_ai):
        fake_ai.queue("generate", GenerateResult(text=" Hello. "))
        assert ai.text("hi", stage="extraction", system="Be brief.") == "Hello."
        system = fake_ai.calls[0][1]["system"]
        assert system.startswith("Be brief.") and system.endswith(ai.HOUSE_RULES)

    def test_default_system_still_gets_house_rules(self, fake_ai):
        fake_ai.queue("generate", GenerateResult(text='{"title": "x", "note": null}'))
        ai.json("hi", stage="profile", schema=Summary)
        assert ai.HOUSE_RULES in fake_ai.calls[0][1]["system"]

    def test_pdf_call_gets_house_rules_and_file(self, fake_ai, tmp_path):
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")
        fake_ai.queue("generate", GenerateResult(text="## Content"))
        assert ai.pdf(str(pdf), "Extract", stage="document") == "## Content"
        kwargs = fake_ai.calls[0][1]
        assert ai.HOUSE_RULES in kwargs["system"]
        file_part, prompt_part = kwargs["content"]
        assert file_part.filename == "doc.pdf" and file_part.data == b"%PDF-1.4 test"
        assert prompt_part == TextPart("Extract")


# ── structured output ────────────────────────────────────────────────────


class TestStructuredOutput:
    def test_pydantic_schema_returns_instance_with_strict_schema(self, fake_ai):
        fake_ai.queue("generate", GenerateResult(text='{"title": "Rezoning", "note": null}'))
        result = ai.json("prompt", stage="extraction", schema=Summary)
        assert isinstance(result, Summary) and result.title == "Rezoning"
        schema = fake_ai.calls[0][1]["schema"]
        assert schema.name == "Summary" and schema.strict is True
        assert set(schema.schema["required"]) == {"title", "note"}
        assert schema.schema["additionalProperties"] is False

    def test_dict_schema_returns_parsed_json(self, fake_ai):
        fake_ai.queue("generate", GenerateResult(text='{"a": 1}'))
        schema = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"], "additionalProperties": False}
        assert ai.json("prompt", stage="extraction", schema=schema) == {"a": 1}
        assert fake_ai.calls[0][1]["schema"].strict is True

    def test_loose_dict_schema_is_not_strict(self, fake_ai):
        fake_ai.queue("generate", GenerateResult(text='{"a": 1}'))
        ai.json("prompt", stage="extraction", schema={"type": "object", "properties": {"a": {"type": "integer"}}})
        assert fake_ai.calls[0][1]["schema"].strict is False

    def test_schema_mismatch_raises_response_error(self, fake_ai):
        fake_ai.queue("generate", GenerateResult(text='{"nope": true}'))
        with pytest.raises(ai.AIResponseError):
            ai.json("prompt", stage="extraction", schema=Summary)

    def test_refusal_raises_response_error(self, fake_ai):
        fake_ai.queue("generate", GenerateResult(text="", refusal="can't help"))
        with pytest.raises(ai.AIResponseError, match="refused"):
            ai.json("prompt", stage="extraction", schema=Summary)

    def test_json_requires_schema(self, fake_ai):
        with pytest.raises(ValueError):
            ai.json("prompt", stage="extraction", schema=None)


# ── retry policy ─────────────────────────────────────────────────────────


class TestRetryPolicy:
    def test_transient_errors_retry_then_succeed(self, fake_ai):
        fake_ai.queue("generate", TimeoutError("slow"), Exception("503 unavailable"), GenerateResult(text="ok"))
        assert ai.text("p", stage="extraction") == "ok"
        assert len(fake_ai.calls) == 3

    def test_gives_up_after_three_attempts(self, fake_ai):
        fake_ai.queue("generate", *[Exception("429 rate limit")] * 5)
        with pytest.raises(ai.AIRequestError) as info:
            ai.text("p", stage="extraction")
        assert info.value.attempts == 3 and info.value.transient
        assert len(fake_ai.calls) == 3

    def test_non_transient_error_fails_immediately(self, fake_ai):
        fake_ai.queue("generate", Exception("400 bad request"), GenerateResult(text="never"))
        with pytest.raises(ai.AIRequestError) as info:
            ai.text("p", stage="extraction")
        assert info.value.attempts == 1 and not info.value.transient
        assert len(fake_ai.calls) == 1

    def test_backoff_is_exponential(self):
        policy = ai.RetryPolicy(base_delay=2.0, max_delay=30.0)
        first, second = policy.delay(1), policy.delay(2)
        assert 1.5 <= first <= 2.5 and 3.0 <= second <= 5.0
        assert policy.delay(10) <= 30.0 * 1.25

    def test_sleeps_between_attempts(self):
        from tests.conftest import FakeProvider

        sleeps = []
        provider = FakeProvider().queue("generate", TimeoutError(), GenerateResult(text="ok"))
        client = ai.AIClient(provider, sleep=sleeps.append, progress=False)
        assert client.text("p", stage="extraction") == "ok"
        assert len(sleeps) == 1 and sleeps[0] > 0

    def test_request_timeout_is_passed(self, fake_ai, monkeypatch):
        monkeypatch.setenv("AI_TIMEOUT_SECONDS", "42")
        fake_ai.queue("generate", GenerateResult(text="ok"))
        ai.text("p", stage="extraction")
        assert fake_ai.calls[0][1]["timeout"] == 42.0


# ── embeddings ───────────────────────────────────────────────────────────


class TestEmbed:
    def test_embeds_with_configured_model_and_dimensions(self, fake_ai):
        fake_ai.queue("embed", EmbedResult(vectors=[[0.1, 0.2], [0.3, 0.4]]))
        assert ai.embed(["a", "b"]) == [[0.1, 0.2], [0.3, 0.4]]
        kwargs = fake_ai.calls[0][1]
        assert (kwargs["model"], kwargs["dimensions"]) == ("text-embedding-3-small", 384)

    def test_batches_large_inputs(self, fake_ai):
        from pipeline.ai.client import EMBED_BATCH_SIZE

        n = EMBED_BATCH_SIZE + 5
        fake_ai.queue("embed", EmbedResult(vectors=[[1.0]] * EMBED_BATCH_SIZE), EmbedResult(vectors=[[2.0]] * 5))
        vectors = ai.embed([f"t{i}" for i in range(n)])
        assert len(vectors) == n and vectors[-1] == [2.0]
        assert [len(c[1]["texts"]) for c in fake_ai.calls] == [EMBED_BATCH_SIZE, 5]

    def test_error_raises_instead_of_zero_vectors(self, fake_ai):
        fake_ai.queue("embed", Exception("401 invalid key"))
        with pytest.raises(ai.AIRequestError):
            ai.embed(["hello"])

    def test_blank_text_raises(self, fake_ai):
        with pytest.raises(ValueError, match="blank"):
            ai.embed(["ok", "  "])
        assert fake_ai.calls == []

    def test_count_mismatch_raises(self, fake_ai):
        fake_ai.queue("embed", EmbedResult(vectors=[[0.1]]))
        with pytest.raises(ai.AIResponseError):
            ai.embed(["a", "b"])

    def test_empty_input(self, fake_ai):
        assert ai.embed([]) == []


# ── decisions ────────────────────────────────────────────────────────────


class TestDecide:
    def test_decide_passes_text_and_images(self, fake_ai):
        answer = SimpleNamespace(name="kind", type="choice", choice="site_plan")
        fake_ai.queue("decide", DecideResult(answers={"kind": answer}))
        q = ai.choice("kind", "What is it?", [("site_plan", "A site plan"), ("other", "Other")])
        result = ai.decide("context", [q], images=[{"data": b"img", "mime_type": "image/webp"}])
        assert result["kind"].choice == "site_plan"
        kwargs = fake_ai.calls[0][1]
        assert kwargs["model"] == "gpt-6-luna"
        assert kwargs["content"][0] == TextPart("context")
        assert kwargs["content"][1].data == b"img"
        assert kwargs["questions"][0]["choices"][0] == {"value": "site_plan", "description": "A site plan"}

    def test_decide_many_preserves_order_and_returns_errors_per_item(self, fake_ai):
        ok = DecideResult(answers={"q": SimpleNamespace(name="q", type="predicate", probability=0.9)})
        fake_ai.queue("decide", ok, Exception("400 bad"))
        q = ai.predicate("q", "True?")
        results = ai.decide_many([("one", [q]), ("two", [q])], workers=1)
        assert results[0]["q"].probability == 0.9
        assert isinstance(results[1], ai.AIRequestError)


# ── usage hook ───────────────────────────────────────────────────────────


class TestUsageHook:
    def test_records_success_and_failure(self, fake_ai):
        records = []
        previous = ai.set_usage_hook(records.append)
        try:
            fake_ai.queue("generate", GenerateResult(text="ok", usage=Usage(input_tokens=10, output_tokens=3)))
            ai.text("p", stage="profile")
            fake_ai.queue("generate", Exception("400 bad"))
            with pytest.raises(ai.AIRequestError):
                ai.text("p", stage="profile")
        finally:
            ai.set_usage_hook(previous)
        ok, failed = records
        assert (ok.stage, ok.model, ok.operation, ok.input_tokens, ok.output_tokens, ok.ok) == (
            "profile", "gpt-6-luna", "text", 10, 3, True,
        )
        assert ok.latency_ms >= 0 and ok.error is None
        assert failed.ok is False and "400 bad" in failed.error

    def test_broken_hook_does_not_break_calls(self, fake_ai):
        def boom(_record):
            raise RuntimeError("hook down")

        previous = ai.set_usage_hook(boom)
        try:
            fake_ai.queue("generate", GenerateResult(text="ok"))
            assert ai.text("p", stage="extraction") == "ok"
        finally:
            ai.set_usage_hook(previous)


# ── OpenAI adapter ───────────────────────────────────────────────────────


def _status_error(cls, status, code=None):
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(status, request=request)
    body = {"code": code} if code else None  # the SDK passes the unwrapped "error" object
    return cls("err", response=response, body=body)


class TestOpenAIProvider:
    def test_is_transient(self):
        p = OpenAIProvider(api_key="test")
        request = httpx.Request("POST", "https://api.openai.com/v1/responses")
        assert p.is_transient(openai.APITimeoutError(request=request))
        assert p.is_transient(openai.APIConnectionError(request=request))
        assert p.is_transient(_status_error(openai.RateLimitError, 429))
        assert p.is_transient(_status_error(openai.InternalServerError, 503))
        assert not p.is_transient(_status_error(openai.RateLimitError, 429, code="insufficient_quota"))
        assert not p.is_transient(_status_error(openai.BadRequestError, 400))
        assert not p.is_transient(ValueError("nope"))

    def test_generate_builds_responses_request(self):
        fake = MagicMock()
        fake.responses.create.return_value = SimpleNamespace(
            output_text='{"title": "x", "note": null}', output=[], status="completed", incomplete_details=None,
            usage=SimpleNamespace(input_tokens=5, output_tokens=2),
        )
        p = OpenAIProvider(client=fake)
        schema = p.schema_for(Summary, "Summary")
        result = p.generate(model="m", system="sys", content=[TextPart("hi")], schema=schema, timeout=12)
        kwargs = fake.responses.create.call_args.kwargs
        assert kwargs["model"] == "m" and kwargs["timeout"] == 12 and kwargs["store"] is False
        assert kwargs["input"][0]["content"][0]["text"] == "sys"
        assert kwargs["text"]["format"]["type"] == "json_schema" and kwargs["text"]["format"]["strict"] is True
        assert (result.usage.input_tokens, result.usage.output_tokens) == (5, 2)

    def test_client_disables_sdk_retries(self, monkeypatch):
        created = {}

        class FakeOpenAI:
            def __init__(self, **kwargs):
                created.update(kwargs)

        monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
        OpenAIProvider(api_key="sk-test").client
        assert created == {"api_key": "sk-test", "max_retries": 0}

    def test_missing_key_is_config_error(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(ai.AIConfigError):
            OpenAIProvider().client

    def test_strict_schema_strips_defaults(self):
        class WithDefaults(BaseModel):
            tags: list[str] = []
            note: str | None = None

        schema = OpenAIProvider(api_key="t").schema_for(WithDefaults, "WithDefaults").schema
        assert "default" not in str(schema)
        assert set(schema["required"]) == {"tags", "note"}
