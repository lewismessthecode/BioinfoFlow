from __future__ import annotations

import re
import unicodedata

from pypinyin import Style, lazy_pinyin

MAX_PROJECT_DIRECTORY_LENGTH = 100

_NON_DIRECTORY_CHARACTER = re.compile(r"[^a-z0-9]+")
_WINDOWS_RESERVED_DIRECTORY_NAMES = (
    {"con", "prn", "aux", "nul"}
    | {f"com{number}" for number in range(1, 10)}
    | {f"lpt{number}" for number in range(1, 10)}
)


def normalize_project_directory_name(project_name: str) -> str:
    """Return a readable, ASCII kebab-case directory name for a project."""
    normalized = unicodedata.normalize("NFKC", project_name)
    transliterated = " ".join(lazy_pinyin(normalized, style=Style.NORMAL))
    ascii_value = (
        unicodedata.normalize("NFKD", transliterated)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    directory_name = _NON_DIRECTORY_CHARACTER.sub("-", ascii_value.lower()).strip("-")
    if directory_name in _WINDOWS_RESERVED_DIRECTORY_NAMES:
        directory_name = f"project-{directory_name}"

    return _truncate_directory_name(directory_name) or "project"


def project_directory_candidate(project_name: str, ordinal: int = 1) -> str:
    """Return the ordinal-specific candidate directory name for a project."""
    if ordinal < 1:
        raise ValueError("ordinal must be at least 1")

    base_name = normalize_project_directory_name(project_name)
    if ordinal == 1:
        return base_name

    suffix = f"-{ordinal}"
    if len(suffix) >= MAX_PROJECT_DIRECTORY_LENGTH:
        raise ValueError("ordinal suffix exceeds the directory name length limit")

    return f"{_truncate_directory_name(base_name, MAX_PROJECT_DIRECTORY_LENGTH - len(suffix))}{suffix}"


def _truncate_directory_name(
    directory_name: str, limit: int = MAX_PROJECT_DIRECTORY_LENGTH
) -> str:
    return directory_name[:limit].rstrip("-")
