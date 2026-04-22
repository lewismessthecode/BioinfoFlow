"""JSON spec input — read from --spec <file> or --spec - (stdin)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


class SpecError(Exception):
    """Invalid or unreadable spec input."""


def read_spec(spec: str | None) -> dict | None:
    """Read JSON from --spec <file>, --spec - (stdin), or None.

    Returns parsed dict or None if spec is not provided.
    Raises SpecError on invalid JSON or missing files.
    """
    if spec is None:
        return None

    if spec == "-":
        raw = sys.stdin.read()
    else:
        path = Path(spec)
        try:
            raw = path.read_text()
        except FileNotFoundError:
            raise SpecError(f"Spec file not found: {spec}") from None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SpecError(f"Invalid JSON in spec: {exc}") from exc

    if not isinstance(parsed, dict):
        raise SpecError("Spec must be a JSON object")

    return parsed


def try_parse_json(s: str) -> Any:
    """Attempt to parse a string as JSON; return original string on failure."""
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return s
