from __future__ import annotations

from typing import Any

from app.services.agent_core.memory import AgentMemoryService
from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec


class ListMemoriesTool:
    spec = AgentToolSpec(
        name="memory.list",
        description="List structured AgentCore memories in the current workspace.",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "status": {"type": "string"},
                "scope": {"type": "string"},
                "type": {"type": "string"},
            },
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"memories": {"type": "array"}},
            "required": ["memories"],
        },
        risk_level="read",
        read_scope=["agent_memories"],
        audit="List structured agent memories.",
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        memories = await AgentMemoryService(context.db).list_memories(
            workspace_id=context.workspace_id,
            project_id=input.get("project_id"),
            status=input.get("status"),
            scope=input.get("scope"),
            type=input.get("type"),
            session_id=context.session_id,
            turn_id=context.turn_id,
        )
        return {"memories": [_memory_payload(memory) for memory in memories]}


class ProposeMemoryTool:
    spec = AgentToolSpec(
        name="memory.propose",
        description="Propose a structured memory for later human or policy confirmation.",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "scope": {"type": "string"},
                "type": {"type": "string"},
                "content": {"type": "object"},
                "source": {"type": "object"},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
            },
            "required": ["scope", "type", "content"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"memory": {"type": "object"}},
            "required": ["memory"],
        },
        risk_level="act_low",
        read_scope=["agent_memories"],
        write_scope=["agent_memories"],
        audit="Propose a structured agent memory.",
        rollback_hint="Reject or disable the memory if it is not reusable.",
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        memory = await AgentMemoryService(context.db).propose_memory(
            workspace_id=context.workspace_id,
            project_id=input.get("project_id"),
            session_id=context.session_id,
            turn_id=context.turn_id,
            scope=input["scope"],
            type=input["type"],
            content=input["content"],
            source=input.get("source"),
            confidence=input.get("confidence"),
        )
        return {"memory": _memory_payload(memory)}


def _memory_payload(memory) -> dict[str, Any]:
    return {
        "id": str(memory.id),
        "workspace_id": str(memory.workspace_id),
        "project_id": str(memory.project_id) if memory.project_id else None,
        "session_id": str(memory.session_id) if memory.session_id else None,
        "scope": memory.scope,
        "type": memory.type,
        "content": memory.content,
        "source": memory.source,
        "confidence": memory.confidence,
        "status": memory.status,
        "created_at": memory.created_at.isoformat(),
        "updated_at": memory.updated_at.isoformat(),
    }
