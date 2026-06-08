from __future__ import annotations

from app.services.agent_core.tools.specs import AgentTool
from app.utils.exceptions import NotFoundError


class AgentToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> None:
        self._tools[tool.spec.name] = tool

    def get(self, name: str) -> AgentTool:
        tool = self._tools.get(name)
        if tool is None:
            raise NotFoundError(f"Agent tool not found: {name}")
        return tool

    def list_specs(self):
        return [tool.spec for tool in self._tools.values()]

    def names(self) -> set[str]:
        return set(self._tools)
