"""Usage hook: one record per model call.

The default hook only debug-logs. Install another with ``set_usage_hook`` to
persist records (a later task wires this to the database).
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Callable

logger = logging.getLogger("pipeline.ai.usage")


@dataclass
class UsageRecord:
    stage: str
    model: str
    operation: str  # text | json | pdf | embed | decide | transcribe
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    ok: bool
    error: str | None = None
    attempts: int = 1

    def as_dict(self) -> dict:
        return asdict(self)


UsageHook = Callable[[UsageRecord], None]


def _default_hook(record: UsageRecord) -> None:
    logger.debug("ai usage %s", record.as_dict())


_hook: UsageHook = _default_hook


def set_usage_hook(hook: UsageHook | None) -> UsageHook:
    """Install a usage hook (None restores the default). Returns the previous hook."""
    global _hook
    previous = _hook
    _hook = hook or _default_hook
    return previous


def record_usage(record: UsageRecord) -> None:
    try:
        _hook(record)
    except Exception:  # a broken hook must never break a pipeline run
        logger.exception("usage hook failed")
