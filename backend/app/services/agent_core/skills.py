from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import settings
from app.utils.exceptions import NotFoundError

try:
    import yaml
except ImportError:  # pragma: no cover - fallback parser remains available
    yaml = None

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(?P<frontmatter>.*?)\n---\s*\n(?P<body>.*)", re.DOTALL)
_SAFE_SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
SKILL_PROMPT_SUMMARY_BUDGET_CHARS = 8000
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
    source: str = "configured"
    root: Path | None = None


class AgentSkillRegistry:
    def __init__(self, skills: list[AgentSkillManifest]):
        self._skills: dict[str, AgentSkillManifest] = {}
        for skill in skills:
            self._skills.setdefault(skill.name, skill)

    @classmethod
    def from_directory(
        cls,
        root: Path | str,
        *,
        source: str = "configured",
    ) -> "AgentSkillRegistry":
        return cls(_discover_skills(root, source=source))

    @classmethod
    def from_roots(
        cls,
        *,
        repo_root: Path | str | None = None,
        configured_root: Path | str | None = None,
    ) -> "AgentSkillRegistry":
        skills: list[AgentSkillManifest] = []
        if repo_root is not None:
            skills.extend(
                _discover_skills(
                    Path(repo_root).expanduser() / ".agents" / "skills",
                    source="repo",
                )
            )
        if configured_root is not None:
            skills.extend(_discover_skills(configured_root, source="configured"))
        return cls(skills)

    @classmethod
    def from_default_roots(cls) -> "AgentSkillRegistry":
        return cls.from_roots(
            repo_root=settings.repo_root,
            configured_root=settings.skills_root,
        )

    def list(self) -> list[AgentSkillManifest]:
        return sorted(self._skills.values(), key=lambda skill: skill.name)

    def get(self, name: str) -> AgentSkillManifest:
        skill = self._skills.get(name)
        if skill is None:
            raise NotFoundError(f"Agent skill not found: {name}")
        return skill

    def describe_for_prompt(self, *, max_chars: int | None = None) -> str:
        lines = [
            f"- {skill.name} ({skill.version}): {skill.description}"
            for skill in self.list()
        ]
        if max_chars is None:
            return "\n".join(lines)
        return _join_lines_with_budget(lines, max_chars=max_chars)


class ActiveSkillResolutionError(ValueError):
    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__(f"Unknown agent skill(s): {', '.join(missing)}")


def _discover_skills(
    root: Path | str,
    *,
    source: str,
) -> list[AgentSkillManifest]:
    root_path = Path(root).expanduser()
    skills: list[AgentSkillManifest] = []
    if not root_path.is_dir():
        return skills

    root_resolved = root_path.resolve()
    for skill_file in sorted(root_path.glob("*/SKILL.md")):
        if _is_excluded_skill_path(skill_file):
            continue
        try:
            if not skill_file.resolve().is_relative_to(root_resolved):
                continue
        except OSError:
            continue
        skill = _parse_skill_file(
            skill_file,
            source=source,
            root=root_resolved,
        )
        if skill is not None:
            skills.append(skill)
    return skills


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


def _join_lines_with_budget(lines: list[str], *, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    accepted: list[str] = []
    used_chars = 0
    for line in lines:
        separator_chars = 1 if accepted else 0
        next_chars = separator_chars + len(line)
        if used_chars + next_chars > max_chars:
            if not accepted:
                return line[:max_chars]
            break
        accepted.append(line)
        used_chars += next_chars
    return "\n".join(accepted)


def _parse_skill_file(
    path: Path,
    *,
    source: str,
    root: Path,
) -> AgentSkillManifest | None:
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
        path=path.resolve(),
        source=source,
        root=root,
    )


def _parse_frontmatter(text: str) -> dict[str, Any]:
    if yaml is not None:
        try:
            loaded = yaml.safe_load(text)
        except yaml.YAMLError:
            loaded = None
        if isinstance(loaded, dict):
            return loaded
    return _parse_simple_frontmatter(text)


def _parse_simple_frontmatter(text: str) -> dict[str, Any]:
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
    if value is None:
        return None
    if isinstance(value, str):
        text = value
    elif isinstance(value, int | float):
        text = str(value)
    else:
        return None
    if text.strip():
        return text.strip().strip('"\'')
    return None


def _is_excluded_skill_path(path: Path) -> bool:
    parts = set(path.parts)
    if parts & _EXCLUDED_SKILL_DIRS:
        return True
    return path.parent.name in _SUPPORT_DIRS
