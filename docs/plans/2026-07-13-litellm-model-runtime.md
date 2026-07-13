# LiteLLM Model Runtime Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development`. Every phase uses TDD, must pass its
> validation gate, and must be committed before the next phase begins.

**Goal:** Refactor Bioinfoflow's model runtime around protocol-neutral
contracts while retaining LiteLLM, then support explicit Chat Completions and
Responses endpoints with a working Codex GPT relay path.

**Architecture:** AgentCore depends on a `ModelGateway` emitting canonical
events. A `LiteLLMBackend` executes either `acompletion()` or `aresponses()`;
Chat and Responses codecs own wire translation. Existing `LlmProvider` records
remain compatible endpoint records and gain an explicit `wire_protocol`.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, Alembic, LiteLLM 1.83,
pytest, Ruff, Next.js 16, React 19, TypeScript, Vitest, Testing Library, ESLint.

---

## Baseline

Recorded on 2026-07-13 from `origin/main` commit `b320b4144`:

- `rtk uv run pytest -q`: `1363 passed, 1 skipped`.
- `rtk uv run ruff check .`: passed.
- Direct relay A/B: Chat Completions returned `503
  no_available_providers`; LiteLLM `aresponses()` completed and returned
  `pong` for `gpt-5.4-mini` with the same endpoint and stored credential.

## Compatibility Invariants

- Existing API paths, provider IDs, model IDs, scopes, credential storage, and
  session selection remain compatible.
- Existing provider rows and templates default to `chat_completions`.
- Current AgentCore tool, approval, resume, interrupt, transcript, ledger, and
  fallback behavior remains available through the new gateway.
- No domain/model/relay-specific protocol guessing.
- No secret leakage through logs, events, transcript, errors, or test status.

## Execution Rules

- Every implementation and review agent must call `create_goal` as its first
  action and work only within its assigned phase/files.
- Before every phase commit, run `rtk git status --short`, inspect the phase
  diff, run the listed gate, and run `rtk git diff --check`.
- Backend command blocks run from `backend/`; frontend blocks run from
  `frontend/`; repository blocks run from the worktree root.
- Every behavior group follows RED (run and observe the expected
  missing-behavior failure), GREEN (minimal implementation and narrow passing
  command), then refactor while keeping the narrow command green.

## Phase 0: Design And Execution Contract

**Files:**

- Create: `docs/plans/2026-07-13-litellm-model-runtime-design.md`
- Create: `docs/plans/2026-07-13-litellm-model-runtime.md`
- Modify: `.gitignore`

- [ ] Review the design against AgentCore, LiteLLM 1.83 APIs, provider catalog,
  migration head `0043`, frontend settings flow, and the real relay evidence.
- [ ] Add narrow `.gitignore` exceptions so both authoritative plan files are
  tracked without unignoring unrelated local plans.
- [ ] From the repository root run `rtk git fetch origin --prune` and
  `rtk git rebase origin/main` before the first commit.
- [ ] Run `rtk git diff --check` from the repository root.
- [ ] Commit with `docs: plan LiteLLM model runtime refactor`.

## Phase 1: Protocol-Neutral Contracts And Chat Compatibility

**Files:**

- Create: `backend/app/services/model_runtime/__init__.py`
- Create: `backend/app/services/model_runtime/contracts.py`
- Create: `backend/app/services/model_runtime/errors.py`
- Create: `backend/app/services/model_runtime/backend/__init__.py`
- Create: `backend/app/services/model_runtime/backend/litellm.py`
- Create: `backend/app/services/model_runtime/codecs/__init__.py`
- Create: `backend/app/services/model_runtime/codecs/base.py`
- Create: `backend/app/services/model_runtime/codecs/chat_completions.py`
- Create: `backend/app/services/model_runtime/gateway.py`
- Create: `backend/tests/test_model_runtime/test_contracts.py`
- Create: `backend/tests/test_model_runtime/test_chat_completions_codec.py`
- Create: `backend/tests/test_model_runtime/test_litellm_backend.py`

