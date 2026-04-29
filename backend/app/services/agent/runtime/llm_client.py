"""Provider-agnostic LLM client powered by LiteLLM.

All providers (Anthropic, OpenAI, Gemini, OpenRouter, Ollama) go through
litellm.acompletion() with unified OpenAI-format messages. Supports both
blocking and streaming calls, extended thinking, and per-user API keys.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from app.config import settings
from app.services.agent.runtime.llm_providers import (
    LLMProviderAttempt,
    _LLM_REQUEST_TIMEOUT,
    is_retryable_llm_exception,
    is_provider_exhausted_exception,
    resolve_provider_attempts,
    resolve_provider_model,
    retry_llm_call,
    select_provider,
)
from app.services.agent.runtime.llm_streaming import (
    StreamFallbackSignal,
    accumulate_tool_calls,
    process_stream_response,
)
from app.services.agent.runtime.stream_events import (
    AgentDone,
    AgentError,
    StreamEvent,
    TextDelta,
    ThinkingDelta,
    ToolCallsAccumulated,
)
from app.utils.logging import get_logger

# Backward-compatible aliases — tests and other modules may import these
# private names directly from llm_client.
_is_retryable_llm_exception = is_retryable_llm_exception
_retry_llm_call = retry_llm_call
_resolve_provider_model = resolve_provider_model
_select_provider = select_provider

logger = get_logger(__name__)


@dataclass(frozen=True)
class LLMResponse:
    """Normalized response from any LLM provider (OpenAI format)."""

    content: str  # Text content
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str = "end_turn"  # "end_turn" | "tool_use" | "max_tokens"
    usage: dict[str, int] = field(
        default_factory=lambda: {"input_tokens": 0, "output_tokens": 0}
    )
    thinking: str | None = None
    thinking_tokens: int = 0  # Thinking token count for billing


class LLMClient:
    """Provider-agnostic LLM client powered by LiteLLM."""

    def __init__(
        self,
        *,
        user_id: str = "",
        model_override: str | None = None,
        db_session: Any = None,
    ) -> None:
        self._provider: str | None = None
        self._model: str | None = None  # Raw model name (without LiteLLM prefix)
        self._litellm_model: str | None = None  # Full LiteLLM model ID
        self._initialized = False
        self._attempts: list[LLMProviderAttempt] = []
        self._disabled_attempts: set[tuple[str, str]] = set()
        self._user_id = user_id
        self._model_override = model_override
        self._db_session = db_session
        # Per-user overrides resolved during init
        self._api_key: str | None = None
        self._api_base: str | None = None
        # Per-client test stub so pytest sessions don't share call-count
        # state through a module-level singleton (prior design caused
        # flaky test-order dependence).
        self._test_client: DeterministicTestClient | None = None

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        if os.getenv("PYTEST_CURRENT_TEST"):
            self._provider = "test"
            self._model = "deterministic"
            self._litellm_model = "deterministic"
            self._attempts = [
                LLMProviderAttempt(
                    provider="test",
                    model="deterministic",
                    litellm_model="deterministic",
                )
            ]
            self._disabled_attempts = set()
            return

        # Try per-user settings first
        user_settings = None
        if self._user_id and self._db_session:
            from app.repositories.user_settings_repo import UserSettingsRepository

            repo = UserSettingsRepository(self._db_session)
            user_settings = await repo.get_by_user_id(self._user_id)

        self._attempts = resolve_provider_attempts(
            model_override=self._model_override,
            user_settings=user_settings,
            current_provider=self._provider,
        )
        if not self._attempts:
            return
        self._disabled_attempts = set()
        primary = self._attempts[0]
        self._provider = primary.provider
        self._model = primary.model
        self._litellm_model = primary.litellm_model
        self._api_key = primary.api_key
        self._api_base = primary.api_base

        logger.info(
            "llm.init",
            provider=self._provider,
            model=self._model,
            litellm_model=self._litellm_model,
            has_user_key=bool(self._api_key),
            fallback_attempts=[
                {"provider": attempt.provider, "model": attempt.model}
                for attempt in self._attempts
            ],
        )

    def _resolve_provider_attempts(
        self, user_settings: Any
    ) -> list[LLMProviderAttempt]:
        """Delegate to the extracted module-level function."""
        return resolve_provider_attempts(
            model_override=self._model_override,
            user_settings=user_settings,
            current_provider=self._provider,
        )

    def _build_kwargs(
        self,
        *,
        attempt: LLMProviderAttempt,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int | None,
        stream: bool,
    ) -> dict[str, Any]:
        """Build the kwargs dict for litellm.acompletion()."""
        resolved_max = max_tokens or settings.agent_max_tokens
        kwargs: dict[str, Any] = {
            "model": attempt.litellm_model,
            "messages": [{"role": "system", "content": system}] + messages,
            "max_tokens": resolved_max,
            "stream": stream,
        }

        if attempt.api_key:
            kwargs["api_key"] = attempt.api_key
        if attempt.api_base:
            kwargs["api_base"] = attempt.api_base

        if tools:
            kwargs["tools"] = tools

        # Thinking / reasoning support
        if settings.agent_thinking_enabled:
            if attempt.provider == "anthropic":
                kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": settings.agent_thinking_budget,
                }
            elif settings.agent_thinking_effort != "none":
                kwargs["reasoning_effort"] = settings.agent_thinking_effort

        return kwargs

    def _available_attempts(self) -> list[LLMProviderAttempt]:
        return [
            attempt
            for attempt in self._attempts
            if (attempt.provider, attempt.model) not in self._disabled_attempts
        ]

    def _disable_attempt(self, attempt: LLMProviderAttempt, error: Exception | str) -> None:
        key = (attempt.provider, attempt.model)
        if key in self._disabled_attempts:
            return
        self._disabled_attempts.add(key)
        logger.warning(
            "llm.provider_disabled",
            provider=attempt.provider,
            model=attempt.model,
            reason="provider_exhausted",
            error=str(error),
        )

    async def create(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Send a blocking request and return a normalized response."""
        import litellm

        await self._ensure_initialized()

        if not self._litellm_model:
            return LLMResponse(
                content="No LLM provider available.",
                stop_reason="end_turn",
            )

        if self._provider == "test":
            if self._test_client is None:
                self._test_client = DeterministicTestClient()
            return await self._test_client.create(
                system=system, messages=messages, tools=tools, max_tokens=max_tokens
            )

        last_error: Exception | None = None
        attempts = self._available_attempts()
        if not attempts:
            raise RuntimeError("No LLM provider available.")

        for index, attempt in enumerate(attempts):
            kwargs = self._build_kwargs(
                attempt=attempt,
                system=system,
                messages=messages,
                tools=tools,
                max_tokens=max_tokens,
                stream=False,
            )

            logger.info(
                "llm.call_start",
                provider=attempt.provider,
                model=attempt.litellm_model,
                message_count=len(messages),
                has_tools=bool(tools),
                attempt=index + 1,
                total_attempts=len(attempts),
            )

            try:
                response = await asyncio.wait_for(
                    retry_llm_call(lambda: litellm.acompletion(**kwargs)),
                    timeout=_LLM_REQUEST_TIMEOUT,
                )
                return self._normalize_response(response)
            except asyncio.TimeoutError:
                last_error = RuntimeError(
                    f"{attempt.provider}/{attempt.model} request timed out after {_LLM_REQUEST_TIMEOUT}s"
                )
            except Exception as exc:
                last_error = exc
                if is_provider_exhausted_exception(exc):
                    self._disable_attempt(attempt, exc)
                if (
                    not is_retryable_llm_exception(exc)
                    or index == len(attempts) - 1
                ):
                    break
                logger.warning(
                    "llm.provider_fallback",
                    from_provider=attempt.provider,
                    from_model=attempt.model,
                    error=str(exc),
                )

        raise RuntimeError(
            str(last_error) if last_error else "No LLM provider available."
        )

    async def create_stream(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Send a streaming request and yield StreamEvent objects."""
        import litellm

        await self._ensure_initialized()

        if not self._litellm_model:
            yield AgentError(message="No LLM provider available.")
            return

        if self._provider == "test":
            if self._test_client is None:
                self._test_client = DeterministicTestClient()
            async for event in self._test_client.create_stream(
                system=system, messages=messages, tools=tools, max_tokens=max_tokens
            ):
                yield event
            return

        last_error: Exception | None = None
        attempts = self._available_attempts()
        if not attempts:
            yield AgentError(message="No LLM provider available.")
            return

        for index, attempt in enumerate(attempts):
            kwargs = self._build_kwargs(
                attempt=attempt,
                system=system,
                messages=messages,
                tools=tools,
                max_tokens=max_tokens,
                stream=True,
            )

            logger.info(
                "llm.stream_start",
                provider=attempt.provider,
                model=attempt.litellm_model,
                message_count=len(messages),
                attempt=index + 1,
                total_attempts=len(attempts),
            )

            try:
                response = await asyncio.wait_for(
                    retry_llm_call(lambda: litellm.acompletion(**kwargs)),
                    timeout=_LLM_REQUEST_TIMEOUT,
                )
            except asyncio.TimeoutError:
                last_error = RuntimeError(
                    f"{attempt.provider}/{attempt.model} request timed out after {_LLM_REQUEST_TIMEOUT}s"
                )
                if index < len(attempts) - 1:
                    continue
                yield AgentError(message=str(last_error))
                return
            except Exception as exc:
                last_error = exc
                if is_provider_exhausted_exception(exc):
                    self._disable_attempt(attempt, exc)
                if is_retryable_llm_exception(exc) and index < len(attempts) - 1:
                    logger.warning(
                        "llm.provider_fallback",
                        from_provider=attempt.provider,
                        from_model=attempt.model,
                        error=str(exc),
                    )
                    continue
                yield AgentError(message=str(exc))
                return

            # Process streamed chunks via the extracted helper
            should_fallback = False
            async for event in process_stream_response(response, attempt):
                if isinstance(event, StreamFallbackSignal):
                    if is_provider_exhausted_exception(RuntimeError(event.error)):
                        self._disable_attempt(attempt, event.error)
                    if index < len(attempts) - 1:
                        should_fallback = True
                    else:
                        yield AgentError(message=event.error)
                        return
                else:
                    yield event

            if should_fallback:
                continue
            return

        if last_error:
            yield AgentError(message=str(last_error))

    def get_accumulated_tool_calls(
        self, tool_call_chunks: dict[int, dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Convert accumulated tool call chunks into structured tool calls."""
        return accumulate_tool_calls(tool_call_chunks)

    @staticmethod
    def _normalize_response(response: Any) -> LLMResponse:
        """Normalize a LiteLLM response into our LLMResponse format."""
        choice = response.choices[0]
        msg = choice.message

        content = msg.content or ""
        thinking = getattr(msg, "reasoning_content", None)

        tool_calls: list[dict[str, Any]] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = (
                        json.loads(tc.function.arguments)
                        if tc.function.arguments
                        else {}
                    )
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "input": args,
                    }
                )

        stop = "tool_use" if tool_calls else "end_turn"
        usage = {}
        thinking_tokens = 0
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens or 0,
                "output_tokens": response.usage.completion_tokens or 0,
            }
            thinking_tokens = getattr(response.usage, "thinking_tokens", 0) or 0

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=stop,
            usage=usage,
            thinking=thinking,
            thinking_tokens=thinking_tokens,
        )


