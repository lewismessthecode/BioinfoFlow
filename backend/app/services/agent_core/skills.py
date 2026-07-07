from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.utils.exceptions import NotFoundError

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(?P<frontmatter>.*?)\n---\s*\n(?P<body>.*)", re.DOTALL)
_SAFE_SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_EXCLUDED_SKILL_DIRS = frozenset(
    {
        ".git",
        ".github",
        ".hub",
        ".archive",
        ".venv",
        "venv",
        "node_modules",
        "site-packages",
        "__pycache__",
        ".tox",
        ".nox",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
)
_SUPPORT_DIRS = frozenset({"references", "templates", "assets", "scripts"})


@dataclass(frozen=True, slots=True)
class AgentSkillManifest:
    name: str
    version: str
    description: str
    tags: list[str]
    body: str
    path: Path
    title: str | None = None
    category: str | None = None


class AgentSkillRegistry:
    def __init__(self, skills: list[AgentSkillManifest]):
        self._skills: dict[str, AgentSkillManifest] = {}
        for skill in skills:
            self._skills.setdefault(skill.name, skill)

    @classmethod
    def from_directory(cls, root: Path | str) -> "AgentSkillRegistry":
        root_path = Path(root).expanduser()
        skills: list[AgentSkillManifest] = []
        if not root_path.is_dir():
            return cls(skills)

        root_resolved = root_path.resolve()
        for skill_file in sorted(root_path.glob("*/SKILL.md")):
            if _is_excluded_skill_path(skill_file):
                continue
            try:
                if not skill_file.resolve().is_relative_to(root_resolved):
                    continue
            except OSError:
                continue
            skill = _parse_skill_file(skill_file)
            if skill is not None:
                skills.append(skill)
        return cls(skills)

    def list(self) -> list[AgentSkillManifest]:
        return sorted(self._skills.values(), key=lambda skill: skill.name)

    def get(self, name: str) -> AgentSkillManifest:
        skill = self._skills.get(name)
        if skill is None:
            raise NotFoundError(f"Agent skill not found: {name}")
        return skill

    def describe_for_prompt(self) -> str:
        return "\n".join(
            f"- {skill.name} ({skill.version}): {skill.description}"
            for skill in self.list()
        )


class ActiveSkillResolutionError(ValueError):
    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__(f"Unknown agent skill(s): {', '.join(missing)}")


def is_safe_skill_name(value: str) -> bool:
    return bool(_SAFE_SKILL_NAME_RE.fullmatch(value))


def normalize_skill_names(values: list[str] | None) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        if not isinstance(value, str):
            continue
        name = value.strip()
        if not name or name in seen:
            continue
        if not is_safe_skill_name(name):
            raise ValueError(f"Invalid agent skill name: {name}")
        seen.add(name)
        names.append(name)
    return names


def resolve_active_skills(
    registry: AgentSkillRegistry, values: list[str] | None
) -> list[AgentSkillManifest]:
    names = normalize_skill_names(values)
    skills: list[AgentSkillManifest] = []
    missing: list[str] = []
    for name in names:
        try:
            skills.append(registry.get(name))
        except NotFoundError:
            missing.append(name)
    if missing:
        raise ActiveSkillResolutionError(missing)
    return skills


def _parse_skill_file(path: Path) -> AgentSkillManifest | None:
    raw = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        return None
    frontmatter = _parse_frontmatter(match.group("frontmatter"))
    name = _as_str(frontmatter.get("name"))
    description = _as_str(frontmatter.get("description"))
    if not name or not description or not is_safe_skill_name(name):
        return None
    return AgentSkillManifest(
        name=name,
        title=_as_str(frontmatter.get("title")),
        version=_as_str(frontmatter.get("version")) or "0.1.0",
        description=description,
        category=_as_str(frontmatter.get("category")),
        tags=_parse_tags(frontmatter.get("tags")),
        body=match.group("body").strip(),
        path=path,
    )


def _parse_frontmatter(text: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    current_key: str | None = None
    current_items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if current_key and stripped.startswith("-"):
            current_items.append(stripped[1:].strip())
            continue
        if current_key:
            values[current_key] = current_items
            current_key = None
            current_items = []
        if not stripped or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value:
            values[key] = value
        else:
            current_key = key
            current_items = []
    if current_key:
        values[current_key] = current_items
    return values


def _parse_tags(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [_clean_tag(item) for item in value if _clean_tag(item)]
    raw = str(value).strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return [_clean_tag(tag) for tag in raw.split(",") if _clean_tag(tag)]


def _clean_tag(value: Any) -> str:
    return str(value).strip().strip('"\'')


def _as_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip().strip('"\'')
    return None


def _is_excluded_skill_path(path: Path) -> bool:
    parts = set(path.parts)
    if parts & _EXCLUDED_SKILL_DIRS:
        return True
    return path.parent.name in _SUPPORT_DIRS
