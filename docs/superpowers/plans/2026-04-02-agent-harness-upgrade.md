# Agent Harness Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade bioinfoflow's agent to a "bioinformatics Claude Code" with modern LLM providers, lean tooling, and a polished thinking UI.

**Architecture:** Three independent phases executed by 3 parallel Opus subagents. Phase 1 (LLM Providers) and Phase 2 (Tool Refactor) have zero file overlap and run fully in parallel. Phase 3 (Event System + Thinking UI) depends on Phase 1 landing the `LLMResponse.thinking` field, then proceeds independently.

**Tech Stack:** Python 3.12, FastAPI, AsyncAnthropic SDK, AsyncOpenAI SDK, google-genai SDK, React 19, Next.js 16, Tailwind CSS 4, Framer Motion

**Spec:** `docs/superpowers/specs/2026-04-02-agent-harness-upgrade-design.md`

---

## Phase 1: LLM Providers (Subagent 1)

**Scope:** Drop LangChain, use official SDKs, add 5 providers (Anthropic, OpenAI, Gemini, OpenRouter, Ollama), add extended thinking, add streaming. Update user settings model/schema/UI for new providers.

**Dependency:** None (can start immediately)

**Files:**
- Create: `backend/app/services/agent/runtime/providers.py`
- Modify: `backend/app/services/agent/runtime/llm_client.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/models/user_settings.py`
- Modify: `backend/app/schemas/user_settings.py`
- Modify: `backend/app/services/user_settings_service.py`
- Modify: `backend/app/services/agent/agent_service.py` (remove v1 routing)
- Modify: `backend/pyproject.toml`
- Modify: `frontend/hooks/use-llm-settings.ts`
- Delete: `backend/app/services/agent/llm_providers.py`
- Delete: `backend/app/services/agent/graph.py`
- Create: Alembic migration for user_settings columns
- Test: `backend/tests/test_agent/test_runtime/test_llm_client.py`
- Test: `backend/tests/test_agent/test_runtime/test_providers.py` (new)

---

### Task 1.1: Delete v1 LangGraph Agent

