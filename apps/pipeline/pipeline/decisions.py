"""OpenAI Decisions API helpers (client.decisions.create, public beta).

Use for classification-style judgements — pick one of N answers, or the
probability a statement is true — where calibrated probabilities matter more
than generated text.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Any

from openai import OpenAI

DECISIONS_MODEL = os.environ.get("DECISIONS_MODEL", "gpt-6-luna")


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    return OpenAI(max_retries=4)


def choice(name: str, instructions: str, choices: list[tuple[str, str]]) -> dict:
    """Build a choice question from (value, description) pairs."""
    return {
        "type": "choice",
        "name": name,
        "instructions": instructions,
        "choices": [{"value": v, "description": d} for v, d in choices],
    }


def decide(input_text: str, questions: list[dict]) -> dict[str, Any]:
    """Evaluate one input against questions. Returns {question_name: answer}."""
    result = _client().decisions.create(model=DECISIONS_MODEL, input=input_text, questions=questions)
    return {a.name: a for a in result.answers}


def decide_many(items: list[tuple[str, list[dict]]], *, workers: int = 8) -> list[dict[str, Any] | Exception]:
    """Run decide() over many (input, questions) pairs concurrently, preserving order."""

    def run(item: tuple[str, list[dict]]) -> Any:
        try:
            return decide(*item)
        except Exception as exc:  # surfaced per item so one failure doesn't sink a batch
            return exc

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(run, items))