- [ ] Write failing contract tests for canonical text/tool parts, typed endpoint
  configuration with redacted credentials, event aggregation, and structured
  errors.
- [ ] Run the new contract tests and confirm they fail because the model runtime
  package does not exist.
- [ ] From `backend/`, run
  `rtk uv run pytest tests/test_model_runtime/test_contracts.py -q`; expected
  result: import/contract failure for the missing model runtime.
- [ ] Implement the minimal immutable contracts and error categories.
- [ ] Re-run the contract test from `backend/`; expected result: pass.
- [ ] Write failing Chat codec tests covering non-stream text/tool/usage and
  stream text/reasoning/tool argument deltas.
- [ ] Run the Chat codec tests and confirm the missing codec failure.
- [ ] From `backend/`, run
  `rtk uv run pytest tests/test_model_runtime/test_chat_completions_codec.py -q`;
  expected result: missing Chat codec behavior.
- [ ] Implement Chat request encoding and response/event decoding by moving,
  not duplicating, the established parsing semantics from AgentCore.
- [ ] Write failing backend dispatch tests proving Chat uses exactly
  `acompletion()` with hidden LiteLLM retries disabled and credentials excluded
  from representations.
- [ ] From `backend/`, run
  `rtk uv run pytest tests/test_model_runtime/test_litellm_backend.py -q`;
  expected result: missing backend dispatch behavior.
- [ ] Implement `LiteLLMBackend` and the gateway registry for Chat.
- [ ] Re-run each narrow test and confirm it passes.
- [ ] From `backend/`, run:

  ```bash
  rtk uv run pytest tests/test_model_runtime -q
  rtk uv run ruff check app/services/model_runtime tests/test_model_runtime
  ```

- [ ] Commit with `refactor: introduce LiteLLM model runtime boundary`.

## Phase 2: Route AgentCore Through ModelGateway

**Files:**

- Modify: `backend/app/services/agent_core/core/loop.py`
- Modify: `backend/app/services/agent_core/runtime.py`
- Modify: `backend/app/services/agent_core/context/assembler.py`
- Modify: `backend/app/services/agent_core/transcript/messages.py`
- Modify: `backend/app/services/agent_core/core/retry.py`
- Modify: `backend/app/services/agent_core/tools/toolsets.py`
- Modify or remove: `backend/app/services/agent_core/core/stream_adapter.py`
- Create: `backend/tests/test_agent_core/test_model_runtime_integration.py`
- Create: `backend/tests/test_model_runtime/test_model_runtime_retry.py`
- Modify: `backend/tests/test_agent_core/test_harness_invariants.py`
- Modify: `backend/tests/test_agent_core/test_runtime_reliability.py`

- [ ] Write a failing integration test that injects a fake `ModelGateway` and
  completes a normal Chat turn without monkeypatching LiteLLM.
- [ ] Add failing fake-gateway tests for tool call/continue, approval pause,
  approve/reject resume, restart resume, cancellation, no-progress, empty
  response, and semantic fallback.
- [ ] Run the focused AgentCore tests and confirm they fail at the missing
  gateway seam.
- [ ] Inject the gateway into `AgentLoopController`; replace provider/model/raw
  request arguments with a typed model target.
- [ ] Move request construction and response parsing fully behind the gateway.
- [ ] Preserve legacy transcript tool-call reading while writing the canonical
  shape.
- [ ] Add dedicated RED/GREEN reliability tests for 429 with `Retry-After`,
  timeout/connection/502-504 retry, 400/401/403 non-retry, replay safety,
  LiteLLM retry disabling, retry-before-fallback ordering, duplicate fallback
  suppression, cancellation, and approval/tool failures not triggering
  fallback.
- [ ] Use a sentinel credential and assert it is absent from `caplog`, ledger
  payloads, turn errors, transcript rows, serialized contracts, and retry/
  fallback events.