Must happen BEFORE removing LangChain deps (Codex Finding #3).

- [ ] **Step 1: Delete `graph.py`**

```bash
rm backend/app/services/agent/graph.py
```

- [ ] **Step 2: Remove v1 routing from `agent_service.py`**

In `backend/app/services/agent/agent_service.py`, remove the v1 branch. Replace lines 93-110:

```python
        # Old code (lines 93-110):
        #     if settings.agent_runtime_v2:
        #         await self._run_v2(...)
        #     else:
        #         await self._run_v1_graph(...)

        # New code — v2 is the only path:
        await self._run_v2(
            content=content,
            project_id=proj_id,
            conversation_id=conv_id,
            current_user_message_id=str(user_message.id),
            trace_recorder=trace_recorder,
            user_id=user_id,
            model_override=model_override,
        )
```

Also delete the entire `_run_v1_graph()` method (lines 234-278) and remove the `from app.config import settings` if it was only used for `agent_runtime_v2`.

- [ ] **Step 3: Remove v1 import from agent_service.py**

Delete the line inside `_run_v1_graph` that imports `build_agent_graph`. Since we deleted the method, this is already handled.

- [ ] **Step 4: Run tests to verify nothing breaks**

```bash
cd backend && uv run pytest tests/test_agent/ -v --tb=short
```

Expected: All passing (v1 path was not covered by tests, v2 is default).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "refactor: delete v1 LangGraph agent and routing"
```

---

### Task 1.2: Create Provider Registry

- [ ] **Step 1: Write test for provider registry**

Create `backend/tests/test_agent/test_runtime/test_providers.py`:

```python
"""Tests for provider registry and configuration."""
from __future__ import annotations

import pytest

from app.services.agent.runtime.providers import (
    PROVIDER_REGISTRY,
    ProviderConfig,
    infer_provider_from_model,
)


def test_registry_has_all_providers():
    assert set(PROVIDER_REGISTRY.keys()) == {
        "anthropic", "openai", "gemini", "openrouter", "ollama",
    }


def test_each_provider_has_default_model():
    for name, config in PROVIDER_REGISTRY.items():
        assert config.default_model, f"{name} missing default_model"


def test_anthropic_uses_native_sdk():
    assert PROVIDER_REGISTRY["anthropic"].sdk == "anthropic"


def test_openrouter_uses_openai_sdk():
    assert PROVIDER_REGISTRY["openrouter"].sdk == "openai"
    assert "openrouter.ai" in PROVIDER_REGISTRY["openrouter"].base_url


def test_ollama_uses_openai_sdk():
    assert PROVIDER_REGISTRY["ollama"].sdk == "openai"
    assert "11434" in PROVIDER_REGISTRY["ollama"].base_url


class TestInferProvider:
    def test_claude_model(self):
        assert infer_provider_from_model("claude-sonnet-4-6") == "anthropic"

    def test_gpt_model(self):
        assert infer_provider_from_model("gpt-5.4") == "openai"

    def test_gemini_model(self):
        assert infer_provider_from_model("gemini-3.1-pro-preview") == "gemini"

    def test_openrouter_slash_format(self):
        # "/" must be checked BEFORE "claude" (Codex Finding #2)
        assert infer_provider_from_model("anthropic/claude-sonnet-4-6") == "openrouter"
        assert infer_provider_from_model("openai/gpt-5.4") == "openrouter"
        assert infer_provider_from_model("google/gemini-3.1-pro") == "openrouter"

    def test_unknown_defaults_to_ollama(self):
        assert infer_provider_from_model("llama3.3") == "ollama"
        assert infer_provider_from_model("qwen-2.5") == "ollama"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_agent/test_runtime/test_providers.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.agent.runtime.providers'`

- [ ] **Step 3: Implement provider registry**

Create `backend/app/services/agent/runtime/providers.py`:

```python
"""LLM provider registry and configuration.

Maps provider names to their SDK, default models, thinking parameters,
and base URLs. Supports 5 providers with 3 SDK dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderConfig:
    """Configuration for an LLM provider."""

    sdk: str  # "anthropic" | "openai" | "google-genai"
    default_model: str
    thinking_param: str | None = None  # "budget_tokens" | "reasoning_effort" | "thinking_level"
    base_url: str = ""
    models: list[str] = field(default_factory=list)


PROVIDER_REGISTRY: dict[str, ProviderConfig] = {
    "anthropic": ProviderConfig(
        sdk="anthropic",
        default_model="claude-sonnet-4-6",
        thinking_param="budget_tokens",
        models=["claude-opus-4-6", "claude-sonnet-4-6", "claude-sonnet-4-5"],
    ),
    "openai": ProviderConfig(
        sdk="openai",
        default_model="gpt-5.4",
        thinking_param="reasoning_effort",
        models=["gpt-5.4", "gpt-5.4-pro", "gpt-5.4-mini"],
    ),
    "gemini": ProviderConfig(
        sdk="google-genai",
        default_model="gemini-3.1-pro-preview",
        thinking_param="thinking_level",
        models=["gemini-3.1-pro-preview", "gemini-3.1-flash"],
    ),
    "openrouter": ProviderConfig(
        sdk="openai",
        default_model="anthropic/claude-sonnet-4-6",
        thinking_param="reasoning_effort",
        base_url="https://openrouter.ai/api/v1",
        models=[],
    ),
    "ollama": ProviderConfig(
        sdk="openai",
        default_model="llama3.3",
        thinking_param=None,
        base_url="http://localhost:11434/v1",
        models=[],
    ),
}


def infer_provider_from_model(model: str) -> str:
    """Infer provider from model name.

    IMPORTANT: Check "/" first — OpenRouter models use "provider/model" format.
    "anthropic/claude-sonnet-4-6" must resolve to openrouter, not anthropic.
    """
    m = model.lower()
    if "/" in m:
        return "openrouter"
    if "claude" in m:
        return "anthropic"
    if "gpt" in m or "o1" in m or "o3" in m:
        return "openai"
    if "gemini" in m:
        return "gemini"
    return "ollama"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/test_agent/test_runtime/test_providers.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agent/runtime/providers.py backend/tests/test_agent/test_runtime/test_providers.py
git commit -m "feat: add LLM provider registry with 5-provider support"
```

---

### Task 1.3: Add Config Settings

- [ ] **Step 1: Add new settings to `backend/app/config.py`**

After the existing agent settings (around line 78), add:

```python
    # OpenRouter
    openrouter_api_key: str = ""
    openrouter_model: str = ""

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""

    # Extended thinking
    agent_thinking_enabled: bool = True
    agent_thinking_budget: int = 10000
    agent_thinking_effort: str = "medium"
    agent_thinking_level: str = "medium"
```

Remove the `agent_runtime_v2` setting (line 74) since we deleted v1.

- [ ] **Step 2: Update default models to latest**

Change existing defaults:
```python
    # Old:
    # agent_model: str = "claude-sonnet-4-5"
    # openai_model: str = "gpt-4o-mini"
    # gemini_model: str = "gemini-2.5-flash"

    # New:
    agent_model: str = "claude-sonnet-4-6"
    openai_model: str = "gpt-5.4"
    gemini_model: str = "gemini-3.1-pro-preview"
```

- [ ] **Step 3: Run existing tests**

```bash
cd backend && uv run pytest tests/ -v --tb=short -x
```

Expected: PASS (new settings have defaults, existing code unaffected).

- [ ] **Step 4: Commit**

```bash
git add backend/app/config.py
git commit -m "feat: add OpenRouter, Ollama, and thinking config settings"
```

---

### Task 1.4: Refactor LLMClient — Native SDKs

This is the largest task. Replace LangChain calls with native SDKs.

- [ ] **Step 1: Write test for OpenAI native call**

Add to `backend/tests/test_agent/test_runtime/test_llm_client.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.agent.runtime.llm_client import LLMClient, LLMResponse


@pytest.mark.asyncio
async def test_openai_native_call():
    """OpenAI provider uses AsyncOpenAI SDK, not LangChain."""
    client = LLMClient()
    client._provider = "openai"
    client._model = "gpt-5.4"
    client._initialized = True

    mock_openai = AsyncMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Hello"
    mock_response.choices[0].message.tool_calls = None
    mock_response.choices[0].finish_reason = "stop"
    mock_response.usage.prompt_tokens = 100
    mock_response.usage.completion_tokens = 50
    mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)
    client._client = mock_openai

    result = await client.create(
        system="You are helpful.",
        messages=[{"role": "user", "content": "Hi"}],
    )

    assert isinstance(result, LLMResponse)
    assert result.content[0]["type"] == "text"
    assert result.content[0]["text"] == "Hello"
    assert result.stop_reason == "end_turn"


@pytest.mark.asyncio
async def test_openai_tool_call_normalization():
    """OpenAI tool_calls are normalized to Anthropic format."""
    client = LLMClient()
    client._provider = "openai"
    client._model = "gpt-5.4"
    client._initialized = True

    mock_openai = AsyncMock()
    mock_tc = MagicMock()
    mock_tc.id = "call_123"
    mock_tc.function.name = "glob"
    mock_tc.function.arguments = '{"pattern": "**/*.py"}'
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = None
    mock_response.choices[0].message.tool_calls = [mock_tc]
    mock_response.choices[0].finish_reason = "tool_calls"
    mock_response.usage.prompt_tokens = 100
    mock_response.usage.completion_tokens = 50
    mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)
    client._client = mock_openai

    result = await client.create(
        system="You are helpful.",
        messages=[{"role": "user", "content": "Find files"}],
        tools=[{"name": "glob", "description": "Find files", "input_schema": {}}],
    )

    assert result.stop_reason == "tool_use"
    assert result.content[0]["type"] == "tool_use"
    assert result.content[0]["name"] == "glob"


@pytest.mark.asyncio
async def test_anthropic_thinking_extraction():
    """Anthropic extended thinking blocks are extracted to LLMResponse.thinking."""
    client = LLMClient()
    client._provider = "anthropic"
    client._model = "claude-sonnet-4-6"
    client._initialized = True

    mock_anthropic = AsyncMock()
    mock_thinking_block = MagicMock()
    mock_thinking_block.type = "thinking"
    mock_thinking_block.thinking = "Let me analyze this step by step..."
    mock_text_block = MagicMock()
    mock_text_block.type = "text"
    mock_text_block.text = "Here is my answer."
    mock_response = MagicMock()
    mock_response.content = [mock_thinking_block, mock_text_block]
    mock_response.stop_reason = "end_turn"
    mock_response.usage.input_tokens = 200
    mock_response.usage.output_tokens = 100
    mock_anthropic.messages.create = AsyncMock(return_value=mock_response)
    client._client = mock_anthropic

    result = await client.create(
        system="You are helpful.",
        messages=[{"role": "user", "content": "Explain"}],
    )

    assert result.thinking == "Let me analyze this step by step..."
    assert result.content[0]["type"] == "text"
    assert result.content[0]["text"] == "Here is my answer."
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_agent/test_runtime/test_llm_client.py -v -k "native or thinking_extraction"
```

Expected: FAIL — `_call_openai_native` does not exist, `LLMResponse` has no `thinking` field.

- [ ] **Step 3: Update LLMResponse dataclass**

In `backend/app/services/agent/runtime/llm_client.py`, update the `LLMResponse` dataclass (lines 21-29):

```python
@dataclass(frozen=True)
class LLMResponse:
    """Normalized response from any LLM provider."""

    content: list[dict[str, Any]]  # ContentBlock dicts
    stop_reason: str  # "end_turn" | "tool_use" | "max_tokens"
    usage: dict[str, int] = field(
        default_factory=lambda: {"input_tokens": 0, "output_tokens": 0}
    )
    thinking: str | None = None  # Reasoning text (Anthropic extended thinking)
    thinking_tokens: int = 0  # Thinking token count for billing
```

- [ ] **Step 4: Add `_call_openai_native()` method**

Replace `_call_langchain()` (lines 265-356) with two new methods. Add to `LLMClient` class:

```python
    async def _call_openai_native(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int | None,
    ) -> LLMResponse:
        """Call OpenAI/OpenRouter/Ollama via native AsyncOpenAI SDK."""
        import json as json_mod

        oai_messages = [{"role": "system", "content": system}]
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "user":
                if isinstance(content, list):
                    for block in content:
                        if block.get("type") == "tool_result":
                            oai_messages.append({
                                "role": "tool",
                                "tool_call_id": block["tool_use_id"],
                                "content": block.get("content", ""),
                            })
                        else:
                            oai_messages.append({"role": "user", "content": str(block)})
                else:
                    oai_messages.append({"role": "user", "content": content})
            elif role == "assistant":
                if isinstance(content, list):
                    text_parts = []
                    tool_calls = []
                    for block in content:
                        if block.get("type") == "text":
                            text_parts.append(block["text"])
                        elif block.get("type") == "tool_use":
                            tool_calls.append({
                                "id": block["id"],
                                "type": "function",
                                "function": {
                                    "name": block["name"],
                                    "arguments": json_mod.dumps(block["input"]),
                                },
                            })
                    ai_msg: dict[str, Any] = {
                        "role": "assistant",
                        "content": "\n".join(text_parts) if text_parts else None,
                    }
                    if tool_calls:
                        ai_msg["tool_calls"] = tool_calls
                    oai_messages.append(ai_msg)
                else:
                    oai_messages.append({"role": "assistant", "content": content})

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": oai_messages,
            "max_completion_tokens": max_tokens or settings.agent_max_tokens,
        }
        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("input_schema", {}),
                    },
                }
                for t in tools
            ]

        # Add reasoning effort if thinking is enabled
        if settings.agent_thinking_enabled and settings.agent_thinking_effort != "none":
            kwargs["reasoning"] = {"effort": settings.agent_thinking_effort}

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        content_blocks: list[dict[str, Any]] = []
        if choice.message.content:
            content_blocks.append({"type": "text", "text": choice.message.content})

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                content_blocks.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": json_mod.loads(tc.function.arguments),
                })

        has_tools = any(b.get("type") == "tool_use" for b in content_blocks)
        stop = "tool_use" if has_tools else "end_turn"

        return LLMResponse(
            content=content_blocks,
            stop_reason=stop,
            usage={
                "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                "output_tokens": response.usage.completion_tokens if response.usage else 0,
            },
        )
```

- [ ] **Step 5: Add `_call_gemini_native()` method**

```python
    async def _call_gemini_native(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int | None,
    ) -> LLMResponse:
        """Call Gemini via google-genai SDK."""
        from google import genai
        from google.genai import types

        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            content = msg["content"]
            if isinstance(content, str):
                contents.append(types.Content(role=role, parts=[types.Part.from_text(content)]))
            elif isinstance(content, list):
                parts = []
                for block in content:
                    if block.get("type") == "text":
                        parts.append(types.Part.from_text(block["text"]))
                    elif block.get("type") == "tool_result":
                        parts.append(types.Part.from_function_response(
                            name=block.get("tool_name", "tool"),
                            response={"result": block.get("content", "")},
                        ))
                if parts:
                    contents.append(types.Content(role=role, parts=parts))

        config: dict[str, Any] = {
            "max_output_tokens": max_tokens or settings.agent_max_tokens,
            "system_instruction": system,
        }
        if settings.agent_thinking_enabled:
            config["thinking_config"] = types.ThinkingConfig(
                thinking_level=settings.agent_thinking_level.upper(),
            )

        gemini_tools = None
        if tools:
            func_decls = []
            for t in tools:
                func_decls.append(types.FunctionDeclaration(
                    name=t["name"],
                    description=t.get("description", ""),
                    parameters=t.get("input_schema"),
                ))
            gemini_tools = [types.Tool(function_declarations=func_decls)]

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=contents,
            config=types.GenerateContentConfig(**config),
            tools=gemini_tools,
        )

        content_blocks: list[dict[str, Any]] = []
        has_tool_calls = False
        for part in response.candidates[0].content.parts:
            if part.text:
                content_blocks.append({"type": "text", "text": part.text})
            elif part.function_call:
                has_tool_calls = True
                content_blocks.append({
                    "type": "tool_use",
                    "id": f"gemini_{part.function_call.name}",
                    "name": part.function_call.name,
                    "input": dict(part.function_call.args) if part.function_call.args else {},
                })

        stop = "tool_use" if has_tool_calls else "end_turn"
        usage_meta = response.usage_metadata
        return LLMResponse(
            content=content_blocks,
            stop_reason=stop,
            usage={
                "input_tokens": usage_meta.prompt_token_count if usage_meta else 0,
                "output_tokens": usage_meta.candidates_token_count if usage_meta else 0,
            },
        )
```

- [ ] **Step 6: Update `_call_anthropic()` to extract thinking**

In `_call_anthropic()` (lines 221-263), add thinking extraction to the content block loop:

```python
    async def _call_anthropic(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int | None,
    ) -> LLMResponse:
        """Call Anthropic API using native SDK with extended thinking support."""
        kwargs: dict[str, Any] = {
            "model": self._model,
            "system": system,
            "messages": messages,
            "max_tokens": max_tokens or settings.agent_max_tokens,
        }
        if tools:
            kwargs["tools"] = tools

        # Add extended thinking if enabled
        if settings.agent_thinking_enabled:
            kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": settings.agent_thinking_budget,
            }

        response = await self._client.messages.create(**kwargs)

        content = []
        thinking_text = None
        thinking_tokens = 0
        for block in response.content:
            if block.type == "thinking":
                thinking_text = block.thinking
            elif block.type == "text":
                content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        # Extract thinking tokens from usage if available
        usage = response.usage
        if hasattr(usage, "cache_read_input_tokens"):
            thinking_tokens = getattr(usage, "thinking_tokens", 0)

        return LLMResponse(
            content=content,
            stop_reason=response.stop_reason,
            usage={
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
            },
            thinking=thinking_text,
            thinking_tokens=thinking_tokens,
        )
```

- [ ] **Step 7: Update `create()` dispatcher and client builders**

Update the `create()` method to route to native calls:

```python
    async def create(self, *, system, messages, tools=None, max_tokens=None) -> LLMResponse:
        await self._ensure_initialized()
        if not self._client:
            return LLMResponse(
                content=[{"type": "text", "text": "No LLM provider available."}],
                stop_reason="end_turn",
            )
        if self._provider == "test":
            return await self._client.create(
                system=system, messages=messages, tools=tools, max_tokens=max_tokens,
            )
        if self._provider == "anthropic":
            return await self._call_anthropic(
                system=system, messages=messages, tools=tools, max_tokens=max_tokens,
            )
        if self._provider == "gemini":
            return await self._call_gemini_native(
                system=system, messages=messages, tools=tools, max_tokens=max_tokens,
            )
        # openai, openrouter, ollama — all use OpenAI SDK
        return await self._call_openai_native(
            system=system, messages=messages, tools=tools, max_tokens=max_tokens,
        )
```

Add new client builder methods:

```python
    def _build_openrouter_client(self, *, api_key_override: str = "") -> Any:
        from openai import AsyncOpenAI
        api_key = api_key_override or settings.openrouter_api_key
        return AsyncOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )

    def _build_ollama_client(self) -> Any:
        from openai import AsyncOpenAI
        return AsyncOpenAI(
            api_key="ollama",  # Ollama doesn't need a real key
            base_url=settings.ollama_base_url + "/v1",
        )
```

Update `_ensure_initialized()` to handle the new providers and import from `providers.py` instead of `llm_providers.py`:

```python
from app.services.agent.runtime.providers import (
    PROVIDER_REGISTRY,
    infer_provider_from_model,
)
```

- [ ] **Step 8: Delete `_call_langchain()` and `_anthropic_tools_to_langchain()`**

Remove `_call_langchain()` method (old lines 265-356) and `_anthropic_tools_to_langchain()` helper (old lines 359-368). Delete the import of `resolve_provider_model` and `select_provider` from `llm_providers`.

- [ ] **Step 9: Run tests**

```bash
cd backend && uv run pytest tests/test_agent/test_runtime/test_llm_client.py -v
```

Expected: All PASS including the new native and thinking extraction tests.

- [ ] **Step 10: Commit**

```bash
git add backend/app/services/agent/runtime/llm_client.py backend/tests/test_agent/test_runtime/test_llm_client.py
git commit -m "feat: replace LangChain with native SDKs, add extended thinking"
```

---

### Task 1.5: Delete `llm_providers.py` and Update Dependencies

- [ ] **Step 1: Delete the old module**

```bash
rm backend/app/services/agent/llm_providers.py
```

- [ ] **Step 2: Update `pyproject.toml` — remove LangChain, add google-genai**

In `backend/pyproject.toml`, replace the LLM dependencies (around lines 21-24):

```toml
# Remove these:
#   "langgraph",
#   "langchain-core",
#   "langchain-anthropic",
#   "langchain-google-genai",
#   "langchain-openai",

# Keep these (already present):
#   "anthropic",

# Add:
    "openai>=1.60",
    "google-genai>=1.0",
```

- [ ] **Step 3: Fix any remaining imports**

Search for any remaining references to `llm_providers` or `langchain`:

```bash
cd backend && grep -rn "llm_providers\|langchain\|langgraph" app/ --include="*.py" | grep -v __pycache__
```

Fix all found references. The `DeterministicTestClient` in `llm_providers.py` was a duplicate of the one in `llm_client.py` — no migration needed.

- [ ] **Step 4: Sync dependencies**

```bash
cd backend && uv sync
```

- [ ] **Step 5: Run full test suite**

```bash
cd backend && uv run pytest -v --tb=short
```

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "chore: remove LangChain deps, add google-genai and openai SDKs"
```

---

### Task 1.6: Update User Settings for New Providers

- [ ] **Step 1: Add columns to user_settings model**

In `backend/app/models/user_settings.py`, add after line 18:

```python
    openrouter_api_key: Mapped[str] = mapped_column(String(500), default="")
    ollama_base_url: Mapped[str] = mapped_column(String(500), default="")
    ollama_model: Mapped[str] = mapped_column(String(100), default="")
```

- [ ] **Step 2: Create Alembic migration**

```bash
cd backend && uv run alembic revision --autogenerate -m "add openrouter and ollama to user_settings"
```

- [ ] **Step 3: Apply migration**

```bash
cd backend && uv run alembic upgrade head
```

- [ ] **Step 4: Update schemas**

In `backend/app/schemas/user_settings.py`, add fields to both `UserSettingsRead` and `UserSettingsUpdate`:

```python
class UserSettingsRead(BaseModel):
    anthropic_api_key: str
    openai_api_key: str
    openai_base_url: str
    gemini_api_key: str
    openrouter_api_key: str      # NEW
    ollama_base_url: str          # NEW
    ollama_model: str             # NEW
    selected_provider: str
    selected_model: str
    configured_providers: list[str]


class UserSettingsUpdate(BaseModel):
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    gemini_api_key: str | None = None
    openrouter_api_key: str | None = None  # NEW
    ollama_base_url: str | None = None     # NEW
    ollama_model: str | None = None        # NEW
    selected_provider: str | None = None
    selected_model: str | None = None
```

- [ ] **Step 5: Update user settings service**

In `backend/app/services/user_settings_service.py`, update `get_settings()` to include new providers in `configured_providers`, and update `_auto_select_user_provider()` in `llm_client.py` to check OpenRouter/Ollama keys.

- [ ] **Step 6: Update frontend `use-llm-settings.ts`**

Add "openrouter" and "ollama" to the provider options list and add UI fields for the new keys.

- [ ] **Step 7: Run full tests**

```bash
cd backend && uv run pytest -v --tb=short
```

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "feat: add OpenRouter and Ollama to user settings"
```

---

## Phase 2: Tool Refactor (Subagent 2)

**Scope:** Remove 2 tools, refactor 4 into thin inline handlers, add 3 new tools (glob, grep, web_search), extract ShellTool from legacy, add risk enforcement to loop, update system prompt.

**Dependency:** None (can start immediately, no overlap with Phase 1 files)

**Files:**
- Create: `backend/app/services/agent/tools/shell_tool.py`
- Create: `backend/app/services/agent/tools/web_tools.py`
- Modify: `backend/app/services/agent/tools/file_tools.py` (add GlobTool)
- Modify: `backend/app/services/agent/tools/search_tools.py` (rename code_search → grep)
- Modify: `backend/app/services/agent/tools/__init__.py` (update exports)
- Modify: `backend/app/services/agent/runtime/dispatch.py` (major refactor)
- Modify: `backend/app/services/agent/runtime/loop.py` (add risk enforcement)
- Modify: `backend/app/services/agent/runtime/system_prompt.py` (add CLI guide)
- Delete: `backend/app/services/agent/tools/workflow_tools.py`
- Delete: `backend/app/services/agent/tools/legacy_tools.py`
- Test: `backend/tests/test_agent/test_tools/test_glob.py` (new)
- Test: `backend/tests/test_agent/test_tools/test_grep.py` (new)
- Test: `backend/tests/test_agent/test_tools/test_shell_tool.py` (new)
- Modify: `backend/tests/test_agent/test_runtime/test_llm_client.py` (update DeterministicTestClient)

---

### Task 2.1: Create GlobTool

- [ ] **Step 1: Write test**

Create `backend/tests/test_agent/test_tools/test_glob.py`:

```python
"""Tests for GlobTool."""
from __future__ import annotations

import pytest
from pathlib import Path

from app.services.agent.tools.file_tools import GlobTool


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "sample.fastq.gz").touch()
    (tmp_path / "data" / "sample.bam").touch()
    (tmp_path / "config.wdl").touch()
    (tmp_path / "README.md").touch()
    return tmp_path


@pytest.fixture
def tool(workspace: Path) -> GlobTool:
    return GlobTool(session=None, project_id="test", workspace_root=workspace)


@pytest.mark.asyncio
async def test_glob_finds_fastq(tool, workspace):
    result = await tool.execute(pattern="**/*.fastq.gz")
    assert result.success
    assert "sample.fastq.gz" in result.data


@pytest.mark.asyncio
async def test_glob_finds_by_extension(tool, workspace):
    result = await tool.execute(pattern="**/*.bam")
    assert result.success
    assert "sample.bam" in result.data


@pytest.mark.asyncio
async def test_glob_no_matches(tool, workspace):
    result = await tool.execute(pattern="**/*.vcf")
    assert result.success
    assert result.data == "No files matched pattern '**/*.vcf'"


@pytest.mark.asyncio
async def test_glob_with_subdirectory(tool, workspace):
    result = await tool.execute(pattern="*.wdl", path=".")
    assert result.success
    assert "config.wdl" in result.data


@pytest.mark.asyncio
async def test_glob_rejects_path_traversal(tool, workspace):
    result = await tool.execute(pattern="../../etc/passwd")
    assert not result.success
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_agent/test_tools/test_glob.py -v
```

Expected: FAIL — `GlobTool` not defined.

- [ ] **Step 3: Implement GlobTool**

Add to `backend/app/services/agent/tools/file_tools.py`:

```python
class GlobTool(BaseTool):
    """Find files matching a glob pattern."""

    name = "glob"
    description = "Find files matching a glob pattern. Returns sorted file paths."
    risk_level = RiskLevel.READ

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern (e.g., '**/*.fastq.gz', 'data/*.bam')",
                    },
                    "path": {
                        "type": "string",
                        "description": "Base directory relative to workspace (default: workspace root)",
                    },
                },
                "required": ["pattern"],
            },
        }

    async def execute(self, **kwargs) -> ToolResult:
        pattern = kwargs.get("pattern", "")
        rel_path = kwargs.get("path", ".")

        workspace = self._get_workspace_root()
        if not workspace:
            return ToolResult(success=False, error="No workspace configured")

        base = self._safe_path(rel_path)
        if base is None:
            return ToolResult(success=False, error="Path is outside workspace")

        try:
            matches = sorted(base.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
            if not matches:
                return ToolResult(success=True, data=f"No files matched pattern '{pattern}'")

            lines = []
            for p in matches[:200]:  # cap at 200 results
                try:
                    rel = p.relative_to(workspace)
                    size = p.stat().st_size
                    lines.append(f"{rel}  ({self._format_size(size)})")
                except (ValueError, OSError):
                    continue

            if len(matches) > 200:
                lines.append(f"\n... and {len(matches) - 200} more files")

            return ToolResult(success=True, data="\n".join(lines))
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    @staticmethod
    def _format_size(size: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"
```

- [ ] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/test_agent/test_tools/test_glob.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agent/tools/file_tools.py backend/tests/test_agent/test_tools/test_glob.py
git commit -m "feat: add GlobTool for file pattern matching"
```

---

### Task 2.2: Refactor CodeSearch → GrepTool

- [ ] **Step 1: Write test**

Create `backend/tests/test_agent/test_tools/test_grep.py`:

```python
"""Tests for GrepTool."""
from __future__ import annotations

import pytest
from pathlib import Path

from app.services.agent.tools.search_tools import GrepTool


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "main.py").write_text("def hello():\n    print('world')\n")
    (tmp_path / "config.wdl").write_text("workflow variant_calling {\n  input {\n    File bam\n  }\n}\n")
    return tmp_path


