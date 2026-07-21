from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from app.config import settings
from app.services.agent_core.plugins import AgentPluginRegistry, register_plugin_tools
from app.services.agent_core.skills import AgentSkillRegistry
from app.services.agent_core.tools.registry import AgentToolRegistry
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
                "title: RNA QC",
                "version: 1.2.0",
                "description: Summarize RNA-seq QC signals.",
                "category: workflow",
                "tags: [rnaseq, qc]",
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
    assert skill.title == "RNA QC"
    assert skill.description == "Summarize RNA-seq QC signals."
    assert skill.category == "workflow"
    assert skill.tags == ["rnaseq", "qc"]
    assert "MultiQC" in skill.body
    assert registry.describe_for_prompt() == "- rna-qc (1.2.0): Summarize RNA-seq QC signals."


def test_agent_skill_registry_discovers_repo_and_configured_roots_with_repo_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo_root = tmp_path / "repo"
    configured_root = tmp_path / "configured-skills"
    monkeypatch.setattr(settings, "repo_root", str(repo_root))
    monkeypatch.setattr(settings, "bioinfoflow_skills_root", str(configured_root))
    _write_skill(
        repo_root / ".agents" / "skills",
        "shared-qc",
        "\n".join(
            [
                "name: shared-qc",
                "description: Repo-local QC guidance.",
            ]
        ),
        "# Repo skill\nPrefer the repo body.",
    )
    _write_skill(
        configured_root,
        "shared-qc",
        "\n".join(
            [
                "name: shared-qc",
                "description: Configured QC guidance.",
            ]
        ),
        "# Configured skill\nThis should lose precedence.",
    )
    _write_skill(
        configured_root,
        "configured-only",
        "\n".join(
            [
                "name: configured-only",
                "description: Configured-only guidance.",
            ]
        ),
        "# Configured only\nThis should still be discoverable.",
    )

    registry = AgentSkillRegistry.from_default_roots()

    assert [skill.name for skill in registry.list()] == ["configured-only", "shared-qc"]
    shared = registry.get("shared-qc")
    assert shared.source == "repo"
    assert shared.root == (repo_root / ".agents" / "skills").resolve()
    assert shared.path == (repo_root / ".agents" / "skills" / "shared-qc" / "SKILL.md").resolve()
    assert shared.description == "Repo-local QC guidance."
    assert shared.body == "# Repo skill\nPrefer the repo body."
    configured = registry.get("configured-only")
    assert configured.source == "configured"
    assert configured.root == configured_root.resolve()


def test_agent_skill_registry_prefers_yaml_frontmatter_and_keeps_simple_fallback(
    tmp_path: Path,
):
    _write_skill(
        tmp_path,
        "yaml-skill",
        "\n".join(
            [
                "name: yaml-skill",
                "title: YAML Skill",
                "version: '2.0'",
                "description: >",
                "  Summarize RNA-seq QC signals.",
                "tags:",
                "  - rnaseq",
                "  - qc",
            ]
        ),
        "# YAML\nUse folded frontmatter fields.",
    )
    _write_skill(
        tmp_path,
        "fallback-skill",
        "\n".join(
            [
                "name: fallback-skill",
                "description: Interpret samples: tumor and normal pairs.",
            ]
        ),
        "# Fallback\nUse the simple parser when YAML parsing fails.",
    )

    registry = AgentSkillRegistry.from_directory(tmp_path)

    assert [skill.name for skill in registry.list()] == ["fallback-skill", "yaml-skill"]
    yaml_skill = registry.get("yaml-skill")
    assert yaml_skill.title == "YAML Skill"
    assert yaml_skill.version == "2.0"
    assert yaml_skill.description == "Summarize RNA-seq QC signals."
    assert yaml_skill.tags == ["rnaseq", "qc"]
    fallback_skill = registry.get("fallback-skill")
    assert fallback_skill.description == "Interpret samples: tumor and normal pairs."


def test_agent_skill_registry_skips_unsafe_and_support_paths(tmp_path: Path):
    _write_skill(
        tmp_path,
        "valid-skill",
        "\n".join(
            [
                "name: valid-skill",
                "description: Safe manifest.",
            ]
        ),
        "# Valid",
    )
    _write_skill(
        tmp_path,
        "unsafe-skill",
        "\n".join(
            [
                "name: ../unsafe",
                "description: Unsafe manifest.",
            ]
        ),
        "# Unsafe",
    )
    _write_skill(
        tmp_path,
        "references",
        "\n".join(
            [
                "name: reference-note",
                "description: Should not be discovered as an active skill.",
            ]
        ),
        "# Reference",
    )

    registry = AgentSkillRegistry.from_directory(tmp_path)

    assert [skill.name for skill in registry.list()] == ["valid-skill"]


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