- [ ] From `backend/`, run
  `rtk uv run pytest tests/test_model_runtime/test_model_runtime_retry.py tests/test_agent_core/test_runtime_reliability.py -q`;
  expected result: failures showing string-based retry decisions, missing
  replay-safety handling, and unsanitized events.
- [ ] Replace string-based retry decisions with structured `ModelError`
  attributes, disable nested LiteLLM retries, and ensure retry/fallback events
  are redacted.
- [ ] Re-run the same retry/reliability command to GREEN.
- [ ] Prove no LiteLLM imports or provider response parsing remain in loop or
  runtime with `rtk rg` checks.
- [ ] From `backend/`, run:

  ```bash
  rtk uv run pytest tests/test_agent_core/test_model_runtime_integration.py tests/test_agent_core/test_harness_invariants.py tests/test_agent_core/test_runtime_reliability.py -q
  rtk uv run pytest tests/test_model_runtime -q
  rtk uv run ruff check app/services/agent_core app/services/model_runtime tests/test_agent_core tests/test_model_runtime
  rtk rg -n "from litellm|import litellm|choices\[|acompletion|aresponses|response\.output" app/services/agent_core
  ```

  The final `rg` command must return no matches.

- [ ] Commit with `refactor: route AgentCore through model gateway`.

## Phase 3: Persist Wire Protocol And Add LiteLLM Responses

**Files:**

- Create: `backend/app/services/model_runtime/codecs/responses.py`
- Create: `backend/tests/test_model_runtime/test_responses_codec.py`
- Add: `backend/tests/test_model_runtime/fixtures/responses/`
- Create: `backend/alembic/versions/0044_llm_provider_wire_protocol.py`
- Create: `backend/tests/test_migrations/test_llm_provider_wire_protocol.py`
- Modify: `backend/app/models/llm.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/schemas/llm.py`
- Modify: `backend/app/services/llm/provider_templates.py`
- Modify: `backend/app/services/llm/bootstrap.py`
- Modify: `backend/tests/test_services/test_llm_provider_platform.py`
- Modify: `backend/app/services/model_runtime/gateway.py`
- Modify: `backend/app/services/agent_core/runtime.py`
- Modify: `backend/app/services/agent_core/transcript/messages.py`
- Modify: `backend/app/services/agent_core/core/loop.py`
- Modify: `backend/tests/test_agent_core/test_model_runtime_integration.py`

- [ ] Write a failing migration test requiring non-null
  `wire_protocol='chat_completions'`, a known-value constraint, upgrade from
  revision `0043_llm_provider_insecure_http_opt_in`, and downgrade restoration.
- [ ] From `backend/`, run
  `rtk uv run pytest tests/test_migrations/test_llm_provider_wire_protocol.py -q`;
  expected result: missing revision/column.
- [ ] Implement the SQLite-safe migration and ORM constant/field; re-run the
  migration test to GREEN.
- [ ] Write failing schema/template/bootstrap tests for supported/default
  protocols, environment variables, invalid values, and final merged
  `kind + wire_protocol` validation when either or both fields change.
- [ ] From `backend/`, run
  `rtk uv run pytest tests/test_schemas.py tests/test_services/test_llm_provider_platform.py -q`;
  expected result: missing protocol schema/template/bootstrap behavior. Implement
  the minimal support and re-run the same command to GREEN.
- [ ] Write failing non-stream Responses tests for final text, usage, one/many
  function calls, refusal/unknown warnings, and response ID.
- [ ] Write failing stream tests for text phase, reasoning, function argument
  deltas, completion metadata, and arbitrary chunk boundaries.
- [ ] From `backend/`, run
  `rtk uv run pytest tests/test_model_runtime/test_responses_codec.py -q`;
  expected result: missing Responses codec behavior.
- [ ] Write failing integration tests proving commentary never completes a turn,
  final answer does, tool outputs become `function_call_output`, and approval
  resume retains call IDs and protocol after a new service instance.
