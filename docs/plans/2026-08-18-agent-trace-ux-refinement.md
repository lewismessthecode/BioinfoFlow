# Agent Trace UX Refinement Plan

## Status

Implemented and verified.

## Goal

Refine the existing `02 Event Rail` trace view so the top area follows the
familiar storage-capacity mental model, model requests remain navigable across
the whole Conversation, the event rail scans like a developer tool instead of
a card feed, and the Inspector prioritizes failure diagnosis.

The frontend continues to consume only the stable Agent Trace Contract and its
Harness-independent View Model. No React component may import Harness or
provider types.

## Confirmed product model

- A Conversation contains the complete task history.
- A Turn is one user-meaningful unit of work and may contain multiple model
  requests.
- Each model request owns one Context Snapshot.
- Context capacity is `input_tokens / max_context_tokens`; output and total
  usage do not increase the request's submitted context occupancy.
- Cached input remains part of the logical Context Snapshot and is shown as an
  auxiliary metric, not as a content category.
- The request navigator shows Conversation evolution. The Context Window bar
  shows the selected request's capacity. These are separate visual components.
- Missing telemetry stays visibly unavailable. The UI never renders an unknown
  context limit as a full bar and never fabricates category token counts.

## Scope

Included:

- replace the weighted append strip with a storage-style Context Window bar;
- show exact used, limit, used percentage, cache, output, and reasoning
  metrics only when reported;
- split the top area into capacity composition and a compact Turn/request
  navigator;
- default to the latest model request and synchronize event selection with its
  nearest Context Snapshot;
- reduce event-card weight, repeated phase noise, and unreadably wide text;
- keep long raw content and exact payloads in the Inspector;
- widen and refine the Inspector, with failure status and useful summary facts
  above its tabs;
- preserve desktop aside and narrow-screen Sheet behavior;
- update English and Simplified Chinese copy;
- browser-level visual verification in dark and light themes.

Excluded:

- backend contract v2, new trace persistence, provider-specific UI branches;
- inferred token totals, cost accounting, OpenTelemetry, workflow spans;
- changing Conversation transcript behavior;
- teaching copy or explanatory cards inside the work surface.

## Adapter boundary

```text
current or future Harness records
  -> backend AgentTraceSource adapter
  -> Agent Trace Contract v1
  -> frontend transport validator
  -> trace projection / trace-model
  -> Context Window + Request Navigator + Event Rail + Inspector
```

`context_flow` remains the transport name. The projection may derive request
ordinals and display metadata, but React must not infer Harness IDs or provider
event shapes. In particular, the UI must not manufacture a `model:` event ID
from `model_trace_id`.

## TDD seams and vertical slices

1. **Context Window model**
   - Red: exact `13.4K / 200K`, clamped over-capacity, and unknown-limit cases.
   - Green: add a Harness-independent capacity/composition presentation helper.
   - Red: cached input is auxiliary and total/output do not affect occupancy.
   - Green: expose only truthful display metrics.
2. **Request navigation**
   - Red: requests group by Turn, retain sequence order, and receive per-Turn
     ordinals.
   - Green: derive navigation presentation from the Harness-independent View
     Model without inferring provider or Harness identifiers.
   - Red: latest request is selected initially; clicking a request updates the
     capacity view; selecting an event synchronizes to the containing request.
   - Green: implement accessible request buttons and selection behavior.
3. **Event Rail hierarchy**
   - Red: primary rows remain compact, raw multiline content is opt-in, and
     semantic status is not repeated for passive System/User facts.
   - Green: replace equal-weight cards with dividers, restrained selection, and
     bounded readable summaries.
4. **Inspector diagnosis**
   - Red: failed tools expose failure state before tab content; all five exact
     detail tabs remain lazy and unchanged.
   - Green: widen the aside, add compact event identity/status header, and keep
     the responsive Sheet.
5. **Polish and delivery**
   - update both locale files and i18n tests;
   - run focused tests after each slice, then full frontend verification;
   - verify 1440px, 1024px, and 390px layouts in light and dark themes;
   - capture visual evidence, review the diff, rebase on `origin/main`, and
     deliver through the repository PR workflow.

## Visual acceptance

- The capacity track's full width means the model limit.
- Used composition occupies only its truthful percentage; unused capacity is a
  quiet neutral remainder.
- Unknown capacity has an explicitly unavailable neutral state, never a full
  bar.
- Turn labels appear once per group; model requests appear as compact nodes,
  not equal-width blocks.
- One accent treatment communicates selection.
- The rail can be scanned without reading full prompts or JSON.
- Failed Tool events and their Inspector state are unmistakable without using
  decorative warnings or explanatory prose.
- The design remains coherent with the existing Agent page in both themes.

## Verification

```bash
cd frontend
rtk bun run test -- tests/unit/lib/agent/projection/trace-projection.test.ts
rtk bun run test -- tests/integration/components/agent-trace-view.test.tsx
rtk bun run test
rtk bun run lint
rtk bun run lint:i18n
rtk bun run lint:dead-code
rtk bun run build

cd ..
rtk git diff --check
```

Completed on 2026-08-18:

- full frontend suite: 181 files, 1002 tests passed;
- ESLint, i18n coverage, Knip dead-code, production build, and diff checks
  passed;
- browser verification used the real local Agent Trace Contract fixture plus
  deterministic network variants for failed Tool and unknown-capacity states;
- screenshots cover 1440px light/dark, 1024px Sheet, 390px narrow layout,
  model-request synchronization, failed Tool diagnosis, and unavailable
  capacity;
- no backend, Harness, transport-contract, or projection-contract changes were
  required.
