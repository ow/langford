"""Provider-selectable AI helpers for pipeline jobs.

Gemini remains the default provider to preserve current ingestion behavior.
Set AI_PROVIDER or a workload-specific *_AI_PROVIDER to "openai" to opt in.
"""

from __future__ import annotations

import json
import os
import time
import base64
from typing import Any

from dotenv import load_dotenv

load_dotenv()

ProviderName = str

DEFAULT_PROVIDER = "gemini"
DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"
DEFAULT_OPENAI_MODEL = "gpt-5-mini"

SCOPE_PREFIX = {
    "rag": "RAG",
    "rerank": "RERANK",
    "extraction": "EXTRACTION",
    "document": "DOCUMENT",
    "profile": "PROFILE",
    "embedding": "EMBEDDING",
}

_gemini_client = None
_openai_client = None


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else None


def normalize_provider(value: str | None) -> ProviderName:
    if value and value.lower() in {"gemini", "openai"}:
        return value.lower()
    return DEFAULT_PROVIDER


def get_ai_config(scope: str = "extraction") -> tuple[ProviderName, str]:
    prefix = SCOPE_PREFIX.get(scope, scope.upper())
    provider = normalize_provider(_env(f"{prefix}_AI_PROVIDER") or _env("AI_PROVIDER"))
    model = (
        _env(f"{prefix}_AI_MODEL")
        or _env("AI_MODEL")
        or (_env("GEMINI_MODEL") if provider == "gemini" else None)
        or (_env("OPENAI_MODEL") if provider == "openai" else None)
        or (DEFAULT_OPENAI_MODEL if provider == "openai" else DEFAULT_GEMINI_MODEL)
    )
    return provider, model


def is_ai_configured(scope: str = "extraction") -> bool:
    provider, _ = get_ai_config(scope)
    key_name = "OPENAI_API_KEY" if provider == "openai" else "GEMINI_API_KEY"
    return bool(_env(key_name))


def get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        from google import genai

        api_key = _env("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI

        api_key = _env("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


def clean_json_text(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return cleaned


def _schema_from_model(schema: Any) -> dict[str, Any] | None:
    if schema is None:
        return None
    if isinstance(schema, dict):
        return schema
    if hasattr(schema, "model_json_schema"):
        return schema.model_json_schema()
    return None


def generate_text(
    prompt: str,
    *,
    scope: str = "extraction",
    model: str | None = None,
    system: str | None = None,
    json_mode: bool = False,
    schema: Any = None,
    retries: int = 2,
) -> str | None:
    provider, configured_model = get_ai_config(scope)
    model_name = model or configured_model

    for attempt in range(retries):
        try:
            if provider == "openai":
                client = get_openai_client()
                input_items = []
                if system:
                    input_items.append(
                        {
                            "role": "system",
                            "content": [{"type": "input_text", "text": system}],
                        }
                    )
                input_items.append(
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": prompt}],
                    }
                )

                text_format = None
                json_schema = _schema_from_model(schema)
                if json_schema:
                    text_format = {
                        "format": {
                            "type": "json_schema",
                            "name": "response",
                            "schema": json_schema,
                            "strict": False,
                        }
                    }
                elif json_mode:
                    text_format = {"format": {"type": "json_object"}}

                response = client.responses.create(
                    model=model_name,
                    input=input_items,
                    text=text_format,
                    store=False,
                )
                return clean_json_text(response.output_text)

            client = get_gemini_client()
            config = None
            if json_mode or schema is not None:
                config = {"response_mime_type": "application/json"}
                if schema is not None:
                    config["response_schema"] = schema
            if system:
                config = config or {}
                config["system_instruction"] = system
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )
            if getattr(response, "parsed", None) is not None:
                parsed = response.parsed
                if hasattr(parsed, "model_dump_json"):
                    return parsed.model_dump_json()
                return json.dumps(parsed)
            return clean_json_text(response.text or "")
        except Exception as exc:
            error = str(exc).lower()
            transient = any(
                marker in error
                for marker in ["rate limit", "429", "500", "503", "overloaded", "unavailable"]
            )
            if transient and attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
                continue
            raise

    return None


def generate_json(
    prompt: str,
    *,
    scope: str = "extraction",
    model: str | None = None,
    system: str | None = None,
    schema: Any = None,
) -> Any:
    text = generate_text(
        prompt,
        scope=scope,
        model=model,
        system=system,
        json_mode=True,
        schema=schema,
    )
    if text is None:
        return None
    return json.loads(clean_json_text(text))


def generate_pdf_text(
    pdf_path: str,
    prompt: str,
    *,
    scope: str = "document",
    model: str | None = None,
    json_mode: bool = False,
    retries: int = 2,
) -> str | None:
    """Send a PDF plus prompt to the configured provider and return text.

    The OpenAI path uses Responses API file input with inline base64 data.
    The Gemini path uses inline PDF bytes, matching the existing document
    extraction behavior without requiring File API state.
    """
    provider, configured_model = get_ai_config(scope)
    model_name = model or configured_model

    for attempt in range(retries):
        try:
            with open(pdf_path, "rb") as handle:
                pdf_bytes = handle.read()

            if provider == "openai":
                client = get_openai_client()
                encoded = base64.b64encode(pdf_bytes).decode("ascii")
                response = client.responses.create(
                    model=model_name,
                    input=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_file",
                                    "filename": os.path.basename(pdf_path),
                                    "file_data": f"data:application/pdf;base64,{encoded}",
                                },
                                {"type": "input_text", "text": prompt},
                            ],
                        }
                    ],
                    store=False,
                )
                return clean_json_text(response.output_text)

            from google.genai import types

            client = get_gemini_client()
            pdf_part = types.Part.from_bytes(
                data=pdf_bytes,
                mime_type="application/pdf",
            )
            response = client.models.generate_content(
                model=model_name,
                contents=[pdf_part, prompt],
            )
            return clean_json_text(response.text or "")
        except Exception as exc:
            error = str(exc).lower()
            transient = any(
                marker in error
                for marker in ["rate limit", "429", "500", "503", "overloaded", "unavailable"]
            )
            if transient and attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
                continue
            raise

    return None
