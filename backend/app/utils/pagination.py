from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any


def _add_padding(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return value + padding


def encode_cursor(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def decode_cursor(cursor: str) -> dict[str, Any]:
    decoded = base64.urlsafe_b64decode(_add_padding(cursor))
    return json.loads(decoded.decode("utf-8"))


def normalize_cursor_value(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return value
    return value
