"""The pipeline's single model client.

    from pipeline import ai

    ai.text(prompt, stage="extraction", system=...)            -> str
    ai.json(prompt, stage="extraction", schema=MyModel)        -> MyModel instance
    ai.json(prompt, stage="extraction", schema={...})          -> parsed JSON
    ai.pdf(path, prompt, stage="document", schema=None)        -> str | parsed
    ai.decide(input, [ai.choice(...)], stage="decisions")      -> {name: answer}
    ai.decide_many([(input, questions), ...])                  -> [answers | Exception]
    ai.embed(texts)                                            -> [[float, ...], ...]

One place for: per-stage model resolution, house rules on every system
prompt, structured output, the retry/timeout policy, typed errors and the
usage hook.
"""

from __future__ import annotations

import json as _json
import logging
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence, TypeVar

from pipeline.ai import config as ai_config
from pipeline.ai.errors import AIConfigError, AIError, AIRequestError, AIResponseError
from pipeline.ai.providers.base import FilePart, ImagePart, Provider, TextPart, Usage
from pipeline.ai.usage import UsageRecord, record_usage

logger = logging.getLogger(__name__)

T = TypeVar("T")

# House rules appended to every system prompt, so individual prompts can't forget them.
HOUSE_RULES = (
    "House rules for anything written about people: never infer or assume anyone's gender. "
    "Do not use he/him/his or she/her/hers unless the source text states that person's pronouns; "
    "refer to people by name, role or title, or use they/them, or start the sentence with the verb."
)

DEFAULT_SYSTEM = "You are a careful assistant processing municipal council records."

EMBED_BATCH_SIZE = 128
PROGRESS_INTERVAL = 30


def with_house_rules(system: str | None) -> str:
    base = (system or "").rstrip() or DEFAULT_SYSTEM
    return f"{base}\n\n{HOUSE_RULES}"


@dataclass(frozen=True)
class RetryPolicy:
    """Transient errors (429, 5xx, timeouts, dropped connections) retry with
    exponential backoff; everything else fails on the first attempt."""

    max_attempts: int = 3
    base_delay: float = 2.0
    max_delay: float = 30.0

    def delay(self, attempt: int) -> float:
        """Seconds to wait after failed attempt number ``attempt`` (1-based)."""
        backoff = min(self.max_delay, self.base_delay * (2 ** (attempt - 1)))
        return backoff * (0.75 + random.random() * 0.5)


def _image_part(image: Any) -> ImagePart:
    if isinstance(image, ImagePart):
        return image
    if isinstance(image, (bytes, bytearray)):
        return ImagePart(data=bytes(image))
    if isinstance(image, str):
        return ImagePart(url=image)
    if isinstance(image, dict):  # {"data": bytes, "mime_type": "..."}
        return ImagePart(url=image.get("url"), data=image.get("data"), mime_type=image.get("mime_type", "image/webp"))
    raise TypeError(f"Unsupported image input {type(image).__name__}")


