"""Typed errors raised by the pipeline AI client."""

from __future__ import annotations


class AIError(Exception):
    """A model call failed. Carries the stage and model for logging."""

    def __init__(self, message: str, *, stage: str | None = None, model: str | None = None):
        super().__init__(message)
        self.stage = stage
        self.model = model


class AIConfigError(AIError):
    """The stage is misconfigured (unsupported provider, missing key, bad value)."""


class AIRequestError(AIError):
    """The provider request failed after the retry policy gave up."""

    def __init__(self, message: str, *, stage=None, model=None, attempts: int = 1, transient: bool = False):
        super().__init__(message, stage=stage, model=model)
        self.attempts = attempts
        self.transient = transient


class AIResponseError(AIError):
    """The provider answered, but the answer was empty, refused, or failed schema validation."""
