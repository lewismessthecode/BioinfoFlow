from __future__ import annotations

from dataclasses import asdict

from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.utils.exceptions import BadRequestError


class SpawnAgentTool:
    spec = AgentToolSpec(
        name="spawn_agent",
        description=(
            "Start a durable child agent asynchronously. The child cannot spawn "
            "more agents. Use followup_task to reuse a completed child."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "task_name": {"type": "string", "pattern": "^[a-z0-9_]+$"},
                "message": {"type": "string", "minLength": 1},
                "fork_turns": {"type": "string", "default": "all"},
                "model": {"type": "string"},
                "reasoning_effort": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                },
            },
            "required": ["task_name", "message"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        risk_level="act_low",
        read_scope=["agent_transcript", "model_catalog"],
        write_scope=[
            "agent_sessions",
            "agent_turns",
            "agent_messages",
            "agent_attachments",
        ],
        audit="Start a durable child agent in the current root tree.",
    )

    async def run(self, input: dict, context: AgentToolContext) -> dict:
        from app.services.agent_core.collaboration.service import (
            AgentCollaborationService,
        )

        result = await AgentCollaborationService(context.db).spawn_agent(
            parent_session_id=context.session_id,
            parent_turn_id=context.turn_id,
            task_name=input.get("task_name"),
            message=input.get("message"),
            fork_turns=input.get("fork_turns", "all"),
            model=input.get("model"),
            reasoning_effort=input.get("reasoning_effort"),
        )
        return asdict(result)


class ListAgentsTool:
    spec = AgentToolSpec(
        name="list_agents",
        description="List the durable shallow agent tree for the current root task.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_schema={"type": "object"},
        risk_level="read",
        read_scope=["agent_sessions", "agent_turns"],
        parallel_safe=True,
    )

    async def run(self, input: dict, context: AgentToolContext) -> dict:
        from app.services.agent_core.collaboration.service import (
            AgentCollaborationService,
        )

        agents = await AgentCollaborationService(context.db).list_agents(
            caller_session_id=context.session_id,
            workspace_id=context.workspace_id,
            user_id=context.user_id,
        )
        return {"agents": [asdict(agent) for agent in agents]}


class _Task4CollaborationTool:
    async def run(self, input: dict, context: AgentToolContext) -> dict:
        del input, context
        raise BadRequestError("collab_manager_unavailable")


class SendMessageTool(_Task4CollaborationTool):
    spec = AgentToolSpec(
        name="send_message",
        description="Send a durable message to an agent in the same root tree.",
        input_schema={
            "type": "object",
            "properties": {
                "target": {"type": "string", "minLength": 1},
                "message": {"type": "string", "minLength": 1},
            },
            "required": ["target", "message"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        risk_level="act_low",
        read_scope=["agent_sessions", "agent_turns"],
        write_scope=["agent_messages"],
        audit="Send a durable inter-agent message.",
    )


class FollowupTaskTool(_Task4CollaborationTool):
    spec = AgentToolSpec(
        name="followup_task",
        description="Give an existing child agent a follow-up task.",
        input_schema={
            "type": "object",
            "properties": {
                "target": {"type": "string", "minLength": 1},
                "message": {"type": "string", "minLength": 1},
            },
            "required": ["target", "message"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        risk_level="act_low",
        read_scope=["agent_sessions", "agent_turns"],
        write_scope=["agent_messages", "agent_turns", "agent_sessions"],
        audit="Queue or steer a follow-up child task.",
    )


class WaitAgentTool(_Task4CollaborationTool):
    spec = AgentToolSpec(
        name="wait_agent",
        description="Wait for agent mailbox activity, a steer, or a bounded timeout.",
        input_schema={
            "type": "object",
            "properties": {
                "timeout_ms": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 60000,
                    "default": 30000,
                }
            },
            "required": [],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        risk_level="read",
        read_scope=["agent_sessions", "agent_turns", "agent_messages"],
        write_scope=[],
        audit="Wait for durable agent mailbox activity.",
        timeout_seconds=65,
    )


class InterruptAgentTool(_Task4CollaborationTool):
    spec = AgentToolSpec(
        name="interrupt_agent",
        description="Interrupt an active child turn while keeping the child reusable.",
        input_schema={
            "type": "object",
            "properties": {"target": {"type": "string", "minLength": 1}},
            "required": ["target"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        risk_level="act_low",
        read_scope=["agent_sessions", "agent_turns"],
        write_scope=["agent_turns", "agent_sessions"],
        audit="Interrupt an active child turn.",
    )


COLLABORATION_TOOLS = (
    SpawnAgentTool(),
    SendMessageTool(),
    FollowupTaskTool(),
    WaitAgentTool(),
    ListAgentsTool(),
    InterruptAgentTool(),
)
