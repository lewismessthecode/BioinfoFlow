from __future__ import annotations

from pathlib import Path
from typing import Any

from app.path_layout import state_root
from app.services.agent_core.plugins import AgentPluginRegistry
from app.services.agent_core.skills import AgentSkillRegistry
from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec


class ListSkillsTool:
    spec = AgentToolSpec(
        name="skills.list",
        description="List AgentCore skill manifests available to the runtime.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_schema={
            "type": "object",
            "properties": {"skills": {"type": "array"}},
            "required": ["skills"],
        },
        risk_level="read",
        read_scope=["agent_skills"],
        audit="List AgentCore skill manifests.",
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        del input, context
        registry = AgentSkillRegistry.from_directory(_skills_root())
        return {"skills": [_skill_payload(skill) for skill in registry.list()]}


class LoadSkillTool:
    spec = AgentToolSpec(
        name="skills.load",
        description="Load the full body for one AgentCore skill manifest.",
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"skill": {"type": "object"}},
            "required": ["skill"],
        },
        risk_level="read",
        read_scope=["agent_skills"],
        audit="Load one AgentCore skill body.",
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        del context
        registry = AgentSkillRegistry.from_directory(_skills_root())
        skill = registry.get(input["name"])
        return {"skill": _skill_payload(skill, include_body=True)}


class ListPluginsTool:
    spec = AgentToolSpec(
        name="plugins.list",
        description="List AgentCore plugin manifests available to the runtime.",
        input_schema={
            "type": "object",
            "properties": {"include_disabled": {"type": "boolean"}},
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"plugins": {"type": "array"}},
            "required": ["plugins"],
        },
        risk_level="read",
        read_scope=["agent_plugins"],
        audit="List AgentCore plugin manifests.",
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        del context
        registry = AgentPluginRegistry.from_directory(_plugins_root())
        return {
            "plugins": [
                _plugin_payload(plugin)
                for plugin in registry.list(
                    include_disabled=bool(input.get("include_disabled", False))
                )
            ]
        }


def _skills_root() -> Path:
    return state_root() / "agent_core" / "skills"


def _plugins_root() -> Path:
    return state_root() / "agent_core" / "plugins"


def _skill_payload(skill, *, include_body: bool = False) -> dict[str, Any]:
    payload = {
        "name": skill.name,
        "version": skill.version,
        "description": skill.description,
        "tags": skill.tags,
        "path": str(skill.path),
    }
    if include_body:
        payload["body"] = skill.body
    return payload


def _plugin_payload(plugin) -> dict[str, Any]:
    return {
        "id": plugin.id,
        "name": plugin.name,
        "version": plugin.version,
        "description": plugin.description,
        "skills": plugin.skills,
        "tools": plugin.tools,
        "enabled": plugin.enabled,
        "path": str(plugin.path),
    }