class AIClient:
    def __init__(
        self,
        provider: Provider | None = None,
        *,
        retry: RetryPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
        progress: bool = True,
    ):
        self._provider = provider
        self.retry = retry or RetryPolicy()
        self._sleep = sleep
        self._progress = progress

    # ── plumbing ─────────────────────────────────────────────────────────

    def provider_for(self, cfg: ai_config.StageConfig) -> Provider:
        if self._provider is not None:
            return self._provider
        if cfg.provider == "openai":
            from pipeline.ai.providers.openai import OpenAIProvider

            self._provider = OpenAIProvider()
            return self._provider
        raise AIConfigError(f"No provider adapter for '{cfg.provider}'", stage=cfg.stage)

    def _call(
        self,
        operation: str,
        cfg: ai_config.StageConfig,
        fn: Callable[[Provider], T],
        *,
        label: str | None = None,
        max_attempts: int | None = None,
        usage_of: Callable[[T], Usage] = lambda r: getattr(r, "usage", Usage()),
    ) -> T:
        """Run ``fn`` under the retry policy, record usage, raise typed errors."""
        provider = self.provider_for(cfg)
        attempts_allowed = max_attempts or self.retry.max_attempts
        started = time.monotonic()
        attempt = 0
        long_running = operation in ("text", "json", "pdf", "transcribe")
        stop_progress = (
            self._start_progress(label or f"{operation} {cfg.stage}", cfg.model, started) if long_running else (lambda: None)
        )
        try:
            while True:
                attempt += 1
                try:
                    result = fn(provider)
                except AIError as exc:
                    self._record(operation, cfg, started, attempt, None, exc)
                    raise
                except Exception as exc:
                    transient = provider.is_transient(exc)
                    if transient and attempt < attempts_allowed:
                        wait = self.retry.delay(attempt)
                        logger.warning(
                            "[AI] %s %s attempt %d/%d failed (%s); retrying in %.1fs",
                            operation, cfg.stage, attempt, attempts_allowed, exc, wait,
                        )
                        self._sleep(wait)
                        continue
                    self._record(operation, cfg, started, attempt, None, exc)
                    raise AIRequestError(
                        f"{operation} ({cfg.stage}, {cfg.model}) failed after {attempt} attempt(s): {exc}",
                        stage=cfg.stage,
                        model=cfg.model,
                        attempts=attempt,
                        transient=transient,
                    ) from exc
                self._record(operation, cfg, started, attempt, usage_of(result), None)
                return result
        finally:
            stop_progress()

    def _record(self, operation, cfg, started, attempts, usage: Usage | None, error: BaseException | None):
        record_usage(
            UsageRecord(
                stage=cfg.stage,
                model=cfg.model,
                operation=operation,
                input_tokens=usage.input_tokens if usage else None,
                output_tokens=usage.output_tokens if usage else None,
                latency_ms=int((time.monotonic() - started) * 1000),
                ok=error is None,
                error=None if error is None else f"{type(error).__name__}: {error}"[:500],
                attempts=attempts,
            )
        )

    def _start_progress(self, label: str, model: str, started: float) -> Callable[[], None]:
        if not self._progress:
            return lambda: None
        print(f"  [AI] Starting {label} (model={model})")
        done = threading.Event()

        def report():
            while not done.wait(PROGRESS_INTERVAL):
                print(f"  [AI] Still waiting on {label} ({int(time.monotonic() - started)}s elapsed)...")

        threading.Thread(target=report, daemon=True).start()

        def stop():
            done.set()
            print(f"  [AI] Finished {label} in {time.monotonic() - started:.1f}s")

        return stop

    # ── generation ───────────────────────────────────────────────────────

    def _generate(self, operation, content, *, stage, system, schema, label=None):
        cfg = ai_config.resolve(stage)
        provider = self.provider_for(cfg)
        response_schema = None
        if schema is not None:
            name = getattr(schema, "__name__", None) or "response"
            response_schema = provider.schema_for(schema, name)
        system_prompt = with_house_rules(system)

        result = self._call(
            operation,
            cfg,
            lambda p: p.generate(
                model=cfg.model,
                system=system_prompt,
                content=content,
                schema=response_schema,
                timeout=cfg.timeout,
            ),
            label=label,
        )
        if result.refusal:
            raise AIResponseError(f"Model refused ({cfg.stage}): {result.refusal}", stage=cfg.stage, model=cfg.model)
        if result.truncated:
            logger.warning("[AI] %s %s response truncated at max output tokens", operation, cfg.stage)
        if schema is None:
            return result.text.strip()
        return self._parse(result.text, schema, cfg)

    @staticmethod
    def _parse(text: str, schema: Any, cfg: ai_config.StageConfig) -> Any:
        if not text.strip():
            raise AIResponseError(f"Empty structured response ({cfg.stage})", stage=cfg.stage, model=cfg.model)
        try:
            if isinstance(schema, type) and hasattr(schema, "model_validate_json"):
                return schema.model_validate_json(text)
            return _json.loads(text)
        except Exception as exc:
            raise AIResponseError(
                f"Response did not match schema ({cfg.stage}): {exc}", stage=cfg.stage, model=cfg.model
            ) from exc

    def text(self, prompt: str, *, stage: str, system: str | None = None) -> str:
        """Free-text generation."""
        return self._generate("text", [TextPart(prompt)], stage=stage, system=system, schema=None)

    def json(self, prompt: str, *, stage: str, schema: Any, system: str | None = None) -> Any:
        """Structured generation. ``schema`` is a pydantic model class (returns an
        instance) or a JSON schema dict (returns parsed JSON)."""
        if schema is None:
            raise ValueError("ai.json requires a schema")
        return self._generate("json", [TextPart(prompt)], stage=stage, system=system, schema=schema)

    def pdf(
        self,
        path: str,
        prompt: str,
        *,
        stage: str = "document",
        schema: Any = None,
        system: str | None = None,
        images: Sequence[Any] | None = None,
    ) -> Any:
        """Send a PDF (plus optional images) with a prompt. Returns text, or the
        parsed schema output when ``schema`` is given."""
        with open(path, "rb") as handle:
            data = handle.read()
        content: list = [FilePart(filename=os.path.basename(path), data=data)]
        for idx, image in enumerate(images or [], 1):
            content.append(TextPart(f"Image {idx}:"))
            content.append(_image_part(image))
        content.append(TextPart(prompt))
        label = f"pdf {stage} {os.path.basename(path)} ({len(data) // 1024} KB)"
        return self._generate("pdf", content, stage=stage, system=system, schema=schema, label=label)

    # ── decisions ────────────────────────────────────────────────────────

    def decide(
        self,
        input: str,
        questions: list[dict],
        *,
        stage: str = "decisions",
        images: Sequence[Any] | None = None,
    ) -> dict[str, Any]:
        """Evaluate one input against Decisions API questions. Returns {question_name: answer}."""
        cfg = ai_config.resolve(stage)
        content: list = [TextPart(input)] + [_image_part(i) for i in images or []]
        result = self._call(
            "decide",
            cfg,
            lambda p: p.decide(model=cfg.model, content=content, questions=questions, timeout=cfg.timeout),
        )
        return result.answers

    def decide_many(
        self,
        items: Iterable[tuple],
        *,
        stage: str = "decisions",
        workers: int = 8,
    ) -> list[dict[str, Any] | Exception]:
        """Run decide() over (input, questions[, images]) items concurrently, preserving
        order. Failures come back per item as exceptions so one bad item doesn't sink a batch."""

        def run(item: tuple) -> Any:
            try:
                text, questions, *rest = item
                return self.decide(text, questions, stage=stage, images=rest[0] if rest else None)
            except Exception as exc:
                return exc

        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(run, list(items)))

    # ── embeddings ───────────────────────────────────────────────────────

    def embed(self, texts: Sequence[str], *, stage: str = "embedding") -> list[list[float]]:
        """Embed texts with the configured model and dimensions. Raises on any
        failure or blank input; never returns placeholder vectors."""
        texts = list(texts)
        if not texts:
            return []
        blank = [i for i, t in enumerate(texts) if not isinstance(t, str) or not t.strip()]
        if blank:
            raise ValueError(f"Cannot embed blank text (indexes {blank[:10]})")
        cfg = ai_config.resolve(stage)
        vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBED_BATCH_SIZE):
            chunk = texts[start : start + EMBED_BATCH_SIZE]
            result = self._call(
                "embed",
                cfg,
                lambda p: p.embed(model=cfg.model, texts=chunk, dimensions=cfg.dimensions, timeout=cfg.timeout),
            )
            if len(result.vectors) != len(chunk):
                raise AIResponseError(
                    f"Embedding count mismatch: sent {len(chunk)}, got {len(result.vectors)}",
                    stage=cfg.stage,
                    model=cfg.model,
                )
            vectors.extend(result.vectors)
        return vectors

    # ── audio ────────────────────────────────────────────────────────────

    def transcribe(
        self,
        audio_path: str,
        *,
        stage: str = "asr",
        model: str | None = None,
        max_attempts: int | None = None,
        **options: Any,
    ):
        """Transcribe an audio file. Returns the provider TranscribeResult
        (``response`` dict plus ``request_id``)."""
        cfg = ai_config.resolve(stage)
        if model:
            cfg = ai_config.StageConfig(stage=cfg.stage, provider=cfg.provider, model=model, timeout=cfg.timeout)
        return self._call(
            "transcribe",
            cfg,
            lambda p: p.transcribe(model=cfg.model, audio_path=audio_path, timeout=cfg.timeout, **options),
            max_attempts=max_attempts,
        )


# ── question builders for the Decisions API ─────────────────────────────


def choice(name: str, instructions: str, choices: list[tuple[str, str]]) -> dict:
    """A choice question from (value, description) pairs."""
    return {
        "type": "choice",
        "name": name,
        "instructions": instructions,
        "choices": [{"value": v, "description": d} for v, d in choices],
    }


def predicate(name: str, instructions: str) -> dict:
    """A yes/no question answered with a probability."""
    return {"type": "predicate", "name": name, "instructions": instructions}


# ── default client ───────────────────────────────────────────────────────

_default: AIClient | None = None
_default_lock = threading.Lock()


def get_client() -> AIClient:
    global _default
    if _default is None:
        with _default_lock:
            if _default is None:
                _default = AIClient()
    return _default


def set_client(client: AIClient | None) -> AIClient | None:
    """Replace the default client (tests). Returns the previous one."""
    global _default
    previous, _default = _default, client
    return previous