@pytest.fixture
def tool(workspace: Path) -> GrepTool:
    return GrepTool(session=None, project_id="test", workspace_root=workspace)


@pytest.mark.asyncio
async def test_grep_finds_pattern(tool):
    result = await tool.execute(pattern="hello")
    assert result.success
    assert "def hello" in result.data


@pytest.mark.asyncio
async def test_grep_with_glob_filter(tool):
    result = await tool.execute(pattern="workflow", glob="*.wdl")
    assert result.success
    assert "variant_calling" in result.data


@pytest.mark.asyncio
async def test_grep_case_insensitive(tool):
    result = await tool.execute(pattern="HELLO", case_insensitive=True)
    assert result.success
    assert "hello" in result.data


@pytest.mark.asyncio
async def test_grep_no_matches(tool):
    result = await tool.execute(pattern="nonexistent_string_xyz")
    assert result.success
    assert "No matches" in result.data
```

- [ ] **Step 2: Run to verify fail, then implement**

Rename `CodeSearchTool` to `GrepTool` in `backend/app/services/agent/tools/search_tools.py`. Change `name = "code_search"` to `name = "grep"`. Update the schema to add `glob`, `context`, `case_insensitive` parameters. Update the execute method to pass these through to ripgrep.

- [ ] **Step 3: Run tests**

```bash
cd backend && uv run pytest tests/test_agent/test_tools/test_grep.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/agent/tools/search_tools.py backend/tests/test_agent/test_tools/test_grep.py
git commit -m "refactor: rename code_search to grep, add regex and glob filter support"
```

---

### Task 2.3: Create WebSearchTool

- [ ] **Step 1: Write test, then implement**

Create `backend/app/services/agent/tools/web_tools.py`:

```python
"""Web search tool using DuckDuckGo."""
from __future__ import annotations