def test_plugin_registration_loads_python_tool_modules(tmp_path: Path):
    plugin_dir = tmp_path / "custom-plugin" / ".bioinfoflow-plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps(
            {
                "id": "custom-tools",
                "name": "Custom Tools",
                "version": "1.0.0",
                "python_modules": ["testsupport.agent_plugin_demo"],
            }
        ),
        encoding="utf-8",
    )

    module = types.ModuleType("testsupport.agent_plugin_demo")
    namespace: dict[str, object] = {}
    exec(
        "from app.services.agent_core.tools.specs import AgentToolSpec\n"
        "class DemoTool:\n"
        "    spec = AgentToolSpec(name='demo.echo', description='Echo demo', input_schema={'type':'object','properties':{},'additionalProperties':False}, output_schema={'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok']}, risk_level='read')\n"
        "    async def run(self, input, context):\n"
        "        return {'ok': True}\n"
        "def register_agent_tools(registry):\n"
        "    registry.register(DemoTool())\n",
        namespace,
    )
    module.__dict__.update(namespace)
    sys.modules[module.__name__] = module

    registry = AgentToolRegistry()
    loaded = register_plugin_tools(registry, root=tmp_path)

    assert registry.get("demo.echo").spec.name == "demo.echo"
    assert loaded == ["custom-tools:testsupport.agent_plugin_demo"]


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
    assert loaded["skill"]["directory"] == str((tmp_path / "skills" / "multiqc").resolve())

    listed_plugins = await ListPluginsTool().run({}, context)
    assert listed_plugins["plugins"][0]["id"] == "qc-plugin"


@pytest.mark.asyncio
async def test_skill_tools_use_repo_scoped_registry_with_debug_payloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo_root = tmp_path / "repo"
    configured_root = tmp_path / "configured-skills"
    repo_skills_root = repo_root / ".agents" / "skills"
    monkeypatch.setattr(settings, "repo_root", str(repo_root))
    monkeypatch.setattr(settings, "bioinfoflow_skills_root", str(configured_root))
    _write_skill(
        repo_skills_root,
        "shared-qc",
        "\n".join(
            [
                "name: shared-qc",
                "description: Repo scoped QC guidance.",
            ]
        ),
        "# Repo\nUse this body.",
    )
    _write_skill(
        configured_root,
        "shared-qc",
        "\n".join(
            [
                "name: shared-qc",
                "description: Configured QC guidance.",
            ]
        ),
        "# Configured\nThis body loses precedence.",
    )
    _write_skill(
        configured_root,
        "configured-only",
        "\n".join(
            [
                "name: configured-only",
                "description: Configured-only guidance.",
            ]
        ),
        "# Configured only",
    )

    context = AgentToolContext(
        db=None,  # type: ignore[arg-type]
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        session_id="session-1",
        turn_id="turn-1",
    )

    listed = await ListSkillsTool().run({}, context)

    assert listed["skills"] == [
        {
            "name": "configured-only",
            "title": None,
            "version": "0.1.0",
            "description": "Configured-only guidance.",
            "category": None,
            "tags": [],
                "source": "configured",
                "root": str(configured_root.resolve()),
                "path": str(configured_root / "configured-only" / "SKILL.md"),
                "directory": str((configured_root / "configured-only").resolve()),
        },
        {
            "name": "shared-qc",
            "title": None,
            "version": "0.1.0",
            "description": "Repo scoped QC guidance.",
            "category": None,
            "tags": [],
                "source": "repo",
                "root": str(repo_skills_root.resolve()),
                "path": str(repo_skills_root / "shared-qc" / "SKILL.md"),
                "directory": str((repo_skills_root / "shared-qc").resolve()),
        },
    ]

    loaded = await LoadSkillTool().run({"name": "shared-qc"}, context)
    assert loaded["skill"]["source"] == "repo"
    assert loaded["skill"]["root"] == str(repo_skills_root.resolve())
    assert loaded["skill"]["body"] == "# Repo\nUse this body."