- [ ] Add the explicit `store=false` continuation case: request encrypted
  reasoning content, persist opaque Responses output items, pause on a tool
  approval, create a new service instance, replay the saved items with the
  matching function output, and reach a final answer.
- [ ] Assert the model snapshot persists endpoint ID and wire protocol before
  approval; a new service instance must resume from the persisted target rather
  than the provider's current default.
- [ ] From `backend/`, run
  `rtk uv run pytest tests/test_agent_core/test_model_runtime_integration.py::test_responses_approval_resume_survives_service_restart -q`;
  expected result: failure caused by missing Responses dispatch and persisted
  continuation metadata, not fixture setup.
- [ ] Implement Responses encoding/decoding using `litellm.aresponses()` through
  the existing backend.
- [ ] Resolve protocol only from `LlmProvider.wire_protocol` and persist it in
  the model snapshot; never infer it.
- [ ] Persist text phase and provider continuation metadata without making it
  canonical transcript identity. Store it only in durable session-scoped
  transcript metadata, omit it from public transcript/API serialization and
  logs, preserve the live chain through compaction, and let it follow existing
  session/transcript retention and deletion.
- [ ] Return deterministic warnings/errors for unsupported or malformed output
  items; never silently discard them.
- [ ] From `backend/`, run:

  ```bash
  rtk uv run pytest tests/test_model_runtime/test_responses_codec.py tests/test_agent_core/test_model_runtime_integration.py -q
  rtk uv run pytest tests/test_migrations/test_llm_provider_wire_protocol.py tests/test_services/test_llm_provider_platform.py -q
  rtk uv run pytest tests/test_model_runtime tests/test_agent_core/test_harness_invariants.py tests/test_agent_core/test_runtime_reliability.py -q
  rtk uv run ruff check app/services/model_runtime app/services/agent_core app/models app/schemas app/services/llm tests/test_model_runtime tests/test_agent_core tests/test_migrations tests/test_services/test_llm_provider_platform.py
  ```

- [ ] Commit with `feat: persist and support LiteLLM Responses protocols`.

## Phase 4: Provider API, Discovery Separation, And Real Probe

**Files:**

- Create: `backend/app/services/llm/probe.py`
- Create: `backend/tests/test_services/test_llm_provider_probe.py`
- Modify: `backend/app/schemas/llm.py`
- Modify: `backend/app/services/llm/catalog.py`
- Modify: `backend/app/api/v1/llm.py`
- Modify: `backend/app/services/agent_core/runtime.py`
- Modify: `backend/tests/test_api/test_llm_api.py`
- Modify: `backend/tests/test_services/test_llm_providers.py`
- Modify: `backend/tests/test_agent_core/test_model_runtime_integration.py`

- [ ] Write failing schema/API/template tests for supported/default protocols,
  compatibility defaults, invalid protocol rejection, final merged
  kind/protocol validation, and round-trip setup.
- [ ] Define `LlmProviderTestRequest(model_id: UUID | None)`. Validate ownership;
  no body deterministically selects the first provider model; no models returns
  a safe failed result rather than an unhandled error.
- [ ] From `backend/`, run the API/service tests and confirm the missing request
  and round-trip behavior before implementing the minimal API changes:

  ```bash
  rtk uv run pytest tests/test_api/test_llm_api.py tests/test_services/test_llm_providers.py -q
  ```

  Expected result: missing test request, protocol round-trip, and
  save/discovery separation behavior. Re-run the same command to GREEN after
  the minimal implementation.
- [ ] Implement explicit protocol validation and persistence. OpenAI and OpenAI
  Compatible support both; other templates initially support Chat only.
- [ ] Separate Save, Discover Models, and Test. Saving a manually supplied model
  must succeed with `discover=false` even if `/models` is unavailable.
- [ ] Write separate failing invalidation tests for provider kind, normalized
  base URL, protocol, credential source/fingerprint, provider template metadata,
  and tested model identity. Unrelated edits preserve valid status.
