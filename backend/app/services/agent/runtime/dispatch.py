"""Unified tool dispatch map.

Wraps ``BaseTool`` instances and inline domain handlers into a single
``dict[str, ToolEntry]`` with uniform handler signatures, OpenAI function
calling format schemas, timing, truncation, and error handling.
"""

from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Awaitable

from app.services.agent.tools import (
    RiskLevel,
    get_all_tools,
)
from app.utils.logging import get_logger

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.agent.runtime.background import BackgroundManager
    from app.services.agent.runtime.llm_client import LLMClient
    from app.services.agent.runtime.session_state import SessionState
    from app.services.agent.runtime.skills import SkillLoader
    from app.services.agent.runtime.tasks import TaskManager
    from app.services.agent.runtime.todo import TodoManager

logger = get_logger(__name__)

MAX_TOOL_OUTPUT_CHARS = 50_000


@dataclass
class ToolEntry:
    """A single tool in the dispatch map."""

    handler: Callable[..., Awaitable[str]]
    schema: dict[
        str, Any
    ]  # OpenAI function calling format: {type, function: {name, description, parameters}}
    risk_level: str
    # Optional per-invocation resolver. When set, the agent loop calls this
    # with the concrete tool input and uses the returned risk level instead
    # of the static class-level ``risk_level`` above. Tools use this to
    # self-downgrade for obviously safe inputs (e.g. shell tool: "git status"
    # is ACT_LOW, arbitrary commands stay ACT_HIGH).
    risk_resolver: Callable[[dict[str, Any]], str] | None = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_dispatch_map(
    session: "AsyncSession",
    *,
    project_id: str,
    workspace_root: "Path | None" = None,
    allow_workspace_tools: bool = True,
    todo_manager: "TodoManager | None" = None,
    skill_loader: "SkillLoader | None" = None,
    task_manager: "TaskManager | None" = None,
    background_manager: "BackgroundManager | None" = None,
    user_id: str | None = None,
    workspace_id: str | None = None,
) -> dict[str, ToolEntry]:
    """Build the complete tool dispatch map.

    Includes:
    - All registered BaseTool instances (file, glob, grep, shell, web_search,
      platform_* first-class platform adapters, etc.)
    - Runtime tools (todo_write, compact, load_skill, task_*, background_run)

    Platform operations (projects, workflows, runs) are exposed as
    ``platform_*`` tools that delegate directly to the service layer. The
    shell tool is kept as a last-resort for unrecognised one-offs only.
    """
    dispatch: dict[str, ToolEntry] = {}

    # --- Registered BaseTool instances ---
    for tool in get_all_tools(
        session,
        project_id=project_id,
        workspace_root=workspace_root,
        allow_workspace_tools=allow_workspace_tools,
        user_id=user_id,
        workspace_id=workspace_id,
    ):
        _register_base_tool(dispatch, tool)

    # --- Runtime tools ---
    if todo_manager is not None:

        async def _todo_handler(items: list[dict[str, Any]]) -> str:
            return todo_manager.update(items)

        _register(
            dispatch,
            "todo_write",
            _TODO_DESC,
            _TODO_SCHEMA,
            RiskLevel.READ,
            _todo_handler,
        )

    async def _compact_handler() -> str:
        return "Context compaction requested. Will be applied before the next LLM call."

    _register(
        dispatch,
        "compact",
        _COMPACT_DESC,
        _EMPTY_SCHEMA,
        RiskLevel.READ,
        _compact_handler,
    )

    # --- Phase 2 tools ---
    if skill_loader is not None:
        _register(
            dispatch,
            "load_skill",
            _SKILL_DESC,
            _SKILL_SCHEMA,
            RiskLevel.READ,
            skill_loader.get_content,
        )
    if task_manager is not None:
        _register_task_tools(dispatch, task_manager)
    if allow_workspace_tools and background_manager is not None:

        async def _bg_handler(command: str) -> str:
            task_id = background_manager.spawn(command)
            return json.dumps({"task_id": task_id, "status": "running"})

        _register(
            dispatch,
            "background_run",
            _BG_DESC,
            _BG_SCHEMA,
            RiskLevel.ACT_HIGH,
            _bg_handler,
        )

    logger.info("dispatch.built", tool_count=len(dispatch), tools=list(dispatch.keys()))
    return dispatch


