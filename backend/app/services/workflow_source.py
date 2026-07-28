from __future__ import annotations

from urllib.parse import urlparse


def resolve_wdl_source_reference(
    source_ref: str,
    *,
    source: str,
    version: str | None,
    entrypoint_relpath: str | None,
) -> str:
    """Resolve a stored GitHub repository reference to its raw WDL entrypoint."""
    reference = str(source_ref or "").strip()
    if source != "github":
        return reference

    parsed = urlparse(reference)
    if parsed.hostname != "github.com":
        return reference
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) != 2:
        return reference

    owner, repository = parts
    repository = repository.removesuffix(".git")
    revision = str(version or "main").strip() or "main"
    entrypoint = str(entrypoint_relpath or "workflow.wdl").strip().lstrip("/")
    return (
        f"https://raw.githubusercontent.com/{owner}/{repository}/"
        f"{revision}/{entrypoint}"
    )
