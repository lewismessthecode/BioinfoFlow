"""Tests for runtime/skills.py — SkillLoader discovery and content retrieval."""

from __future__ import annotations

from pathlib import Path

from app.services.agent.runtime.skills import SkillLoader


def _make_skill(skills_dir: Path, name: str, desc: str, body: str) -> None:
    """Helper: create a SKILL.md file with frontmatter."""
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: |\n  {desc}\n---\n\n{body}\n",
        encoding="utf-8",
    )


class TestSkillDiscovery:
    def test_discovers_skills(self, tmp_path: Path):
        _make_skill(tmp_path, "skill-a", "First skill desc", "# Skill A body")
        _make_skill(tmp_path, "skill-b", "Second skill desc", "# Skill B body")
        loader = SkillLoader(tmp_path)
        assert sorted(loader.names) == ["skill-a", "skill-b"]

    def test_empty_dir(self, tmp_path: Path):
        loader = SkillLoader(tmp_path)
        assert loader.names == []
        assert loader.get_descriptions() == ""

    def test_missing_dir(self, tmp_path: Path):
        loader = SkillLoader(tmp_path / "nonexistent")
        assert loader.names == []

    def test_skips_file_without_frontmatter(self, tmp_path: Path):
        skill_dir = tmp_path / "bad-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# No frontmatter here\n")
        loader = SkillLoader(tmp_path)
        assert loader.names == []


class TestSkillDescriptions:
    def test_format(self, tmp_path: Path):
        _make_skill(tmp_path, "my-skill", "Does something cool", "body")
        loader = SkillLoader(tmp_path)
        desc = loader.get_descriptions()
        assert "**my-skill**" in desc
        assert "Does something cool" in desc


class TestSkillContent:
    def test_get_content_wraps_in_tags(self, tmp_path: Path):
        _make_skill(tmp_path, "test-skill", "Test desc", "# Full body here")
        loader = SkillLoader(tmp_path)
        content = loader.get_content("test-skill")
        assert content.startswith('<skill name="test-skill">')
        assert "# Full body here" in content
        assert content.endswith("</skill>")

    def test_unknown_skill_error(self, tmp_path: Path):
        _make_skill(tmp_path, "only-skill", "Desc", "body")
        loader = SkillLoader(tmp_path)
        result = loader.get_content("nonexistent")
        assert "Unknown skill" in result
        assert "only-skill" in result  # suggests available skills
