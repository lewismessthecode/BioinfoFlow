from __future__ import annotations

from collections.abc import Iterable

from app.services.agent_core.tools.specs import AgentTool
from app.utils.exceptions import BadRequestError, NotFoundError


class AgentToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> None:
        if tool.spec.name in self._tools:
            raise BadRequestError(f"Agent tool already registered: {tool.spec.name}")
        self._tools[tool.spec.name] = tool

    def register_many(self, tools: Iterable[AgentTool]) -> None:
        pending = list(tools)
        names = [tool.spec.name for tool in pending]
        duplicate_names = {name for name in names if names.count(name) > 1}
        duplicate_names.update(name for name in names if name in self._tools)
        if duplicate_names:
            joined = ", ".join(sorted(duplicate_names))
            raise BadRequestError(f"Agent tool already registered: {joined}")
        for tool in pending:
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
