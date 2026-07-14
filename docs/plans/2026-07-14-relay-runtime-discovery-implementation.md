# Relay Runtime and Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make LiteLLM public-network calls valid for Chat and Responses, restore blank-Model-ID discovery, use endpoint UUIDs for model selection, and bound/diagnose model request failures.

**Architecture:** LiteLLM remains a one-attempt network backend. Bioinfoflow owns transport policy, retry, timeout, safe errors, model discovery orchestration, and durable provider/model identity. The frontend saves provider configuration first, then performs best-effort discovery when the user did not enter a model ID.

**Tech Stack:** Python 3.12, FastAPI, LiteLLM, aiohttp/httpx, pytest, TypeScript, React 19, Next.js 16, Vitest, Testing Library.

---

## File Map

- `backend/app/services/model_runtime/backend/litellm_network.py`: expose the validated request-scoped aiohttp session while retaining lifecycle ownership.
- `backend/app/services/model_runtime/backend/litellm.py`: bind `public_only` through LiteLLM's `shared_session` contract and normalize timeout errors.
- `backend/app/services/agent_core/core/loop.py`: enforce the model-attempt deadline and emit safe retry metadata.
- `backend/app/services/agent_core/core/types.py`: carry optional safe model failure metadata.
- `backend/app/services/agent_core/runtime.py`: include safe failure metadata in terminal events/logs.
- `backend/app/config.py` and `.env.example`: define the model-attempt timeout.
- `frontend/components/bioinfoflow/settings/llm-catalog-panel.tsx`: orchestrate save-then-discover for blank Model ID.
- `frontend/hooks/use-llm-catalog.ts`: return structured discovery success/failure outcomes.
- `frontend/hooks/use-llm-settings.ts`: separate endpoint UUID identity from provider kind and migrate legacy selection.
- `frontend/components/bioinfoflow/chat/model-selector.tsx`: group/select by endpoint UUID and render by provider display name/kind.
- `frontend/components/bioinfoflow/composer-selector-chip.ts`: prevent vertical glyph clipping.
- locale JSON files: add non-fatal discovery and safe runtime status copy if required.

### Task 1: Correct LiteLLM Public-Network Transport

**Files:**
- Modify: `backend/tests/test_model_runtime/test_litellm_backend.py`
- Modify: `backend/app/services/model_runtime/backend/litellm_network.py`
- Modify: `backend/app/services/model_runtime/backend/litellm.py`

- [ ] **Step 1: Write failing transport contract tests**

Add tests that call the real LiteLLM `acompletion` and `aresponses` entrypoints against an in-process mock HTTP endpoint. Parameterize Chat/Responses and streaming/non-streaming. Assert `public_only` reaches the endpoint and never raises the previous `client.api_key` internal error. Update injected-call tests to require `shared_session` and forbid `client`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `rtk uv run pytest tests/test_model_runtime/test_litellm_backend.py -q`

Expected: the Chat public-only regression fails because `PublicNetworkHTTPHandler` is passed as `client`.

- [ ] **Step 3: Implement request-scoped shared-session binding**

Expose a read-only `shared_session: ClientSession` property on `PublicNetworkHTTPHandler`. In `LiteLLMBackend.invoke`, set `shared_session=policy_client.shared_session` for public-only requests and do not set `client`. Keep the handler alive until a returned stream completes, then close it exactly once.

- [ ] **Step 4: Verify GREEN and regression scope**

Run:

```bash
rtk uv run pytest tests/test_model_runtime/test_litellm_backend.py tests/test_model_runtime/test_chat_completions_codec.py tests/test_model_runtime/test_responses_codec.py -q
rtk uv run ruff check app/services/model_runtime tests/test_model_runtime
```