from app.services.agent.tools.base import BaseTool, RiskLevel, ToolResult


class WebSearchTool(BaseTool):
    """Search the web via DuckDuckGo. No API key needed."""

    name = "web_search"
    description = "Search the web. Returns titles, snippets, and URLs."
    risk_level = RiskLevel.READ

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "description": "Max results (default: 5)"},
                },
                "required": ["query"],
            },
        }

    async def execute(self, **kwargs) -> ToolResult:
        query = kwargs.get("query", "")
        max_results = kwargs.get("max_results", 5)

        if not query.strip():
            return ToolResult(success=False, error="Empty query")

        try:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))

            if not results:
                return ToolResult(success=True, data="No results found.")

            lines = []
            for r in results:
                lines.append(f"**{r.get('title', '')}**")
                lines.append(r.get("body", ""))
                lines.append(r.get("href", ""))
                lines.append("")

            return ToolResult(success=True, data="\n".join(lines))
        except ImportError:
            return ToolResult(success=False, error="duckduckgo-search package not installed")
        except Exception as e:
            return ToolResult(success=False, error=f"Search failed: {e}")
```

Add `duckduckgo-search>=7.0` to `backend/pyproject.toml` dependencies.

- [ ] **Step 2: Test and commit**

```bash
cd backend && uv sync && uv run pytest tests/test_agent/test_tools/ -v --tb=short
git add -A && git commit -m "feat: add WebSearchTool using DuckDuckGo"
```

---

### Task 2.4: Extract ShellTool from Legacy

- [ ] **Step 1: Write test for expanded commands and limits**

Create `backend/tests/test_agent/test_tools/test_shell_tool.py`:

```python
"""Tests for ShellTool (expanded safe_shell)."""
from __future__ import annotations