- [ ] From `backend/`, run
  `rtk uv run pytest tests/test_services/test_llm_providers.py -k test_status_invalidation -q`;
  expected result: credential rotation and configuration changes do not yet
  invalidate status while unrelated edits do not yet preserve it correctly.
- [ ] Include the environment variable name and a non-reversible digest of the
  resolved credential in an internal keyed-HMAC fingerprint; rotating a value
  under the same environment variable name invalidates the status without
  persisting the key. Re-run the same invalidation command to GREEN.
- [ ] Write failing probe tests for Chat success, Responses success, selected
  protocol failure, missing credential, timeout/auth failures, model ownership,
  safe status, and sentinel-secret absence.
- [ ] From `backend/`, run
  `rtk uv run pytest tests/test_services/test_llm_provider_probe.py -q`;
  expected result: missing real probe behavior.
- [ ] Implement `LlmProviderProbe` using the production `ModelGateway` and
  replace `contract_only` testing.
- [ ] Persist an invocation fingerprint and assert the sentinel secret is absent
  from `caplog`, ledger, turn errors, transcript, serialized `ModelError`, retry
  and fallback events, and public `test_status`. Also assert the internal
  fingerprint itself is absent from provider list, configuration response,
  provider test response, logs, and serialized errors.
- [ ] From `backend/`, run:

  ```bash
  rtk uv run pytest tests/test_services/test_llm_provider_probe.py tests/test_services/test_llm_providers.py tests/test_api/test_llm_api.py tests/test_agent_core/test_model_runtime_integration.py -q
  rtk env DATABASE_URL=sqlite+aiosqlite:////tmp/bioinfoflow-wire-protocol.db BIOINFOFLOW_HOME=/tmp/bioinfoflow-wire-protocol-home uv run alembic upgrade head
  rtk uv run ruff check app/schemas app/services/llm app/api/v1/llm.py app/services/agent_core/runtime.py tests/test_services/test_llm_provider_probe.py tests/test_services/test_llm_providers.py tests/test_api/test_llm_api.py tests/test_agent_core/test_model_runtime_integration.py
  ```

- [ ] From the repository root remove only the isolated validation artifacts
  with `rtk rm -rf /tmp/bioinfoflow-wire-protocol.db /tmp/bioinfoflow-wire-protocol-home`.
- [ ] Commit with `feat: probe configured LLM protocols`.

## Phase 5: Provider Protocol And Test UI

**Files:**

- Modify: `frontend/lib/llm/types.ts`
- Modify: `frontend/lib/llm/client.ts`
- Modify: `frontend/hooks/use-llm-catalog.ts`
- Modify: `frontend/components/bioinfoflow/settings/llm-catalog-panel.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`
- Modify: `frontend/tests/unit/components/llm-catalog-panel.test.tsx`
- Modify: `frontend/tests/unit/hooks/use-llm-catalog.test.tsx`
- Modify: `frontend/tests/integration/pages/settings-page-flow.test.tsx`
- Modify: `frontend/tests/e2e/settings-provider-flow.spec.ts`
- Modify: `frontend/tests/e2e/pages/settings-page.ts`

- [ ] Write failing tests for default Chat, saved Responses restoration,
  protocol payload, card-local state, accessibility, test model selection,
  success/failure status, stale status after edits, and write-only credentials.
- [ ] From `frontend/`, run the three focused Vitest files; expected result:
  missing protocol/test UI behavior.
- [ ] Implement typed client/hook support for protocol and provider probe.
- [ ] Show the selector only when the template supports multiple protocols.
- [ ] Keep Save and Test as separate actions and render safe protocol/model/
  latency status.
- [ ] Add complete English and Chinese copy.
- [ ] Add E2E coverage for Responses restoration/payload, selected test model,
  safe success/failure status, and status invalidation after edits.
