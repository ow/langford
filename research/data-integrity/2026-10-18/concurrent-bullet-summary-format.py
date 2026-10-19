"""Canonical storage format for the public meeting summary: a Markdown bullet list."""

import re


def normalize_meeting_summary(value: str) -> str:
    """Light cleanup only — keep the model's bullets, drop wrappers and noise.

    Strips code fences and bold markers, unifies bullet markers to "- ", and
    drops blank lines. Does not rewrite or merge content.
    """
    text = value.strip()
    text = re.sub(r"^```(?:markdown|md|text)?\s*\n?|\n?```$", "", text).strip()
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^(?:[-*•]|\d+[.)])\s+", "- ", line)
        lines.append(line)
    return "\n".join(lines)