def get_tool_schemas(dispatch_map: dict[str, ToolEntry]) -> list[dict[str, Any]]:
    """Extract OpenAI function calling format tool schemas from the dispatch map."""
    return [entry.schema for entry in dispatch_map.values()]


# ---------------------------------------------------------------------------
# Schema helpers and tool definitions (data only)
# ---------------------------------------------------------------------------

_EMPTY_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}
_STATUS_ENUM = {"type": "string", "enum": ["pending", "in_progress", "completed"]}


def _json_schema_object(
    props: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    """Shorthand for a JSON Schema ``object`` with typed properties."""
    schema: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


_COMPACT_DESC = (
    "Compact the conversation context to save tokens. "
    "Use when the conversation is getting long and you need to free up context space. "
    "Saves transcript to disk and summarizes the conversation."
)
_TODO_DESC = (
    "Update the session todo list. Replaces the entire list. "
    "Each item: {id, text, status}. Status: pending|in_progress|completed. "
    "Max 1 item may be in_progress at a time."
)
_TODO_SCHEMA = _json_schema_object(
    {
        "items": {
            "type": "array",
            "items": _json_schema_object(
                {
                    "id": {"type": "string"},
                    "text": {"type": "string"},
                    "status": _STATUS_ENUM,
                },
                required=["id", "text", "status"],
            ),
        }
    },
    required=["items"],
)

_SKILL_DESC = (
    "Load full content of a skill by name. "
    "Returns detailed instructions and examples for the requested skill."
)
_SKILL_SCHEMA = _json_schema_object(
    {"name": {"type": "string", "description": "Skill name to load"}},
    required=["name"],
)
_BG_DESC = (
    "Run a shell command in the background. "
    "Returns a task ID. Results are delivered automatically between rounds."
)
_BG_SCHEMA = _json_schema_object(
    {"command": {"type": "string", "description": "Shell command to run"}},
    required=["command"],
)

_TASK_CREATE_SCHEMA = _json_schema_object(
    {
        "subject": {"type": "string", "description": "Brief task title"},
        "description": {"type": "string", "description": "Detailed description"},
    },
    required=["subject"],
)
_TASK_UPDATE_SCHEMA = _json_schema_object(
    {
        "task_id": {"type": "string"},
        "status": _STATUS_ENUM,
        "subject": {"type": "string"},
        "description": {"type": "string"},
        "add_blocked_by": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Task IDs that must complete before this one",
        },
        "add_blocks": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Task IDs that this task blocks",
        },
        "owner": {"type": "string"},
    },
    required=["task_id"],
)
_TASK_GET_SCHEMA = _json_schema_object(
    {"task_id": {"type": "string"}}, required=["task_id"]
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _wrap_handler(
    name: str, handler: Callable[..., Awaitable[Any]]
) -> Callable[..., Awaitable[str]]:
    """Wrap a raw handler with timing, truncation, and error handling."""

    async def wrapped(**kwargs: Any) -> str:
        start = time.perf_counter()
        status = "ok"
        try:
            result = await handler(**kwargs)
            output = _serialize_result(result)
            if len(output) > MAX_TOOL_OUTPUT_CHARS:
                output = output[:MAX_TOOL_OUTPUT_CHARS] + "\n...[truncated]"
            return output
        except Exception as exc:
            status = "error"
            logger.warning("dispatch.tool_error", tool=name, error=str(exc))
            return json.dumps({"error": str(exc)})
        finally:
            elapsed = (time.perf_counter() - start) * 1000
            logger.info(
                "dispatch.tool_call",
                tool=name,
                elapsed_ms=round(elapsed, 2),
                status=status,
            )

    return wrapped


def _serialize_result(result: Any) -> str:
    """Serialize a tool result to string."""
    if isinstance(result, str):
        return result
    if hasattr(result, "to_dict"):
        return json.dumps(result.to_dict(), ensure_ascii=False, default=str)
    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(result)


def _register(
    dispatch: dict[str, ToolEntry],
    name: str,
    description: str,
    input_schema: dict[str, Any],
    risk_level: str,
    handler: Callable[..., Awaitable[Any]],
) -> None:
    """Register a single tool with standard wrapping."""
    dispatch[name] = ToolEntry(
        handler=_wrap_handler(name, handler),
        schema={
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": input_schema,
            },
        },
        risk_level=risk_level,
    )


# ---------------------------------------------------------------------------
# Registration functions
# ---------------------------------------------------------------------------


