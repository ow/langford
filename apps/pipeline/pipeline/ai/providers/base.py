"""Provider adapter interface.

A provider turns the client's provider-neutral requests into API calls. It
does no retries and applies no house rules; the client owns both.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, Union


@dataclass(frozen=True)
class TextPart:
    text: str


@dataclass(frozen=True)
class FilePart:
    filename: str
    data: bytes
    mime_type: str = "application/pdf"


@dataclass(frozen=True)
class ImagePart:
    """An image as a URL (https:// or data:) or raw bytes plus mime type."""

    url: str | None = None
    data: bytes | None = None
    mime_type: str = "image/webp"


ContentPart = Union[TextPart, FilePart, ImagePart]


@dataclass
class ResponseSchema:
    """A JSON schema the provider must constrain its output to."""

    name: str
    schema: dict[str, Any]
    strict: bool


@dataclass
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass
class GenerateResult:
    text: str
    usage: Usage = field(default_factory=Usage)
    refusal: str | None = None
    truncated: bool = False


@dataclass
class EmbedResult:
    vectors: list[list[float]]
    usage: Usage = field(default_factory=Usage)


@dataclass
class DecideResult:
    answers: dict[str, Any]  # question name -> provider answer object
    usage: Usage = field(default_factory=Usage)


@dataclass
class TranscribeResult:
    response: dict[str, Any]
    request_id: str | None = None
    usage: Usage = field(default_factory=Usage)


class Provider(Protocol):
    name: str

    def generate(
        self,
        *,
        model: str,
        system: str,
        content: list[ContentPart],
        schema: ResponseSchema | None,
        timeout: float,
    ) -> GenerateResult: ...

    def embed(self, *, model: str, texts: list[str], dimensions: int | None, timeout: float) -> EmbedResult: ...

    def decide(
        self,
        *,
        model: str,
        content: list[ContentPart],
        questions: list[dict],
        timeout: float,
    ) -> DecideResult: ...

    def transcribe(
        self,
        *,
        model: str,
        audio_path: str,
        timeout: float,
        **options: Any,
    ) -> TranscribeResult: ...

    def schema_for(self, schema: Any, name: str) -> ResponseSchema:
        """Turn a pydantic model class or JSON schema dict into a ResponseSchema."""
        ...

    def is_transient(self, exc: BaseException) -> bool:
        """True for errors worth retrying (rate limits, 5xx, timeouts, connection drops)."""
        ...
