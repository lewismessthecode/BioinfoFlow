from __future__ import annotations

from app.services.agent_core.tools.registry import AgentToolRegistry
from app.utils.exceptions import PermissionDeniedError


class ReadOnlySubagentRunner:
    def __init__(self, registry: AgentToolRegistry):
        self.registry = registry

    async def analyze(
        self,
        *,
        task: str,
        context: dict | None = None,
        allowed_tools: list[str] | None = None,
    ) -> dict:
        tool_names = allowed_tools or self._default_read_only_tools()
        for tool_name in tool_names:
            tool = self.registry.get(tool_name)
            if tool.spec.write_scope or tool.spec.risk_level != "read":
                raise PermissionDeniedError(
                    f"Read-only subagent cannot use write-capable tool: {tool_name}"
                )

        return {
            "mode": "read_only",
            "task": task,
            "context": context or {},
            "allowed_tools": tool_names,
            "write_handoff_required": True,
            "handoff_contract": {
                "write_operations": "return_to_main_agent_action_ledger",
                "artifacts": "return_as_summary_or_file_refs",
            },
        }

    def _default_read_only_tools(self) -> list[str]:
        return [
            spec.name
            for spec in self.registry.list_specs()
            if not spec.write_scope and spec.risk_level == "read"
        ]
