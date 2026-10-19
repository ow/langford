"""OpenAI provider: Responses API, Embeddings, Decisions, audio transcription.

This is the only module in the pipeline that constructs an OpenAI client.
The SDK's own retries are disabled (max_retries=0) so the client's retry
policy is the only one in play.
"""

from __future__ import annotations

import base64
import copy
import os
import threading
from typing import Any

from pipeline.ai.errors import AIConfigError
from pipeline.ai.providers.base import (
    ContentPart,
    DecideResult,
    EmbedResult,
    FilePart,
    GenerateResult,
    ImagePart,
    ResponseSchema,
    TextPart,
    TranscribeResult,
    Usage,
)

TRANSIENT_STATUS = {408, 409, 429, 500, 502, 503, 504}


def _strip_defaults(node: Any) -> Any:
    """Strict mode makes every property required, so `default` carries no meaning."""
    if isinstance(node, dict):
        return {k: _strip_defaults(v) for k, v in node.items() if k != "default"}
    if isinstance(node, list):
        return [_strip_defaults(v) for v in node]
    return node


def _is_strict_compatible(node: Any) -> bool:
    """A hand-written schema can use strict mode only if every object closes
    additionalProperties and requires all of its properties."""
    if isinstance(node, dict):
        if node.get("type") == "object" or "properties" in node:
            props = node.get("properties") or {}
            if node.get("additionalProperties") is not False:
                return False
            if set(node.get("required") or []) != set(props):
                return False
        return all(_is_strict_compatible(v) for v in node.values())
    if isinstance(node, list):
        return all(_is_strict_compatible(v) for v in node)
    return True


def _usage(obj: Any) -> Usage:
    usage = getattr(obj, "usage", None)
    if usage is None:
        return Usage()
    def first(*names: str) -> int | None:
        for name in names:
            value = getattr(usage, name, None)
            if isinstance(value, int):
                return value
        return None

    return Usage(
        input_tokens=first("input_tokens", "prompt_tokens"),
        output_tokens=first("output_tokens", "completion_tokens"),
    )


def _image_url(part: ImagePart) -> str:
    if part.url:
        return part.url
    if part.data is None:
        raise ValueError("ImagePart needs a url or data")
    return f"data:{part.mime_type};base64,{base64.b64encode(part.data).decode('ascii')}"


def _input_content(parts: list[ContentPart]) -> list[dict]:
    out: list[dict] = []
    for part in parts:
        if isinstance(part, TextPart):
            out.append({"type": "input_text", "text": part.text})
        elif isinstance(part, FilePart):
            encoded = base64.b64encode(part.data).decode("ascii")
            out.append(
                {
                    "type": "input_file",
                    "filename": part.filename,
                    "file_data": f"data:{part.mime_type};base64,{encoded}",
                }
            )
        elif isinstance(part, ImagePart):
            out.append({"type": "input_image", "image_url": _image_url(part)})
        else:  # pragma: no cover - guarded by typing
            raise TypeError(f"Unsupported content part {type(part).__name__}")
    return out


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str | None = None, client: Any = None):
        self._api_key = api_key
        self._client = client
        self._lock = threading.Lock()

    @property
    def client(self):
        if self._client is None:
            with self._lock:
                if self._client is None:
                    from openai import OpenAI

                    api_key = self._api_key or os.environ.get("OPENAI_API_KEY")
                    if not api_key:
                        raise AIConfigError("OPENAI_API_KEY is not set")
                    self._client = OpenAI(api_key=api_key, max_retries=0)
        return self._client

    # ── structured output ────────────────────────────────────────────────

    def schema_for(self, schema: Any, name: str) -> ResponseSchema:
        if isinstance(schema, dict):
            body = _strip_defaults(copy.deepcopy(schema))
            return ResponseSchema(name=name, schema=body, strict=_is_strict_compatible(body))
        if isinstance(schema, type) and hasattr(schema, "model_json_schema"):
            from openai.lib._pydantic import to_strict_json_schema

            body = _strip_defaults(to_strict_json_schema(schema))
            return ResponseSchema(name=name, schema=body, strict=True)
        raise TypeError(f"schema must be a pydantic model class or a JSON schema dict, got {schema!r}")

    # ── calls ────────────────────────────────────────────────────────────

    def generate(self, *, model, system, content, schema, timeout) -> GenerateResult:
        kwargs: dict[str, Any] = {
            "model": model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": system}]},
                {"role": "user", "content": _input_content(content)},
            ],
            "store": False,
            "timeout": timeout,
        }
        if schema is not None:
            kwargs["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": schema.name,
                    "schema": schema.schema,
                    "strict": schema.strict,
                }
            }
        response = self.client.responses.create(**kwargs)

        refusal = None
        for item in getattr(response, "output", None) or []:
            for piece in getattr(item, "content", None) or []:
                if getattr(piece, "type", None) == "refusal":
                    refusal = getattr(piece, "refusal", None) or "refused"
        details = getattr(response, "incomplete_details", None)
        truncated = getattr(response, "status", None) == "incomplete" and (
            getattr(details, "reason", None) == "max_output_tokens"
        )
        return GenerateResult(
            text=response.output_text or "",
            usage=_usage(response),
            refusal=refusal,
            truncated=truncated,
        )

    def embed(self, *, model, texts, dimensions, timeout) -> EmbedResult:
        kwargs: dict[str, Any] = {"model": model, "input": texts, "timeout": timeout}
        if dimensions:
            kwargs["dimensions"] = dimensions
        response = self.client.embeddings.create(**kwargs)
        data = sorted(response.data, key=lambda d: getattr(d, "index", 0) or 0)
        return EmbedResult(vectors=[list(d.embedding) for d in data], usage=_usage(response))

    def decide(self, *, model, content, questions, timeout) -> DecideResult:
        if all(isinstance(p, TextPart) for p in content):
            input_: Any = "\n\n".join(p.text for p in content)
        else:
            input_ = [{"role": "user", "content": _input_content(content)}]
        result = self.client.decisions.create(model=model, input=input_, questions=questions, timeout=timeout)
        return DecideResult(answers={a.name: a for a in result.answers}, usage=_usage(result))

    def transcribe(self, *, model, audio_path, timeout, **options) -> TranscribeResult:
        with open(audio_path, "rb") as handle:
            raw = self.client.audio.transcriptions.with_raw_response.create(
                file=handle, model=model, timeout=timeout, **options
            )
        parsed = raw.parse()
        return TranscribeResult(
            response=parsed.model_dump(),
            request_id=raw.headers.get("x-request-id"),
            usage=_usage(parsed),
        )

    # ── retry classification ─────────────────────────────────────────────

    def is_transient(self, exc: BaseException) -> bool:
        import openai

        if isinstance(exc, (openai.APITimeoutError, openai.APIConnectionError)):
            return True
        if isinstance(exc, openai.RateLimitError):
            # An exhausted quota is a 429 too, but waiting will not fix it.
            return getattr(exc, "code", None) != "insufficient_quota"
        if isinstance(exc, openai.APIStatusError):
            return exc.status_code in TRANSIENT_STATUS
        return isinstance(exc, TimeoutError)
