from __future__ import annotations

import asyncio
import inspect
import json
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.config import settings
from app.services.hermes_service.home import ensure_hermes_home_environment
from app.services.hermes_service.system_prompt import build_bioinfoflow_hermes_prompt
from app.services.hermes_service.tool_bridge import (
    HermesToolRuntimeContext,
    bind_tool_context,
    ensure_bioinfoflow_toolset_registered,
    get_enabled_toolsets,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

ensure_hermes_home_environment()

try:  # pragma: no cover - exercised indirectly when dependency is installed
    from run_agent import AIAgent
except Exception as exc:  # pragma: no cover - graceful fallback in dev/test
    logger.warning("hermes.sdk.import_failed", module="run_agent", error=str(exc))
    AIAgent = None

try:  # pragma: no cover - exercised indirectly when dependency is installed
    from tools.approval import reset_current_session_key, set_current_session_key
except Exception as exc:  # pragma: no cover - graceful fallback in dev/test
    logger.warning(
        "hermes.sdk.import_failed", module="tools.approval", error=str(exc)
    )
    reset_current_session_key = None
    set_current_session_key = None

try:  # pragma: no cover - exercised indirectly when dependency is installed
    from tools.terminal_tool import set_approval_callback as set_terminal_approval_callback
except Exception as exc:  # pragma: no cover - graceful fallback in dev/test
    logger.warning(
        "hermes.sdk.import_failed", module="tools.terminal_tool", error=str(exc)
    )
    set_terminal_approval_callback = None


EventCallback = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class HermesRunResult:
    final_text: str
    usage: dict[str, int] = field(default_factory=dict)


def _json_safe_payload(value: Any) -> tuple[str, Any | None, str | None]:
    if value is None:
        return "", None, None

    summary = None
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return value, None, None
        summary = parsed.get("summary") if isinstance(parsed, dict) else None
        return value, parsed, summary if isinstance(summary, str) else None

    if isinstance(value, (dict, list)):
        if isinstance(value, dict):
            maybe_summary = value.get("summary")
            if isinstance(maybe_summary, str):
                summary = maybe_summary
        return json.dumps(value, ensure_ascii=True), value, summary

    return str(value), None, None


class HermesRunner:
    """Thin wrapper around Hermes' AIAgent.

    The concrete SDK integration is intentionally isolated here so the
    application can mock it in tests and evolve the bridge without leaking
    Hermes details into API handlers.
    """

    def __init__(self, max_concurrency: int | None = None) -> None:
        configured = max_concurrency
        if configured is None:
            configured = settings.agent_hermes_max_concurrency
        self._max_concurrency = max(1, int(configured or 1))
        self._run_semaphore: asyncio.Semaphore | None = None
        self._run_semaphore_loop: asyncio.AbstractEventLoop | None = None

    def _get_run_semaphore(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        if self._run_semaphore is None or self._run_semaphore_loop is not loop:
            self._run_semaphore = asyncio.Semaphore(self._max_concurrency)
            self._run_semaphore_loop = loop
        return self._run_semaphore

    async def run_response(
        self,
        *,
        session_id: str,
        prompt: str,
        model: str | None,
        cwd: str | None,
        session_store=None,
        clarify_callback: Callable[[str, list[str] | None], str] | None = None,
        approval_callback: Callable[..., str] | None = None,
        tool_context: HermesToolRuntimeContext | None = None,
        on_event: EventCallback,
    ) -> HermesRunResult:
        if AIAgent is None:
            raise RuntimeError(
                "Hermes Agent SDK is not installed. Configure the backend dependency before enabling agent_engine=hermes_service."
            )

        ensure_hermes_home_environment(state_db_path=settings.agent_hermes_state_db)
        loop = asyncio.get_running_loop()
        ensure_bioinfoflow_toolset_registered()

        async def _emit(event: dict[str, Any]) -> None:
            await on_event(event)

        # Track in-flight emissions scheduled from the worker thread so we can
        # wait for them before returning — otherwise consumers can miss events
        # that were posted just before run_conversation completes.
        pending_emissions: list = []

        def _schedule(event: dict[str, Any]) -> None:
            future = asyncio.run_coroutine_threadsafe(_emit(event), loop)
            pending_emissions.append(future)

        def _parse_args(args: Any) -> Any:
            if isinstance(args, str):
                try:
                    return json.loads(args)
                except json.JSONDecodeError:
                    return {"raw": args}
            return args if isinstance(args, dict) else (args or {})

        history = None
        if session_store is not None:
            history = session_store.get_messages_as_conversation(session_id) or None

        agent_signature = inspect.signature(AIAgent)
        accepts_var_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in agent_signature.parameters.values()
        )

        def _supports(name: str) -> bool:
            return accepts_var_kwargs or name in agent_signature.parameters

        def _tool_start_callback(*cb_args, **cb_kwargs) -> None:
            call_id = cb_args[0] if len(cb_args) > 0 else cb_kwargs.get("call_id") or cb_kwargs.get("id")
            name = cb_args[1] if len(cb_args) > 1 else cb_kwargs.get("name")
            args = cb_args[2] if len(cb_args) > 2 else cb_kwargs.get("args")
            _schedule(
                {
                    "type": "tool_call_start",
                    "metadata": {
                        "id": str(call_id or ""),
                        "name": str(name or ""),
                        "args": _parse_args(args),
                    },
                }
            )

        def _tool_progress_callback(*cb_args, **cb_kwargs) -> None:
            status = cb_args[0] if len(cb_args) > 0 else cb_kwargs.get("status")
            name = cb_args[1] if len(cb_args) > 1 else cb_kwargs.get("name") or cb_kwargs.get("function_name")
            preview = cb_args[2] if len(cb_args) > 2 else cb_kwargs.get("preview") or cb_kwargs.get("message")
            args = cb_args[3] if len(cb_args) > 3 else cb_kwargs.get("args") or cb_kwargs.get("function_args")
            if name in {None, "", "_thinking"}:
                return
            _schedule(
                {
                    "type": "tool_call_progress",
                    "content": str(preview or ""),
                    "metadata": {
                        "id": str(cb_kwargs.get("call_id") or cb_kwargs.get("id") or ""),
                        "name": str(name or ""),
                        "args": _parse_args(args),
                        "status": str(status or ""),
                        "preview": str(preview or ""),
                    },
                }
            )

        def _tool_complete_callback(*cb_args, **cb_kwargs) -> None:
            call_id = cb_args[0] if len(cb_args) > 0 else cb_kwargs.get("call_id") or cb_kwargs.get("id")
            name = cb_args[1] if len(cb_args) > 1 else cb_kwargs.get("name")
            args = cb_args[2] if len(cb_args) > 2 else cb_kwargs.get("args")
            result = cb_args[3] if len(cb_args) > 3 else cb_kwargs.get("result")
            result_text, result_json, summary = _json_safe_payload(result)
            _schedule(
                {
                    "type": "tool_call_end",
                    "metadata": {
                        "id": str(call_id or ""),
                        "name": str(name or ""),
                        "args": _parse_args(args),
                        "result": result_text,
                        "result_json": result_json,
                        "summary": summary,
                        "is_error": bool(cb_kwargs.get("is_error") or False),
                        "duration_ms": float(cb_kwargs.get("duration_ms") or 0.0),
                    },
                }
            )

        agent_kwargs: dict[str, Any] = {}
        ephemeral_system_prompt = build_bioinfoflow_hermes_prompt(
            project_id=getattr(tool_context, "project_id", None),
            workspace_root=cwd or getattr(tool_context, "workspace_root", None),
        )
        candidate_kwargs = {
            "model": model,
            "session_id": session_id,
            "working_directory": cwd,
            "session_db": session_store,
            "platform": "bioinfoflow",
            "persist_session": True,
            "skip_memory": True,
            "quiet_mode": True,
            "enabled_toolsets": get_enabled_toolsets(),
            "ephemeral_system_prompt": ephemeral_system_prompt,
            "stream_delta_callback": lambda delta: _schedule({"type": "text_delta", "content": delta or ""}),
            "reasoning_callback": lambda text: _schedule({"type": "thinking_delta", "content": text or ""}),
            "thinking_callback": lambda text: _schedule({"type": "thinking_delta", "content": text or ""}),
            "clarify_callback": clarify_callback,
            "tool_start_callback": _tool_start_callback,
            "tool_progress_callback": _tool_progress_callback,
            "tool_complete_callback": _tool_complete_callback,
            "status_callback": lambda category, message: _schedule(
                {
                    "type": "status",
                    "content": str(message or ""),
                    "metadata": {"category": str(category or "status")},
                }
            ),
        }
        for key, value in candidate_kwargs.items():
            if _supports(key):
                agent_kwargs[key] = value

        if approval_callback is not None and set_terminal_approval_callback is not None:
            set_terminal_approval_callback(approval_callback)

        agent = AIAgent(**agent_kwargs)

        def _run() -> dict[str, Any]:
            logger.info("hermes.run_response.start", session_id=session_id)
            run_context = bind_tool_context(tool_context) if tool_context is not None else nullcontext()
            session_token = None
            try:
                if set_current_session_key is not None:
                    session_token = set_current_session_key(session_id)
                with run_context:
                    result = agent.run_conversation(
                        prompt,
                        conversation_history=history,
                    )
                if isinstance(result, dict):
                    return result
                return {"final_response": str(result)}
            finally:
                if reset_current_session_key is not None and session_token is not None:
                    reset_current_session_key(session_token)

        async with self._get_run_semaphore():
            final_result = await asyncio.to_thread(_run)
        # Drain any events still being emitted from the worker thread so the
        # caller sees a complete event stream by the time we return.
        for future in pending_emissions:
            try:
                await asyncio.wrap_future(future)
            except Exception:  # noqa: BLE001 — emit failures must not poison the run result
                logger.exception("hermes.run_response.emit_failed", session_id=session_id)
        return HermesRunResult(
            final_text=str(final_result.get("final_response") or ""),
            usage=final_result.get("usage") or {},
        )
