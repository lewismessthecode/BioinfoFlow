# Agent Harness Surface Simplification Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce BioinfoFlow's default model-visible tool surface from 47 tools to a small capability-oriented core, and replace the frontend's dependency on 41 durable event names with an eight-category public event protocol.

**Architecture:** Keep the complete tool registry and durable event ledger because they are useful host extension, compatibility, recovery, and audit mechanisms. Add explicit exposure bundles at the model boundary and a versioned projection at the API boundary. The default agent receives only the primitives needed for ordinary reasoning and coding; domain and remote tools remain registered and become visible only through an explicit policy capability, explicit allowlist, or a selected remote target. The frontend consumes projected public events and normalizes them into its existing internal reducer format, allowing the wire contract to simplify without an all-at-once UI rewrite.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, pytest, TypeScript, Next.js 16, React 19, Vitest.

---

## First-principles constraints

- Registration is not exposure. Keeping a tool implementation costs little context; exposing its schema to every model turn does.
- The default harness should contain primitives, not every product operation. `bash` plus typed read/inspect tools provide a compact escape hatch while permission policy still gates side effects.
- Context should disclose capabilities. Remote tools appear for a selected remote target; product mutation tools require an explicit capability or allowlist.
- Durable events optimize for correctness, recovery, and audit. Public events optimize for a stable frontend contract. They should not be the same type system.
- Compatibility is preserved at deliberate seams: all tools remain registered, explicit `allowed_tools` remains authoritative, legacy user-visible event views remain available, and the frontend normalizes the new public projection before existing reducers see it.

## Target surfaces

The ordinary local execution core is exactly 16 tools:

```python
{
    "ask_user",
    "attachments.read",
    "attachments.search",
    "bash",
    "files.apply_patch",
    "files.read",
    "glob",
    "grep",
    "projects.list",
    "runs.inspect",
    "skills.load",
    "task",
    "todo_write",
    "web.fetch",
    "web.search",
    "workflows.inspect",
}
```

The public event protocol is exactly eight categories:

```python
{
    "action.lifecycle",
    "artifact.created",
    "assistant.content",
    "assistant.tool_call",
    "memory.lifecycle",
    "model.lifecycle",
    "turn.lifecycle",
    "turn.steering",
}
```

## Task 1: Lock the tool exposure contract with failing tests

**Files:**

- Modify: `backend/tests/test_agent_core/test_harness_invariants.py`
- Modify: `backend/tests/test_agent_core/test_toolsets.py`

- [x] Replace the weak subset assertion with an exact execution-core assertion and `len(exposed) == 16`.
- [x] Add exact default and plan surface assertions.
- [x] Add tests proving `bioinfo.read`, `bioinfo.manage`, and `remote` capability bundles opt in registered tools without changing registration.
- [x] Add a compatibility test proving a non-empty explicit `allowed_tools` policy is authoritative even for tools outside the default core.
- [x] Add remote-target tests proving remote read/exec primitives appear contextually while local file/shell tools do not.
- [x] Run the focused tests and confirm they fail because execution currently exposes nearly every registered tool:

```bash
rtk uv run pytest tests/test_agent_core/test_harness_invariants.py tests/test_agent_core/test_toolsets.py tests/test_agent_core/test_execution_scope.py -q
```

## Task 2: Implement explicit capability-oriented exposure

**Files:**

- Modify: `backend/app/services/agent_core/tools/toolsets.py`

- [x] Introduce immutable named sets for `default`, `plan`, and `execution` core tools.
- [x] Introduce immutable capability bundles for `bioinfo.read`, `bioinfo.manage`, and `remote`.
- [x] Resolve exposure in this order: role base -> policy base -> named capabilities -> explicit allowlist -> execution-target compatibility.
- [x] Treat a non-empty `allowed_tools` list as an exact explicit exposure request, bounded to registered non-hidden tools.
- [x] Automatically disclose remote read tools in plan mode and remote execution tools in execution mode only when the selected target is remote SSH.
- [x] Keep `_MODEL_HIDDEN_TOOLS` hidden unless a future host-only path explicitly bypasses model exposure.
- [x] Run the focused tests until green.

## Task 3: Lock the public event projection and visibility boundary with failing tests

**Files:**

- Add: `backend/tests/test_agent_core/test_public_events.py`
- Modify: `backend/tests/test_api/test_agent_core_api.py`

