from __future__ import annotations

from pathlib import Path


_DENIED_CONTEXT_NAMES = {
    ".env",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "better-auth.db",
    "bioinfoflow.db",
    "credentials",
    "credentials.json",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
}
_DENIED_CONTEXT_DIRECTORY_NAMES = {".aws", ".ssh"}
_DENIED_CONTEXT_SUFFIXES = {
    ".db",
    ".key",
    ".pem",
    ".p12",
    ".pfx",
    ".sqlite",
    ".sqlite3",
}


def is_sensitive_context_path(path: Path) -> bool:
    """Return whether a path must not be exposed to agent context."""
    parts = {part.casefold() for part in path.parts}
    if parts & _DENIED_CONTEXT_DIRECTORY_NAMES:
        return True
    if ".config" in parts and "gcloud" in parts:
        return True

    name = path.name.casefold()
    if name in _DENIED_CONTEXT_NAMES or name.startswith(".env."):
        return True
    return path.suffix.casefold() in _DENIED_CONTEXT_SUFFIXES


def safe_manifest_paths(root: Path, manifest: list[str]) -> list[str]:
    """Remove sensitive relative paths from a persisted or local manifest."""
    return [
        relative_path
        for relative_path in manifest
        if not is_sensitive_context_path(root / relative_path)
    ]