- [ ] Re-run the focused Vitest files to GREEN.
- [ ] From `frontend/`, run:

  ```bash
  rtk bun run test -- tests/unit/components/llm-catalog-panel.test.tsx tests/unit/hooks/use-llm-catalog.test.tsx tests/integration/pages/settings-page-flow.test.tsx
  rtk bun run lint
  rtk bun run lint:i18n
  rtk bun run lint:dead-code
  rtk bunx playwright test tests/e2e/settings-provider-flow.spec.ts --project=chromium
  ```

- [ ] If visual review is needed, set `AUTH_MODE=dev`, restart services, and
  capture desktop and narrow screenshots of the provider settings flow.
- [ ] Commit with `feat: configure and test LLM wire protocols`.

## Phase 6: Live Relay End-To-End Validation

**Files:**

- Create: `backend/tests/integration/test_live_responses_relay.py`
- Modify: `backend/pyproject.toml`
- Modify: `RUNBOOK.md`

- [ ] Register a `live_relay` marker. The test is skipped unless
  `BIOINFOFLOW_LIVE_RELAY=1`; it reads `BIOINFOFLOW_RELAY_BASE_URL`,
  `BIOINFOFLOW_RELAY_API_KEY`, and `BIOINFOFLOW_RELAY_MODEL`.
- [ ] Write the test first. From `backend/`, run
  `rtk uv run pytest tests/integration/test_live_responses_relay.py -m live_relay -q`;
  expected result: exactly one skip when opt-in is absent.
- [ ] Exercise provider/model selection, AgentCore runtime, LiteLLM Responses,
  completed turn, transcript reload, ledger events, and secret redaction.
- [ ] Catch live provider failures through structured safe errors and assert the
  key is absent from captured logs, ledger, transcript, turn errors, and model
  snapshots.
- [ ] From `backend/`, run the live smoke with existing environment values:

  ```bash
  rtk env BIOINFOFLOW_LIVE_RELAY=1 uv run pytest tests/integration/test_live_responses_relay.py -m live_relay -q --show-capture=no
  ```

  The command line must never contain the key value.
- [ ] From `backend/`, run:

  ```bash
  rtk uv run pytest tests/integration/test_live_responses_relay.py tests/test_model_runtime tests/test_agent_core/test_model_runtime_integration.py tests/test_agent_core/test_runtime_reliability.py -q
  rtk uv run ruff check app/services/model_runtime app/services/agent_core tests/integration/test_live_responses_relay.py tests/test_model_runtime tests/test_agent_core
  ```
- [ ] Commit with `test: cover live LiteLLM Responses relay`.

## Phase 7: Independent Reviews, Fixes, And Publication

- [ ] Every reviewer creates a dedicated goal before inspection. Spawn parallel
  independent reviewers for architecture boundaries,
  Responses/tool/phase state correctness, security/retry/fallback, and
  migration/API/frontend UX.
- [ ] Fix every Critical and Important finding with a failing regression test
  first; re-run the responsible reviewer until approved.
- [ ] Commit review fixes with `fix: address model runtime review findings`.
- [ ] From `backend/`, run:

  ```bash
  rtk uv run pytest
  rtk uv run ruff check .
  rtk env DATABASE_URL=sqlite+aiosqlite:////tmp/bioinfoflow-final-migration.db BIOINFOFLOW_HOME=/tmp/bioinfoflow-final-home uv run alembic upgrade head
  ```

- [ ] From `frontend/`, run:

  ```bash
  rtk bun run test
  rtk bun run lint
  rtk bun run lint:i18n
  rtk bun run lint:dead-code
  rtk bun run build
  rtk bunx playwright test tests/e2e/settings-provider-flow.spec.ts --project=chromium
  ```

- [ ] From the repository root, run:

  ```bash
  rtk git diff --check
  rtk rm -rf /tmp/bioinfoflow-final-migration.db /tmp/bioinfoflow-final-home
  ```

- [ ] Sync `origin/main`, rebase, and repeat the complete backend/frontend
  verification unconditionally after the rebase.
- [ ] Push `codex/litellm-model-runtime` and open a ready-for-review PR with the root cause,
  architecture, migration behavior, validation, live relay result, and review
  conclusions.