Expected: all selected tests pass and Ruff reports no errors.

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/services/model_runtime/backend/litellm.py backend/app/services/model_runtime/backend/litellm_network.py backend/tests/test_model_runtime/test_litellm_backend.py
rtk git commit -m "fix: bind LiteLLM public transport correctly"
```

### Task 2: Restore Blank-Model Discovery Without Partial Failure

**Files:**
- Modify: `frontend/tests/unit/components/llm-catalog-panel.test.tsx`
- Modify: `frontend/tests/unit/hooks/use-llm-catalog.test.tsx`
- Modify: `frontend/tests/integration/pages/settings-page-flow.test.tsx`
- Modify: `frontend/components/bioinfoflow/settings/llm-catalog-panel.tsx`
- Modify: `frontend/hooks/use-llm-catalog.ts`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`

- [ ] **Step 1: Write failing discovery orchestration tests**

Cover four behaviors: discoverable template plus blank Model ID calls setup with `discover:false` and then discovers using the returned provider ID; explicit Model ID skips discovery; static templates skip discovery; discovery failure still clears the dirty state and reports that configuration was saved.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
rtk bun run test tests/unit/components/llm-catalog-panel.test.tsx tests/unit/hooks/use-llm-catalog.test.tsx tests/integration/pages/settings-page-flow.test.tsx
```

Expected: blank Model ID does not call discovery and the new tests fail.

- [ ] **Step 3: Implement save-then-discover**

Keep setup `discover:false`. After setup succeeds, if `cleanModelIds(values.model_id)` is empty and `template.discovery !== "static"`, call discovery with `result.provider.id`. Treat `null` as non-fatal failure, `[]` as an empty-result warning, and a non-empty result as success. Preserve provider save success and existing models in every discovery outcome.

- [ ] **Step 4: Verify frontend checks**

Run:

```bash
rtk bun run test tests/unit/components/llm-catalog-panel.test.tsx tests/unit/hooks/use-llm-catalog.test.tsx tests/integration/pages/settings-page-flow.test.tsx
rtk bun run lint
rtk bun run lint:i18n
```

Expected: all tests and lint commands pass.

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/components/bioinfoflow/settings/llm-catalog-panel.tsx frontend/hooks/use-llm-catalog.ts frontend/messages/en.json frontend/messages/zh-CN.json frontend/tests/unit/components/llm-catalog-panel.test.tsx frontend/tests/unit/hooks/use-llm-catalog.test.tsx frontend/tests/integration/pages/settings-page-flow.test.tsx
rtk git commit -m "fix: discover models after provider setup"
```

### Task 3: Make Provider Selection Endpoint-Stable

**Files:**
- Modify: `frontend/tests/unit/hooks/use-llm-settings.test.ts`
- Modify: `frontend/tests/unit/components/model-selector.test.tsx`
- Modify: `frontend/hooks/use-llm-settings.ts`
- Modify: `frontend/components/bioinfoflow/chat/model-selector.tsx`
- Modify: `frontend/components/bioinfoflow/composer-selector-chip.ts`

- [ ] **Step 1: Write failing identity and layout tests**

Add two providers with the same kind and identical model slugs. Assert separate headings, unique React groups, endpoint UUID selection, correct model UUID persistence, and deterministic migration from an unambiguous legacy kind value. Assert the composer trigger includes a non-clipping line height/minimum height class.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
rtk bun run test tests/unit/hooks/use-llm-settings.test.ts tests/unit/components/model-selector.test.tsx
```

Expected: provider groups collide because `provider.kind` is the identity.

- [ ] **Step 3: Implement identity separation**

Change `ProviderModels.provider` to the endpoint UUID and add `provider_kind`. Build groups with `provider.id`, render icons with `provider_kind`, and key groups with `provider_id`. Persist endpoint UUID in the existing provider storage key. Resolve legacy kind-based values only when exactly one group matches both kind and model; otherwise select the first valid model. Raise the chip from fixed 26px/`leading-none` to a non-clipping minimum height and readable line height.

- [ ] **Step 4: Verify unit, lint, and visual behavior**

Run:

```bash
rtk bun run test tests/unit/hooks/use-llm-settings.test.ts tests/unit/components/model-selector.test.tsx
rtk bun run lint
```

Then start the app with `AUTH_MODE=dev`, open `/agent`, and verify two same-kind providers remain distinct and `gpt-5.4-mini` is not clipped at 100% and 125% zoom.

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/hooks/use-llm-settings.ts frontend/components/bioinfoflow/chat/model-selector.tsx frontend/components/bioinfoflow/composer-selector-chip.ts frontend/tests/unit/hooks/use-llm-settings.test.ts frontend/tests/unit/components/model-selector.test.tsx
rtk git commit -m "fix: identify model providers by endpoint"
```

