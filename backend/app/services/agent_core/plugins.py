from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.utils.exceptions import NotFoundError


@dataclass(frozen=True, slots=True)
class AgentPluginManifest:
    id: str
    name: str
    version: str
    description: str
    skills: list[str]
    tools: list[str]
    python_modules: list[str]
    enabled: bool
    path: Path


class AgentPluginRegistry:
    def __init__(self, plugins: list[AgentPluginManifest]):
        self._plugins = {plugin.id: plugin for plugin in plugins}

    @classmethod
    def from_directory(cls, root: Path | str) -> "AgentPluginRegistry":
        root_path = Path(root)
        plugins: list[AgentPluginManifest] = []
        if not root_path.is_dir():
            return cls(plugins)

        manifest_paths = [
            *root_path.glob("*/.bioinfoflow-plugin/plugin.json"),
            *root_path.glob("*/plugin.json"),
        ]
        for manifest_path in sorted(set(manifest_paths)):
            plugin = _parse_plugin_file(manifest_path)
            if plugin is not None:
                plugins.append(plugin)
        return cls(plugins)

    def list(self, *, include_disabled: bool = False) -> list[AgentPluginManifest]:
        plugins = sorted(self._plugins.values(), key=lambda plugin: plugin.id)
        if include_disabled:
            return plugins
        return [plugin for plugin in plugins if plugin.enabled]

    def get(self, plugin_id: str) -> AgentPluginManifest:
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            raise NotFoundError(f"Agent plugin not found: {plugin_id}")
        return plugin


def register_plugin_tools(registry, *, root: Path | str) -> list[str]:
    loaded_modules: list[str] = []
    for plugin in AgentPluginRegistry.from_directory(root).list():
        for module_name in plugin.python_modules:
            module = _load_plugin_module(module_name)
            register = getattr(module, "register_agent_tools", None)
            if callable(register):
                register(registry)
                loaded_modules.append(f"{plugin.id}:{module_name}")
    return loaded_modules


def _parse_plugin_file(path: Path) -> AgentPluginManifest | None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    plugin_id = _as_str(raw.get("id"))
    name = _as_str(raw.get("name"))
    version = _as_str(raw.get("version"))
    if not plugin_id or not name or not version:
        return None
    python_modules = _as_str_list(raw.get("python_modules"))
    single_module = _as_str(raw.get("python_module"))
    if single_module and single_module not in python_modules:
        python_modules.append(single_module)
    return AgentPluginManifest(
        id=plugin_id,
        name=name,
        version=version,
        description=_as_str(raw.get("description")) or "",
        skills=_as_str_list(raw.get("skills")),
        tools=_as_str_list(raw.get("tools")),
        python_modules=python_modules,
        enabled=bool(raw.get("enabled", True)),
        path=path,
    )


def _load_plugin_module(module_name: str):
    return importlib.import_module(module_name)


def _as_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]