import pytest
from pathlib import Path

from app.services.agent.tools.shell_tool import ShellTool


@pytest.fixture
def tool(tmp_path: Path) -> ShellTool:
    return ShellTool(session=None, project_id="test", workspace_root=tmp_path)


@pytest.mark.asyncio
async def test_ls_command(tool):
    result = await tool.execute(command="ls")
    assert result.success


@pytest.mark.asyncio
async def test_git_allowed(tool):
    result = await tool.execute(command="git status")
    # May fail if not a git repo, but should not be blocked
    assert result.success or "not a git repository" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_rm_blocked(tool):
    result = await tool.execute(command="rm -rf /")
    assert not result.success
    assert "blocked" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_pipe_blocked(tool):
    result = await tool.execute(command="ls | cat")
    assert not result.success


@pytest.mark.asyncio
async def test_output_not_truncated_at_4k(tool, tmp_path):
    # Create a file larger than 4K
    big = tmp_path / "big.txt"
    big.write_text("x" * 10000)
    result = await tool.execute(command=f"cat {big}")
    assert result.success
    assert len(result.data) > 4000  # Old limit was 4K
```

- [ ] **Step 2: Implement ShellTool**

Create `backend/app/services/agent/tools/shell_tool.py` extracting the safe_shell logic from `legacy_tools.py` with expanded commands and higher limits (120s timeout, 50K char output). Follow the `BaseTool` pattern.

- [ ] **Step 3: Test and commit**

```bash
cd backend && uv run pytest tests/test_agent/test_tools/test_shell_tool.py -v
git add -A && git commit -m "feat: extract ShellTool from legacy with expanded commands"
```

---

### Task 2.5: Refactor Dispatch Map

- [ ] **Step 1: Move domain tools to inline handlers**

In `backend/app/services/agent/runtime/dispatch.py`, replace `_register_legacy_tools()` with:
1. Registration of `ShellTool` as a BaseTool instance
2. Inline async handlers for `search_workflows`, `list_images`, `read_logs`, `validate_workflow`
3. Remove `_LEGACY_TOOL_DEFS` constant

- [ ] **Step 2: Register new tools**

Add `GlobTool`, `GrepTool`, `WebSearchTool` to `build_dispatch_map()`.

- [ ] **Step 3: Delete legacy files**

```bash
rm backend/app/services/agent/tools/legacy_tools.py
rm backend/app/services/agent/tools/workflow_tools.py
```

- [ ] **Step 4: Update `__init__.py` exports**

Remove `AgentTools`, `ALLOWED_COMMANDS`, `MAX_OUTPUT_CHARS` exports. Add new tool imports.

- [ ] **Step 5: Update DeterministicTestClient**

In `llm_client.py`, change the test stub to emit `glob` instead of `scan_dir`:

```python
# In DeterministicTestClient.create(), change:
#   "name": "scan_dir"
# to:
    "name": "glob",
    "input": {"pattern": "**/*"},
