# Agent Trace View Plan

## Status

Accepted for implementation on 2026-08-17.

## Goal

Add the selected `02 Event Rail / 轨迹优先` design to the existing Agent page.
The Conversation and Trace are sibling tabs. The Trace shows one complete Agent
session in occurrence order, grouped by Turn, with a compact Context Flow and an
event inspector. The browser depends only on a stable Agent Trace Contract; the
current Harness is one replaceable adapter.

## Product invariants

1. **Session-wide:** every completed and active Turn in the current session is
   visible in one ordered Trace.
2. **Truthful:** raw model and tool payloads are shown as persisted. Missing
   token, cache, schema, or timing data stays absent; the UI never invents it.
3. **Quiet by default:** the primary rail contains only event identity, useful
   content, state, and hierarchy. Exact timestamps and large payloads live in
   the inspector.
4. **Replaceable:** frontend code imports only the Trace Contract and Trace View
   Model. Harness and provider types stop at the backend adapter.
5. **Credential-safe:** exact payload means exact provider content, but API keys,
   authorization headers, and request-scoped clients are never captured.

## Scope

Included:

- `对话 / 轨迹` tabs for persisted sessions;
- ordered `System / User / Context / Assistant / Tool` events grouped by Turn;
- compact Context Flow aligned with the timeline;
- click-to-inspect `Summary / Payload / Result / Schema / Timing` tabs;
- exact provider request and response/chunks captured at the model-runtime seam;
- actual input, output, cached-input, reasoning, and total token counts when the
  provider reports them;
- desktop inspector aside and narrow-screen inspector sheet;
- stable contracts, adapter tests, API tests, UI tests, visual verification, and
  accessibility checks.

Excluded:

- OpenTelemetry, generic platform spans, workflow-run observability, cost
  accounting, or cross-service tracing;
- a second live event stream;
- inferred token-category counts or synthetic cache values;
- provider-specific branches in React components;
- secrets or transport-only client objects in persisted raw payloads.

## Architecture

```text
Current Harness persistence          Future Harness persistence
  session/run/entries                  implementation-specific records
  model trace records                           |
          |                                     |
          v                                     v
 CompleteHarnessTraceAdapter             FutureTraceAdapter
          +------------------+------------------+
                             v
                  Agent Trace Contract v1
                    timeline + detail API
                             |
                             v
              transport validator / projection
                             |
                             v
                    AgentTraceViewModel
                             |
             Context Flow / Event Rail / Inspector
```

The existing Presentation Contract remains unchanged and continues to power the
Conversation tab. Trace data is a sibling read model, not conversation history.

### Persistence

Add a dedicated `agent_model_traces` table instead of inserting raw exchanges
into `agent_entries`. One row represents one model attempt and belongs to a
session and run. It stores:

- provider, model, wire protocol, attempt, status;
- compiled request before `api_base`, `api_key`, and client injection;
- raw non-streaming response or ordered raw streaming chunks;
- logical context snapshot and tool definitions;
- usage including cache and reasoning tokens;
- request, first-byte, and completion timestamps plus duration;
- provider error metadata when the attempt fails.

Large raw data is returned only by the event-detail endpoint. The timeline API
returns compact summaries and usage.

### Backend seams

- `ModelExchangeObserver` is a generic model-runtime callback interface.
- `AgentModelTraceRecorder` implements the observer using Agent persistence.
- `CompleteHarnessTraceAdapter` implements `AgentTraceSource` and projects
  current Harness records into the stable contract.
- `GET /api/v1/agent/sessions/{session_id}/trace` returns the compact session
  trace.
- `GET /api/v1/agent/sessions/{session_id}/trace/events/{event_id}` returns the
  inspector detail.

Turn IDs map to ordered Harness Runs in the current adapter. Event ordering uses
durable entry sequence plus model-attempt timing; this mapping is private to the
adapter.

### Frontend seams

```text
trace endpoint
  -> transport/trace-contract.ts
  -> projection/trace-projection.ts
  -> trace-model/types.ts
  -> use-agent-trace.ts
  -> agent-trace-view.tsx
```

The Trace tab fetches on first activation and revalidates when reopened. The
Conversation content stays mounted while hidden so Composer draft state is not
lost. Raw detail is fetched only after an event is selected.

## Visual specification: 02 Event Rail

- A compact Context Flow sits directly below the sibling tabs. It is an append
  history across Turns, not a token-budget progress bar.
- The main rail groups events by Turn and preserves occurrence order. Category,
  hierarchy, state, and a useful first line form the visible hierarchy.
- The primary rail does not show exact timestamps.
- The inspector is closed until selection, then occupies roughly `320px` on
  desktop and a Sheet on narrow screens.
- Neutral semantic surfaces, restrained borders, existing typography and theme
  tokens, no gradients, glass effects, or decorative copy.
- Long raw values use a bounded monospace viewer; only the selected raw payload
  is mounted.

## TDD vertical slices and commits

1. **Plan and vocabulary**
   - Commit this plan and the approved Trace domain vocabulary.
2. **Trace storage and runtime capture**
   - Write failing recorder/gateway tests.
   - Add migration, model, repository, observer, safe raw serialization, timing,
     and complete usage capture.
3. **Stable backend contract and adapter**
   - Write failing projection/API tests.
   - Add compact trace and event-detail contracts, adapter, ownership checks,
     and endpoints.
4. **Frontend contract and state**
   - Write failing parser/projection/client/hook tests.
   - Add strict normalization, unknown-event fallback, lazy detail fetch, and
     loading/error state.
5. **02 Event Rail UI**
   - Write failing workbench and interaction tests.
   - Add sibling tabs, Context Flow, Turn rail, event selection, five inspector
     tabs, responsive Sheet, and bilingual labels.
6. **Visual hardening**
   - Verify desktop/tablet/mobile, light/dark, keyboard, reduced motion, long
     payloads, active sessions, and LiveDeck coexistence.
7. **Review and delivery**
   - Run full backend/frontend verification, two-pass review, rebase on
     `origin/main`, push, open PR, and merge through the repository gate.

## Verification

Backend:

```bash
rtk uv run pytest tests/test_model_runtime tests/test_agent_harness
rtk uv run pytest
rtk uv run ruff check .
```

Frontend:

```bash
rtk bun run test
rtk bun run lint
rtk bun run lint:i18n
rtk bun run lint:dead-code
```

Repository and browser:

```bash
rtk git diff --check
```

- `/agent/{sessionId}` at 1440px, 1024px, and 390px;
- light and dark themes;
- keyboard selection and inspector tabs;
- Conversation/Trace switching with an unsent Composer draft;
- long raw JSON and an unknown event;
- inspector with LiveDeck open and closed.

## Completion criteria

- The selected 02 design is integrated into the real Agent page.
- The Trace renders the full session and every current Harness Turn in order.
- Exact model/tool content is inspectable without persisting credentials.
- Missing telemetry is absent rather than fabricated.
- Replacing the Harness requires a backend adapter, not frontend changes.
- Focused and full verification pass, visual evidence is captured, review
  findings are resolved, and the PR is merged.