- [x] Add table-driven tests mapping all user-visible durable event families into exactly eight public categories.
- [x] Add tests proving audit/internal events project to no public event.
- [x] Add repository/service tests proving visibility filtering happens in SQL before limits are applied.
- [x] Add state endpoint tests for `event_view=public` and turn endpoint tests for public projection.
- [x] Add SSE tests proving `event_view=public` emits the projected event name and never emits audit/internal events.
- [x] Run the new focused backend tests and confirm the projection/filtering APIs do not yet exist:

```bash
rtk uv run pytest tests/test_agent_core/test_public_events.py tests/test_api/test_agent_core_api.py -q
```

## Task 4: Implement the eight-category public event boundary

**Files:**

- Modify: `backend/app/services/agent_core/events.py`
- Modify: `backend/app/repositories/agent_core_repo.py`
- Modify: `backend/app/services/agent_core/service.py`
- Modify: `backend/app/api/v1/agent.py`

- [x] Add `PublicAgentEventType` and a pure `project_public_event()` function.
- [x] Encode lifecycle subtype as `payload.status` and content/tool-call subtype as `payload.kind` plus `payload.phase`, preserving original domain payload fields.
- [x] Add optional visibility filters to event repository queries; apply filters before ordering/limits.
- [x] Make every HTTP event surface request only `user` visibility.
- [x] Add `public` to state/turn/SSE event views while retaining `full` and `transcript` compatibility views.
- [x] Compact completed stream deltas before public state projection, but keep live SSE deltas.
- [x] Run focused backend tests until green.

## Task 5: Migrate the frontend transport to public events with TDD

**Files:**

- Modify: `frontend/lib/agent-runtime/types.ts`
- Modify: `frontend/lib/agent-runtime/client.ts`
- Modify: `frontend/lib/agent-runtime/event-stream.ts`
- Modify: `frontend/hooks/use-agent-runtime.ts`
- Add: `frontend/lib/agent-runtime/public-events.ts`
- Modify: `frontend/lib/agent-runtime/index.ts`
- Modify: `frontend/tests/unit/lib/agent-runtime/client.test.ts`
- Modify: `frontend/tests/unit/lib/agent-runtime/event-stream.test.ts`
- Add: `frontend/tests/unit/lib/agent-runtime/public-events.test.ts`
- Modify: `frontend/tests/unit/hooks/use-agent-runtime.test.tsx`

- [x] Add failing normalization tests covering all eight public categories and malformed/unknown event rejection.
- [x] Add failing transport tests expecting `event_view=public` and only eight named SSE listeners.
- [x] Implement a small normalization adapter that converts public wire events into the current internal event names before reducers receive them.
- [x] Request the public state view and normalize its events in the API client.
- [x] Request the public stream view and normalize each SSE event.
- [x] Keep reducers, timeline construction, and transcript rendering unchanged in this PR.
- [x] Run focused frontend tests until green:

```bash
rtk bun run test -- tests/unit/lib/agent-runtime/public-events.test.ts tests/unit/lib/agent-runtime/event-stream.test.ts tests/unit/lib/agent-runtime/client.test.ts tests/unit/hooks/use-agent-runtime.test.tsx
```

## Task 6: Verification and architectural review

**Files:**

- Review all changed files.

- [x] Run focused backend Agent Core tests.
- [x] Run the full backend suite and Ruff:

```bash
rtk uv run pytest
rtk uv run ruff check .
```

- [x] Run frontend lint, dead-code lint, and full tests:

```bash
rtk bun run lint
rtk bun run lint:dead-code
rtk bun run test
```

- [x] Run repository hygiene checks:

```bash
rtk git diff --check
rtk git status --short
```

- [x] Request an independent code review focused on security regressions, compatibility, event cursor correctness, and accidental capability loss.
- [x] Fix all Critical and Important findings, then repeat affected verification.

## Task 7: Commit, push, and open the PR

- [x] Sync `origin/main` into the feature branch before publishing.
- [x] Stage only intended files and inspect the staged diff.
- [x] Commit with `refactor: simplify agent capability surfaces`.
- [x] Push `codex/simplify-agent-harness-surfaces`.
- [x] Open a draft PR titled `refactor: simplify agent capability surfaces` with the motivation, boundary design, compatibility notes, and verification results.

## Deferred follow-ups

- Physically remove tool implementations only after usage telemetry proves they are redundant with `bash`, the CLI, or consolidated inspect tools.
- Add host UI/configuration for capability bundles if product workflows need persistent opt-in beyond execution target selection.
- Migrate frontend reducers from normalized legacy event names to the eight public categories, then delete the adapter.
- Version the public protocol independently when a second schema is required; do not reuse durable ledger schema versions.