```

- [ ] **Step 6: Run full test suite**

```bash
cd backend && uv run pytest -v --tb=short
```

Fix any failures from deleted tools or changed names.

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "refactor: replace legacy tools with BaseTool + inline dispatch handlers"
```

---

### Task 2.6: Add Risk Enforcement to Loop

- [ ] **Step 1: Add risk check before tool execution in `loop.py`**

In `backend/app/services/agent/runtime/loop.py`, add a risk check function and call it before `entry.handler()`:

```python
async def _check_risk(
    entry: ToolEntry,
    tool_input: dict,
    on_event: Callable,
) -> bool:
    """Check tool risk level. Returns True if execution should proceed."""
    if entry.risk_level == RiskLevel.READ:
        return True
    if entry.risk_level == RiskLevel.ACT_LOW:
        # Auto-allowed but logged
        return True
    if entry.risk_level == RiskLevel.ACT_HIGH:
        # Emit approval event and wait (for now, auto-approve with warning log)
        logger.warning("agent.high_risk_tool", tool=entry.schema.get("name", "unknown"))
        return True
    return True
```

Wire this into the tool dispatch section (around line 226).

- [ ] **Step 2: Test and commit**

```bash
cd backend && uv run pytest tests/test_agent/test_runtime/test_loop.py -v
git add -A && git commit -m "feat: add risk-level enforcement to agent loop"
```

---

### Task 2.7: Update System Prompt

- [ ] **Step 1: Add bioinformatics CLI guide to system prompt**

In `backend/app/services/agent/runtime/system_prompt.py`, add a new section to `build_system_prompt()`:

```python
    prompt += """

## Shell Commands

Use `safe_shell` for CLI operations:

### Bioinformatics CLI (`bif`)
- `bif workflow list` — list available pipelines
- `bif workflow search "variant calling"` — search workflows
- `bif workflow validate <id>` — validate workflow config
- `bif image list` — list container images
- `bif image pull <name>` — pull container image
- `bif run list` — list pipeline runs
- `bif run logs <id>` — read run logs
- `bif project list` — list projects

### Version Control
- `git status`, `git diff`, `git log --oneline -20`
- `git add <file>`, `git commit -m "message"`

### File Types (Bioinformatics)
When searching data files:
- Sequences: .fastq, .fastq.gz, .fasta, .fa, .fq
- Alignments: .bam, .sam, .cram, .bai
- Variants: .vcf, .vcf.gz, .bcf, .tbi
- Annotations: .gff, .gtf, .bed
- Configs: .wdl, .nf (workflow definitions)
"""
```

- [ ] **Step 2: Remove references to deleted tools**

Remove mentions of `scan_dir`, `visualize_result` from the system prompt.

- [ ] **Step 3: Test and commit**

```bash
cd backend && uv run pytest tests/test_agent/test_runtime/test_system_prompt.py -v
git add -A && git commit -m "feat: add bioinformatics CLI guide to system prompt"
```

