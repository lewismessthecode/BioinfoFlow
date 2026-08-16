from __future__ import annotations

from collections.abc import Iterable


_TITLE_MAX_LENGTH = 30
_TRIM_CHARACTERS = "'\"`*_#> "
_TRAILING_PUNCTUATION = " ,.;:，。；："


def derive_automatic_session_title(text_parts: Iterable[str]) -> str | None:
    """Derive a stable sidebar title without mutating conversation context."""

    for text in text_parts:
        compact = " ".join(text.strip().split()).strip(_TRIM_CHARACTERS)
        if not compact:
            continue
        if len(compact) <= _TITLE_MAX_LENGTH:
            return compact
        candidate = compact[:_TITLE_MAX_LENGTH].rstrip(_TRAILING_PUNCTUATION)
        if " " in candidate:
            boundary = candidate.rfind(" ")
            if boundary >= 12:
                candidate = candidate[:boundary]
        return candidate or compact[:_TITLE_MAX_LENGTH]
    return None


__all__ = ["derive_automatic_session_title"]
