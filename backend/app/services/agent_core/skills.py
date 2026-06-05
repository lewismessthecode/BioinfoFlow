from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.utils.exceptions import NotFoundError


_FRONTMATTER_RE = re.compile(r"\A---\s*\n(?P<frontmatter>.*?)\n---\s*\n(?P<body>.*)", re.DOTALL)


@dataclass(frozen=True, slots=True)
class AgentSkillManifest:
    name: str
    version: str
    description: str
    tags: list[str]
    body: str
    path: Path


class AgentSkillRegistry:
    def __init__(self, skills: list[AgentSkillManifest]):
        self._skills = {skill.name: skill for skill in skills}

    @classmethod
    def from_directory(cls, root: Path | str) -> "AgentSkillRegistry":
        root_path = Path(root)
        skills: list[AgentSkillManifest] = []
        if not root_path.is_dir():
            return cls(skills)

        for skill_file in sorted(root_path.glob("*/SKILL.md")):
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


def _parse_skill_file(path: Path) -> AgentSkillManifest | None:
    raw = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        return None
    frontmatter = _parse_frontmatter(match.group("frontmatter"))
    name = frontmatter.get("name")
    description = frontmatter.get("description")
    if not name or not description:
        return None
    return AgentSkillManifest(
        name=name,
        version=frontmatter.get("version") or "0.1.0",
        description=description,
        tags=_parse_tags(frontmatter.get("tags")),
        body=match.group("body").strip(),
        path=path,
    )


def _parse_frontmatter(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def _parse_tags(value: str | None) -> list[str]:
    if not value:
        return []
    return [tag.strip() for tag in value.split(",") if tag.strip()]