def _register_base_tool(dispatch: dict[str, ToolEntry], tool: Any) -> None:
    """Register a BaseTool instance into the dispatch map."""

    async def handler(**kwargs: Any) -> Any:
        return await tool.execute(**kwargs)

    defn = tool.get_definition()
    raw_args = defn.get("args", {})
    # Wrap bare properties dict in a proper JSON Schema object.
    # BaseTool.get_schema() returns {"param": {"type": ...}, ...} directly;
    # Gemini/Vertex AI requires {"type": "object", "properties": {...}}.
    # Deep-copy so mutation (pop("required")) below doesn't corrupt the
    # tool's cached schema — some BaseTool subclasses return a shared dict.
    if raw_args and "type" not in raw_args:
        args_copy = copy.deepcopy(raw_args)
        required = [k for k, v in args_copy.items() if v.pop("required", False)]
        params = _json_schema_object(args_copy, required or None)
    else:
        params = raw_args or _EMPTY_SCHEMA
    dispatch[tool.name] = ToolEntry(
        handler=_wrap_handler(tool.name, handler),
        schema={
            "type": "function",
            "function": {
                "name": defn["name"],
                "description": defn["description"],
                "parameters": params,
            },
        },
        risk_level=getattr(tool, "risk_level", RiskLevel.READ),
        risk_resolver=getattr(tool, "effective_risk_level", None),
    )


def _register_task_tools(
    dispatch: dict[str, ToolEntry], task_manager: "TaskManager"
) -> None:
    """Register the four task management tools."""

    async def create_handler(subject: str, description: str = "") -> str:
        return task_manager.create(subject=subject, description=description)

    async def update_handler(
        task_id: str,
        status: str | None = None,
        subject: str | None = None,
        description: str | None = None,
        add_blocked_by: list[str] | None = None,
        add_blocks: list[str] | None = None,
        owner: str | None = None,
    ) -> str:
        return task_manager.update(
            task_id=task_id,
            status=status,
            subject=subject,
            description=description,
            add_blocked_by=add_blocked_by,
            add_blocks=add_blocks,
            owner=owner,
        )

    async def get_handler(task_id: str) -> str:
        return task_manager.get(task_id)

    async def list_handler() -> str:
        return task_manager.list_all()

    _register(
        dispatch,
        "task_create",
        "Create a new task. Returns the task ID.",
        _TASK_CREATE_SCHEMA,
        RiskLevel.READ,
        create_handler,
    )
    _register(
        dispatch,
        "task_update",
        "Update a task's status, subject, description, dependencies, or owner.",
        _TASK_UPDATE_SCHEMA,
        RiskLevel.READ,
        update_handler,
    )
    _register(
        dispatch,
        "task_get",
        "Get full details of a task by ID.",
        _TASK_GET_SCHEMA,
        RiskLevel.READ,
        get_handler,
    )
    _register(
        dispatch,
        "task_list",
        "List all tasks with summary info.",
        _EMPTY_SCHEMA,
        RiskLevel.READ,
        list_handler,
    )


def register_task_tool(
    dispatch: dict[str, ToolEntry],
    *,
    session_state: "SessionState",
    llm: "LLMClient",
    system_prompt_factory: Callable[[], str],
    db_session: "AsyncSession | None" = None,
    conversation_id: str | None = None,
) -> None:
    """Register the ``task`` tool for subagent delegation.

    Must be called *after* ``build_dispatch_map`` returns, because the
    handler captures ``dispatch`` by reference to pass to ``run_subagent``.

    ``db_session`` and ``conversation_id`` are threaded so the child
    loop's risk/approval gate still fires for ACT_HIGH tools — omitting
    them re-introduces the approval bypass documented in the
    2026-04-17 review.
    """
    from app.services.agent.runtime.subagent import run_subagent

    async def handler(prompt: str) -> str:
        return await run_subagent(
            prompt=prompt,
            parent_session=session_state,
            llm=llm,
            parent_dispatch_map=dispatch,
            system_prompt=system_prompt_factory(),
            db_session=db_session,
            conversation_id=conversation_id,
        )

    _register(
        dispatch,
        "task",
        (
            "Delegate a subtask to an autonomous subagent. "
            "The subagent has access to all tools except recursive task delegation. "
            "Returns the subagent's final text summary."
        ),
        {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Task prompt for the subagent",
                },
            },
            "required": ["prompt"],
        },
        RiskLevel.ACT_LOW,
        handler,
    )
