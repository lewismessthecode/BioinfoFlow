"""Shared policy for detecting legacy flat run-spec keys."""

from __future__ import annotations

from collections.abc import Mapping

LEGACY_RUN_KEYS: frozenset[str] = frozenset(
    {
        "params",
        "inputs",
        "config_overrides",
        "timeout_seconds",
        "workspace",
        "submission_mode",
        "json_inputs",
        "table_rows",
    }
)


def detect_legacy_run_keys(payload: Mapping[str, object]) -> tuple[str, ...]:
    """Return legacy flat keys in deterministic order."""
    return tuple(sorted(key for key in payload if key in LEGACY_RUN_KEYS))