# ---------------------------------------------------------------------------
# Test client (used when PYTEST_CURRENT_TEST is set)
# ---------------------------------------------------------------------------


class DeterministicTestClient:
    """Deterministic LLM stub for pytest runs.

    Default: Call 1 requests glob, Call 2 returns text.
    With ``responses`` list: returns responses in order, cycling the last one.
    Supports both create() and create_stream() for loop compatibility.
    """

    def __init__(self, responses: list[LLMResponse] | None = None) -> None:
        self._call_count = 0
        self._responses = responses
        self._last_tool_calls: list[dict[str, Any]] = []

    async def create(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self._call_count += 1

        # Playwright E2E needs the intermediate tool-running state to stay
        # visible long enough for the browser to observe it.
        if os.getenv("PYTEST_CURRENT_TEST") == "playwright-e2e" and self._call_count > 1:
            await asyncio.sleep(0.35)

        if self._responses is not None:
            idx = min(self._call_count - 1, len(self._responses) - 1)
            resp = self._responses[idx]
            self._last_tool_calls = resp.tool_calls
            return resp

        playwright_workflow_run = self._maybe_create_playwright_workflow_run(messages)
        if playwright_workflow_run is not None:
            self._last_tool_calls = playwright_workflow_run.tool_calls
            return playwright_workflow_run

        # Default behavior: glob then text
        if self._call_count == 1:
            resp = LLMResponse(
                content="",
                tool_calls=[
                    {
                        "id": "test_tool_call_glob",
                        "name": "glob",
                        "input": {"pattern": "**/*"},
                    }
                ],
                stop_reason="tool_use",
                usage={"input_tokens": 100, "output_tokens": 50},
            )
            self._last_tool_calls = resp.tool_calls
            return resp
        self._last_tool_calls = []
        return LLMResponse(
            content="I scanned the workspace and I'm ready to proceed.",
            stop_reason="end_turn",
            usage={"input_tokens": 200, "output_tokens": 30},
        )

    async def create_stream(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Simulate streaming by yielding events from a blocking create() call."""
        resp = await self.create(
            system=system, messages=messages, tools=tools, max_tokens=max_tokens
        )
        if resp.thinking:
            yield ThinkingDelta(text=resp.thinking)
        if resp.content:
            yield TextDelta(text=resp.content)
        if resp.tool_calls:
            yield ToolCallsAccumulated(tool_calls=resp.tool_calls)
        yield AgentDone(usage=resp.usage)

    def get_accumulated_tool_calls(
        self, tool_call_chunks: dict[int, dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Return tool calls from the last response (no chunking in test mode)."""
        return self._last_tool_calls

    def _maybe_create_playwright_workflow_run(
        self, messages: list[dict[str, Any]]
    ) -> LLMResponse | None:
        if os.getenv("PYTEST_CURRENT_TEST") != "playwright-e2e":
            return None

        prompt = self._latest_user_prompt(messages)
        workflow_name = self._match_playwright_workflow_run_prompt(prompt)
        if workflow_name is None:
            return None

        listed_group = self._extract_project_workflow_group(messages)
        submitted_run = self._extract_tool_result(
            messages, "platform_run_submit"
        )

        if submitted_run is not None:
            run_id = (
                submitted_run.get("data", {})
                .get("run", {})
                .get("run_id", "unknown-run")
            )
            return LLMResponse(
                content=f"Queued run {run_id} for workflow {workflow_name}.",
                stop_reason="end_turn",
                usage={"input_tokens": 260, "output_tokens": 48},
            )

        if listed_group is None:
            return LLMResponse(
                content="",
                tool_calls=[
                    {
                        "id": "test_tool_call_project_workflows",
                        "name": "platform_workflow_project_list",
                        "input": {},
                    }
                ],
                stop_reason="tool_use",
                usage={"input_tokens": 180, "output_tokens": 55},
            )

        pinned_workflow = listed_group.get("pinned_workflow", {})
        workflow_id = pinned_workflow.get("id")
        if not workflow_id:
            return LLMResponse(
                content=f"I couldn't find an enabled workflow named {workflow_name}.",
                stop_reason="end_turn",
                usage={"input_tokens": 220, "output_tokens": 36},
            )

        return LLMResponse(
            content="",
            tool_calls=[
                {
                    "id": "test_tool_call_submit_run",
                    "name": "platform_run_submit",
                    "input": {"workflow_id": workflow_id, "values": {}},
                }
            ],
            stop_reason="tool_use",
            usage={"input_tokens": 230, "output_tokens": 60},
        )

    @staticmethod
    def _latest_user_prompt(messages: list[dict[str, Any]]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                return str(message.get("content", ""))
        return ""

    @staticmethod
    def _match_playwright_workflow_run_prompt(prompt: str) -> str | None:
        match = re.search(
            r"run the (?P<workflow>agent-e2e-workflow-\d+) workflow",
            prompt,
            flags=re.IGNORECASE,
        )
        if match:
            return match.group("workflow")
        return None

    def _extract_project_workflow_group(
        self, messages: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        result = self._extract_tool_result(messages, "platform_workflow_project_list")
        if result is None:
            return None
        workflows = result.get("data", {}).get("workflows", [])
        if workflows:
            return workflows[0]
        return None

    @staticmethod
    def _extract_tool_result(
        messages: list[dict[str, Any]], tool_name: str
    ) -> dict[str, Any] | None:
        for index in range(len(messages) - 1):
            assistant_message = messages[index]
            tool_message = messages[index + 1]
            if assistant_message.get("role") != "assistant":
                continue
            if tool_message.get("role") != "tool":
                continue

            for tool_call in assistant_message.get("tool_calls", []):
                function = tool_call.get("function", {})
                if function.get("name") != tool_name:
                    continue
                if tool_call.get("id") != tool_message.get("tool_call_id"):
                    continue
                try:
                    return json.loads(str(tool_message.get("content", "{}")))
                except json.JSONDecodeError:
                    return None
        return None
