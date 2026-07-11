"""Shared policy for platform-managed run input names."""

from __future__ import annotations


MANAGED_RUN_DIRECTORY_NAMES: frozenset[str] = frozenset(
    {"outdir", "output_dir", "publish_dir", "work_dir"}
)


def is_managed_run_directory_name(name: str) -> bool:
    """Return whether an exact input name is a managed run directory."""
    return name.lower() in MANAGED_RUN_DIRECTORY_NAMES
