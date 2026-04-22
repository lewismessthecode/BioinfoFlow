"""Skill discovery and on-demand loading (s05-s06 pattern).

Two-layer injection:
  Layer 1 — Short descriptions injected into the system prompt (~100 tokens/skill).
  Layer 2 — Full body loaded on-demand via the ``load_skill`` tool.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.utils.logging import get_logger

logger = get_logger(__name__)

_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n(.*)",
    re.DOTALL,
)
_NAME_RE = re.compile(r"^name:\s*(.+)$", re.MULTILINE)
_DESC_RE = re.compile(r"^description:\s*\|?\s*\n((?:[ \t]+.+\n?)+)", re.MULTILINE)


class SkillLoader:
    """Discovers ``SKILL.md`` files and provides layered access to their content."""

    def __init__(self, skills_dir: Path) -> None:
        self._skills_dir = skills_dir
        # name -> (first_line_description, full_body)
        self._skills: dict[str, tuple[str, str]] = {}
        self._discover()

    def _discover(self) -> None:
        """Walk *skills_dir*/*/SKILL.md and parse frontmatter."""
        if not self._skills_dir.is_dir():
            logger.info("skills.dir_missing", path=str(self._skills_dir))
            return

        for skill_file in sorted(self._skills_dir.glob("*/SKILL.md")):
            raw = skill_file.read_text(encoding="utf-8")
            match = _FRONTMATTER_RE.match(raw)
            if not match:
                logger.warning("skills.no_frontmatter", file=str(skill_file))
                continue

            frontmatter, body = match.group(1), match.group(2)

            name_match = _NAME_RE.search(frontmatter)
            if not name_match:
                logger.warning("skills.no_name", file=str(skill_file))
                continue
            name = name_match.group(1).strip()

            desc_match = _DESC_RE.search(frontmatter)
            first_line = ""
            if desc_match:
                desc_block = desc_match.group(1)
                first_line = desc_block.strip().split("\n")[0].strip()

            self._skills[name] = (first_line, body.strip())

        logger.info("skills.discovered", count=len(self._skills))

    @property
    def names(self) -> list[str]:
        """Return all discovered skill names."""
        return list(self._skills.keys())

    def get_descriptions(self) -> str:
        """Layer 1: short descriptions for system prompt injection."""
        if not self._skills:
            return ""
        lines = []
        for name, (first_line, _body) in self._skills.items():
            lines.append(f"- **{name}**: {first_line}")
        return "\n".join(lines)

    def get_content(self, name: str) -> str:
        """Layer 2: full skill body wrapped in ``<skill>`` tags."""
        entry = self._skills.get(name)
        if entry is None:
            available = ", ".join(self._skills.keys()) or "(none)"
            return f"Unknown skill '{name}'. Available: {available}"
        _desc, body = entry
        return f'<skill name="{name}">\n{body}\n</skill>'