---

## Phase 3: Event System + Thinking UI (Subagent 3)

**Scope:** Add `thinking_content` message type, extend SSE event envelope, implement streaming persistence filter, redesign ThinkingBlock component.

**Dependency:** Starts after Phase 1 Task 1.4 lands `LLMResponse.thinking` field.

**Files:**
- Modify: `backend/app/models/message.py`
- Modify: `backend/app/services/agent/agent_service.py`
- Modify: `backend/app/services/agent/runtime/loop.py`
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/hooks/use-events.ts`
- Modify: `frontend/lib/chat-utils.ts`
- Modify: `frontend/components/bioinfoflow/thinking-block.tsx`
- Modify: `frontend/components/bioinfoflow/chat/message-list.tsx`

---

### Task 3.1: Add `THINKING_CONTENT` MessageType

- [ ] **Step 1: Update backend enum**

In `backend/app/models/message.py`, add to `MessageType` (after line 20):

```python
class MessageType(str, Enum):
    TEXT = "text"
    THINKING = "thinking"
    THINKING_CONTENT = "thinking_content"  # NEW
    ARTIFACT = "artifact"
    PLAN = "plan"
    STATUS = "status"
    COMPLETION = "completion"
```

No Alembic migration needed — `type` column is `String(20)`.

- [ ] **Step 2: Update EVENT_MAP**

In `backend/app/services/agent/agent_service.py`, add to `EVENT_MAP` (line 19):

```python
EVENT_MAP = {
    MessageType.THINKING.value: "agent.thinking",
    MessageType.THINKING_CONTENT.value: "agent.thinking_content",  # NEW
    MessageType.PLAN.value: "agent.plan",
    MessageType.ARTIFACT.value: "agent.artifact",
    MessageType.TEXT.value: "agent.message",
    MessageType.STATUS.value: "agent.message",
    MessageType.COMPLETION.value: "agent.message",
}
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/message.py backend/app/services/agent/agent_service.py
git commit -m "feat: add THINKING_CONTENT message type and event mapping"
```

---

### Task 3.2: Extend SSE Event Envelope

- [ ] **Step 1: Add timestamp, sequence, stream to `_publish_agent_event()`**

In `backend/app/services/agent/agent_service.py`, update `_publish_agent_event()` (lines 507-528):

```python
    _sequence_counter: int = 0  # Add as class attribute

    async def _publish_agent_event(
        self,
        *,
        message_type: str,
        message_id: str,
        project_id: str,
        conversation_id: str,
        content: str,
        metadata: dict | None,
        stream: bool = False,
    ) -> None:
        self._sequence_counter += 1
        event_name = EVENT_MAP.get(message_type, "agent.message")
        await publish_event(
            event=event_name,
            project_id=project_id,
            conversation_id=conversation_id,
            data={
                "id": message_id,
                "type": message_type,
                "content": content,
                "metadata": metadata,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sequence": self._sequence_counter,
                "stream": stream,
            },
        )
```

- [ ] **Step 2: Add streaming persistence filter**

In `_persist_and_publish_agent_event()`, skip DB persistence for streaming deltas:

```python
    async def _persist_and_publish_agent_event(
        self,
        *,
        conversation_id: str,
        project_id: str,
        event: dict,
    ) -> None:
        is_stream = event.get("stream", False)

        if not is_stream:
            # Only persist complete events, not streaming deltas
            message = await self._persist_agent_event(
                conversation_id=conversation_id,
                project_id=project_id,
                event=event,
            )
            message_id = str(message.id)
        else:
            message_id = event.get("id", "stream")

        await self._publish_agent_event(
            message_type=event.get("type") or MessageType.TEXT.value,
            message_id=message_id,
            project_id=project_id,
            conversation_id=conversation_id,
            content=event.get("content") or "",
            metadata=event.get("metadata"),
            stream=is_stream,
        )
```

- [ ] **Step 3: Run tests**

```bash
cd backend && uv run pytest tests/test_api/ -v --tb=short
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/agent/agent_service.py
git commit -m "feat: extend SSE event envelope with timestamp, sequence, stream flag"
```

---

### Task 3.3: Emit Thinking Content from Agent Loop

- [ ] **Step 1: Update loop to emit thinking_content events**

In `backend/app/services/agent/runtime/loop.py`, after the LLM call returns (around line 168), add:

```python
        # Emit thinking content if available (from extended thinking)
        if response.thinking:
            await on_event({
                "type": "thinking_content",
                "content": response.thinking,
                "metadata": {"thinking_tokens": response.thinking_tokens},
            })
```

Also persist a final complete thinking_content message (not streaming delta):

```python
            # Persist the complete thinking content for replay
            await on_event({
                "type": "thinking_content",
                "content": response.thinking,
                "metadata": {"thinking_tokens": response.thinking_tokens},
            })
```

- [ ] **Step 2: Run loop tests**

```bash
cd backend && uv run pytest tests/test_agent/test_runtime/test_loop.py -v
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/agent/runtime/loop.py
git commit -m "feat: emit thinking_content events from agent loop"
```

---

### Task 3.4: Frontend — Subscribe to New Event

- [ ] **Step 1: Update `use-events.ts`**

In `frontend/hooks/use-events.ts`, line 157, add `"agent.thinking_content"`:

```typescript
const agentEvents = [
  "agent.thinking",
  "agent.thinking_content",  // NEW
  "agent.plan",
  "agent.artifact",
  "agent.message",
  "agent.done",
  "agent.cancelled",
]
```

- [ ] **Step 2: Update `types.ts`**

In `frontend/lib/types.ts`, line 318:

```typescript
export type AgentMessageType = "text" | "thinking" | "thinking_content" | "artifact" | "plan" | "status" | "completion"
```

Add `thinkingContent` to `AgentEventData` or wherever `ChatMessage` is defined.

- [ ] **Step 3: Update `chat-utils.ts`**

In `frontend/lib/chat-utils.ts`, update `mapAgentMessage()` (around line 376) to handle `thinking_content`:

```typescript
  if (message.type === "thinking_content") {
    base.thinkingContent = base.content
    base.content = ""  // Don't show thinking as main content
  }
```

Add `thinkingContent?: string` to the `ChatMessage` type (around line 30).

- [ ] **Step 4: Commit**

```bash
git add frontend/hooks/use-events.ts frontend/lib/types.ts frontend/lib/chat-utils.ts
git commit -m "feat: subscribe to thinking_content events, add to ChatMessage"
```

---

### Task 3.5: Redesign ThinkingBlock Component

- [ ] **Step 1: Rewrite `thinking-block.tsx`**

Replace `frontend/components/bioinfoflow/thinking-block.tsx` with the Claude-style design:

```tsx
"use client"