### Task 4: Bound Model Calls and Preserve Safe Diagnostics

**Files:**
- Modify: `backend/tests/test_agent_core/test_model_runtime_integration.py`
- Modify: `backend/tests/test_agent_core/test_observability.py`
- Modify: `backend/app/config.py`
- Modify: `.env.example`
- Modify: `backend/app/services/agent_core/core/types.py`
- Modify: `backend/app/services/agent_core/core/loop.py`
- Modify: `backend/app/services/agent_core/runtime.py`

- [ ] **Step 1: Write failing timeout and metadata tests**

Use a gateway that never yields to assert a configured model-attempt timeout ends the turn as `model_request_failed` with category `timeout`. Assert retry events and terminal events include only safe fields: `category`, `http_status`, `provider_code`, `request_id`, `retryable`, and `replay_safe`. Add a semantic-delta-then-timeout case and assert it is not replayed.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
rtk uv run pytest tests/test_agent_core/test_model_runtime_integration.py tests/test_agent_core/test_observability.py -q
```

Expected: the never-yielding gateway is not bounded and structured fields are absent.

- [ ] **Step 3: Implement timeout and safe failure projection**

Add `agent_model_attempt_timeout_seconds` with a conservative default of 120 seconds. Wrap each `_consume_model_events` attempt in `asyncio.timeout`. Convert expiry to `ModelError(category="timeout", message="The model provider request timed out.", retryable=True, replay_safe=True)`; gateway replay-safety handling changes it to false after semantic output. Extend `LoopResult` with an optional safe failure dictionary and include it in retry/terminal event payloads and structured logs without raw exception text.

- [ ] **Step 4: Verify backend reliability suite**

Run:

```bash
rtk uv run pytest tests/test_agent_core/test_model_runtime_integration.py tests/test_agent_core/test_runtime_reliability.py tests/test_agent_core/test_observability.py tests/test_services/test_llm_provider_probe.py -q
rtk uv run ruff check app/services/agent_core app/services/model_runtime tests/test_agent_core tests/test_model_runtime tests/test_services/test_llm_provider_probe.py
```

Expected: all selected tests pass and no secret-bearing values appear in event assertions.

- [ ] **Step 5: Commit**

```bash
rtk git add .env.example backend/app/config.py backend/app/services/agent_core/core/types.py backend/app/services/agent_core/core/loop.py backend/app/services/agent_core/runtime.py backend/tests/test_agent_core/test_model_runtime_integration.py backend/tests/test_agent_core/test_observability.py
rtk git commit -m "fix: bound model attempts and expose safe errors"
```

### Task 5: Integrated Validation and Review

- [ ] **Step 1: Run backend verification**

```bash
rtk uv run pytest
rtk uv run ruff check .
```

- [ ] **Step 2: Run frontend verification**

```bash
rtk bun run test
rtk bun run lint
rtk bun run lint:i18n
rtk bun run lint:dead-code
```

- [ ] **Step 3: Run live relay checks without printing credentials**

Use the existing opt-in live relay test with the configured secret source. Verify model discovery, a non-streaming Responses probe, and an AgentCore streaming Responses turn. Record only status/category/request IDs and endpoint paths.

- [ ] **Step 4: Dispatch parallel review**

Assign separate reviewers to runtime/security, provider discovery/API compatibility, and frontend identity/UX. Fix every validated finding with a failing test, rerun the relevant phase verification, and commit review fixes.

- [ ] **Step 5: Sync and publish**

```bash
rtk git fetch origin --prune
rtk git rebase origin/main
rtk git push -u origin codex/fix-relay-runtime-discovery
```

Open a ready PR with Conventional Commit title `fix: make relay model setup and runtime reliable`.

