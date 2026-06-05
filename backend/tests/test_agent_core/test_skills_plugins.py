from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.agent_core.plugins import AgentPluginRegistry
from app.services.agent_core.skills import AgentSkillRegistry
from app.services.agent_core.tools.skills import ListPluginsTool, ListSkillsTool, LoadSkillTool
from app.services.agent_core.tools.specs import AgentToolContext
from app.workspace import DEFAULT_WORKSPACE_ID


def _write_skill(root: Path, dirname: str, frontmatter: str, body: str) -> None:
    skill_dir = root / dirname
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\n{frontmatter}\n---\n{body}\n",
        encoding="utf-8",
    )


def test_agent_skill_registry_discovers_versioned_manifests(tmp_path: Path):
    _write_skill(
        tmp_path,
        "rna-qc",
        "\n".join(
            [
                "name: rna-qc",
                "version: 1.2.0",
                "description: Summarize RNA-seq QC signals.",
                "tags: rnaseq, qc",
            ]
        ),
        "# RNA QC\nUse MultiQC and count matrix summaries.",
    )
    _write_skill(
        tmp_path,
        "bad",
        "description: Missing name.",
        "# Bad",
    )

    registry = AgentSkillRegistry.from_directory(tmp_path)

    assert [skill.name for skill in registry.list()] == ["rna-qc"]
    skill = registry.get("rna-qc")
    assert skill.version == "1.2.0"
    assert skill.description == "Summarize RNA-seq QC signals."
    assert skill.tags == ["rnaseq", "qc"]
    assert "MultiQC" in skill.body
    assert registry.describe_for_prompt() == "- rna-qc (1.2.0): Summarize RNA-seq QC signals."


def test_agent_plugin_registry_discovers_versioned_plugin_manifests(tmp_path: Path):
    plugin_dir = tmp_path / "variant-plugin" / ".bioinfoflow-plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps(
            {
                "id": "variant-tools",
                "name": "Variant Tools",
                "version": "0.3.0",
                "description": "VCF and annotation helpers.",
                "skills": ["variant-qc"],
                "tools": ["vcf.filter"],
                "enabled": True,
            }
        ),
        encoding="utf-8",
    )

    registry = AgentPluginRegistry.from_directory(tmp_path)

    assert [plugin.id for plugin in registry.list()] == ["variant-tools"]
    plugin = registry.get("variant-tools")
    assert plugin.name == "Variant Tools"
    assert plugin.version == "0.3.0"
    assert plugin.skills == ["variant-qc"]
    assert plugin.tools == ["vcf.filter"]
    assert plugin.enabled is True


@pytest.mark.asyncio
async def test_skill_and_plugin_tools_use_default_registry_roots(tmp_path: Path, monkeypatch):
    _write_skill(
        tmp_path / "skills",
        "multiqc",
        "\n".join(
            [
                "name: multiqc",
                "version: 0.1.0",
                "description: Interpret MultiQC reports.",
            ]
        ),
        "# MultiQC\nSummarize reports.",
    )
    plugin_dir = tmp_path / "plugins" / "qc-plugin" / ".bioinfoflow-plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps(
            {
                "id": "qc-plugin",
                "name": "QC Plugin",
                "version": "1.0.0",
                "description": "Quality-control helpers.",
                "skills": ["multiqc"],
            }
        ),
        encoding="utf-8",
    )

    from app.services.agent_core.tools.skills import resources

    monkeypatch.setattr(resources, "_skills_root", lambda: tmp_path / "skills")
    monkeypatch.setattr(resources, "_plugins_root", lambda: tmp_path / "plugins")

    context = AgentToolContext(
        db=None,  # type: ignore[arg-type]
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        session_id="session-1",
        turn_id="turn-1",
    )

    listed_skills = await ListSkillsTool().run({}, context)
    assert listed_skills["skills"][0]["name"] == "multiqc"

    loaded = await LoadSkillTool().run({"name": "multiqc"}, context)
    assert loaded["skill"]["body"].startswith("# MultiQC")

    listed_plugins = await ListPluginsTool().run({}, context)
    assert listed_plugins["plugins"][0]["id"] == "qc-plugin"