import { useState, useEffect, useMemo } from "react"
import { ChevronDown } from "lucide-react"
import { motion, AnimatePresence, useReducedMotion } from "framer-motion"
import { cn } from "@/lib/utils"

interface ToolTraceItem {
  name: string
  status?: string
  durationMs?: number
  count?: number
}

interface ThinkingBlockProps {
  summary: string[]
  tools?: ToolTraceItem[]
  defaultExpanded?: boolean
  isStreaming?: boolean
  thinkingContent?: string
  thinkingContentStreaming?: boolean
}

const formatDuration = (value?: number) => {
  if (!value && value !== 0) return null
  if (value < 1000) return `${Math.round(value)}ms`
  return `${(value / 1000).toFixed(1)}s`
}

const toolDescriptions: Record<string, string> = {
  search_workflows: "Search workflows",
  list_images: "List images",
  read_logs: "Read logs",
  validate_workflow: "Validate workflow",
  file_read: "Read file",
  file_write: "Write file",
  file_edit: "Edit file",
  glob: "Find files",
  grep: "Search content",
  web_search: "Web search",
  safe_shell: "Run command",
  execute_code: "Execute code",
  run_workflow: "Run workflow",
  scan_dir: "Scan directory",
  todo_write: "Update todos",
  compact: "Compact context",
  load_skill: "Load skill",
  background_run: "Background task",
}

const getToolLabel = (name: string): string =>
  toolDescriptions[name] || name.replace(/_/g, " ")

type ToolStatus = "done" | "active" | "error"

function getStatus(status?: string): ToolStatus {
  if (status === "error") return "error"
  if (status === "ok" || status === "success") return "done"
  return "active"
}

function StatusIcon({ status }: { status: ToolStatus }) {
  if (status === "done") return <span className="text-emerald-500">✓</span>
  if (status === "error") return <span className="text-destructive">!</span>
  return <span className="text-muted-foreground">●</span>
}

export function ThinkingBlock({
  summary,
  tools = [],
  defaultExpanded = false,
  isStreaming = false,
  thinkingContent,
  thinkingContentStreaming = false,
}: ThinkingBlockProps) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const prefersReducedMotion = useReducedMotion()

  const totalDuration = tools.reduce((acc, t) => acc + (t.durationMs || 0), 0)

  // Auto-expand while streaming, auto-collapse when done
  useEffect(() => {
    if (isStreaming || thinkingContentStreaming) {
      setExpanded(true)
    }
  }, [isStreaming, thinkingContentStreaming])

  useEffect(() => {
    if (!isStreaming && !thinkingContentStreaming && expanded && !defaultExpanded) {
      const timer = setTimeout(() => setExpanded(false), 500)
      return () => clearTimeout(timer)
    }
  }, [isStreaming, thinkingContentStreaming, expanded, defaultExpanded])

  const hasContent = !!thinkingContent || tools.length > 0

  return (
    <div>
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 py-1 text-left cursor-pointer"
      >
        {isStreaming || thinkingContentStreaming ? (
          <>
            <motion.span
              className="h-2 w-2 rounded-full bg-foreground/70"
              animate={prefersReducedMotion ? {} : { opacity: [1, 0.3, 1] }}
              transition={{ duration: 1.2, repeat: Infinity, ease: "easeInOut" }}
            />
            <span className="text-sm text-muted-foreground">
              Thinking...
            </span>
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
          </>
        ) : (
          <span className="text-sm text-muted-foreground flex items-center gap-1">
            Thinking{totalDuration ? ` · ${formatDuration(totalDuration)}` : ""}
            {expanded ? (
              <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <span className="text-xs">›</span>
            )}
          </span>
        )}
      </button>

      {/* Expanded content */}
      <AnimatePresence initial={false}>
        {expanded && hasContent && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: prefersReducedMotion ? 0 : 0.2, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <div className="rounded-xl border border-border/50 bg-muted/30 p-4 mt-1">
              {/* Reasoning text */}
              {thinkingContent && (
                <p className="text-sm text-muted-foreground/80 italic leading-relaxed whitespace-pre-wrap mb-3">
                  {thinkingContent}
                </p>
              )}

              {/* Tool pills */}
              {tools.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {tools.map((tool, i) => (
                    <span
                      key={`${tool.name}-${i}`}
                      className={cn(
                        "inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs",
                        "bg-muted text-muted-foreground"
                      )}
                    >
                      <StatusIcon status={getStatus(tool.status)} />
                      {getToolLabel(tool.name)}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
```

- [ ] **Step 2: Update `message-list.tsx` to pass thinkingContent**

In the message-list component, when rendering ThinkingBlock, add:

```tsx
const thinkingContentMessages = turnMessages.filter(m => m.thinkingContent)
const reasoningText = thinkingContentMessages.map(m => m.thinkingContent).join("")

<ThinkingBlock
  summary={allSummary}
  tools={allTools}
  thinkingContent={reasoningText}
  thinkingContentStreaming={isStreaming && turnIndex === turns.length - 1}
  isStreaming={isStreaming && turnIndex === turns.length - 1}
/>
```

- [ ] **Step 3: Run frontend tests and linting**

```bash
cd frontend && bun run lint && bun run build
```

- [ ] **Step 4: Commit**

```bash
git add frontend/components/bioinfoflow/thinking-block.tsx frontend/components/bioinfoflow/chat/message-list.tsx
git commit -m "feat: redesign ThinkingBlock with Claude-style reasoning text + tool pills"
```

---

## Parallelization Strategy

```
Timeline:
  ┌─ Subagent 1: Phase 1 (LLM Providers) ──────────────────────┐
  │ Task 1.1 → 1.2 → 1.3 → 1.4 → 1.5 → 1.6                   │
  │ (~45 min)                                                    │
  └──────────────────────────────┬───────────────────────────────┘
                                 │ LLMResponse.thinking ready
  ┌─ Subagent 2: Phase 2 (Tools) ───────────────────────┐       │
  │ Task 2.1 → 2.2 → 2.3 → 2.4 → 2.5 → 2.6 → 2.7      │       │
  │ (~30 min, starts immediately)                        │       │
  └──────────────────────────────────────────────────────┘       │
                                                                 │
  ┌─ Subagent 3: Phase 3 (Events + UI) ─────────────────────────┤
  │ Task 3.1 → 3.2 → 3.3 → 3.4 → 3.5                           │
  │ (~25 min, starts after Phase 1 Task 1.4)                     │
  └──────────────────────────────────────────────────────────────┘
```

**Subagent 1** and **Subagent 2** start simultaneously — zero file overlap.
**Subagent 3** starts after Subagent 1 completes Task 1.4 (LLMResponse.thinking field exists).

After all 3 subagents complete:
- Run full backend tests: `cd backend && uv run pytest -v`
- Run full frontend build: `cd frontend && bun run build && bun run lint`
- Merge branches if using worktrees
