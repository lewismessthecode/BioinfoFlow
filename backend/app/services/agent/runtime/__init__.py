"""Agent runtime — explicit async loop replacing LangGraph StateGraph.

Phase 1: core loop, tool dispatch, todo, compaction.
Phase 2: subagents, skills, tasks, background jobs.
"""

from app.services.agent.runtime.compact import (
    auto_compact,
    micro_compact,
    should_auto_compact,
)
from app.services.agent.runtime.background import BackgroundManager, BackgroundResult
from app.services.agent.runtime.dispatch import (
    ToolEntry,
    build_dispatch_map,
    get_tool_schemas,
    register_task_tool,
)
from app.services.agent.runtime.llm_client import (
    DeterministicTestClient,
    LLMClient,
    LLMResponse,
)
from app.services.agent.runtime.loop import agent_loop
from app.services.agent.runtime.messages import (
    estimate_tokens,
    extract_text,
    extract_tool_calls,
    make_tool_results,
    make_user_message,
)
from app.services.agent.runtime.session_state import SessionState
from app.services.agent.runtime.skills import SkillLoader
from app.services.agent.runtime.subagent import run_subagent
from app.services.agent.runtime.system_prompt import build_system_prompt
from app.services.agent.runtime.tasks import Task, TaskManager
from app.services.agent.runtime.todo import TodoItem, TodoManager

__all__ = [
    # Loop
    "agent_loop",
    # Background
    "BackgroundManager",
    "BackgroundResult",
    # Dispatch
    "ToolEntry",
    "build_dispatch_map",
    "get_tool_schemas",
    "register_task_tool",
    # LLM
    "LLMClient",
    "LLMResponse",
    "DeterministicTestClient",
    # Messages
    "make_user_message",
    "make_tool_results",
    "extract_tool_calls",
    "extract_text",
    "estimate_tokens",
    # Session
    "SessionState",
    # System prompt
    "build_system_prompt",
    # Skills
    "SkillLoader",
    # Subagent
    "run_subagent",
    # Tasks
    "Task",
    "TaskManager",
    # Todo
    "TodoManager",
    "TodoItem",
    # Compact
    "auto_compact",
    "micro_compact",
    "should_auto_compact",
]
