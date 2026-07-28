# Subagent Runtime Recovery and Workspace Design

## Goal

Fix the production failure where a successfully spawned child appears stuck,
stop completed-response retry buttons from inheriting unrelated turn activity,
and replace the duplicated child-agent cards with a compact Codex-style agent
workspace.

The design follows two constraints:

- First principles: the durable parent turn, action, tool batch, child turn, and
  public events must tell one consistent lifecycle story.
- Occam's razor: repair the existing Agent Core transaction boundary and reuse
  the existing workspace sidecar instead of introducing another runtime or
  drawer.

## Observed Production Failure

The affected root turn was `f8c9437a-6c04-4551-8f4a-c79bdcad27d7`.

- Two `spawn_agent` actions were prepared in one tool batch at `01:40:38`.
- The first child turn started immediately and completed in 16 seconds.
- The root received the child's terminal result.
- The first parent action never reached `action.completed` or `action.failed`.
- The second spawn action never started.
- The parent tool batch and turn remained active until the user interrupted them
  six minutes later.
- The backend log records `agent_core.runner.failed` with
  `exception_type=MissingGreenlet` immediately after the first child was
  committed.

The child runtime was not stuck. The parent executor crashed while attempting to
finish the spawn tool action.

## Root Cause

`AgentToolExecutor._run_action()` commits `action.started`, retains the SQLAlchemy
ORM `action`, and calls the tool with the same `AsyncSession`.

`AgentCollaborationService.spawn_agent()` performs model preflight and then calls
`await self.db.rollback()` on that shared session. SQLAlchemy rollback expires
the identity map even when `expire_on_commit=False`. The child is then created,
committed, and queued successfully. When control returns to the executor, a
synchronous access such as `str(action.id)` attempts to lazy-refresh the expired
ORM object outside SQLAlchemy's async greenlet and raises `MissingGreenlet`.

The exception occurs after the tool handler's guarded block, so the action,
batch, and parent turn remain non-terminal.

## Runtime Modes

Root and child sessions continue to use the same durable Agent Core runtime.
This change adds no worker process and no second task state machine.

- Root turns may spawn shallow child sessions.
- Child turns remain ordinary queued Agent Core turns.
- Child sessions still cannot expose `spawn_agent`.
- The existing eight-slot root-tree concurrency contract remains unchanged.

## Turn Loop and Tool Boundary

The executor owns the parent action lifecycle. `spawn_agent` already owns a
separate domain transaction because it commits child session, turn, messages,
slot reservation, and lifecycle events before returning. The bug comes from
running that domain transaction on the executor's session.

The repaired boundary is one explicit session boundary at the tool adapter:

1. `SpawnAgentTool.run()` creates a short-lived `AsyncSession` from the current
   database bind.
2. The complete `AgentCollaborationService.spawn_agent()` operation runs in that
   session, including role resolution, model probing/fallback, duplicate and
   capacity checks, child creation, commits, and error rollbacks.
3. The isolated session closes before the tool result returns.
4. The executor's original session and ORM action remain untouched and can
   persist `action.completed` or `action.failed` normally.

This is smaller and more complete than isolating model preflight alone. The
service also rolls back on duplicate-name, capacity, integrity, and cancellation
paths; the whole spawn domain transaction must therefore be isolated. No generic
executor refactor or `MissingGreenlet` suppression is required.

## Canonical Lifecycle Invariants

For every successful asynchronous spawn:

- `spawn_agent` returns after the child turn is durably queued;
- parent action becomes `completed` even while the child is queued or running;
- a batch containing two sequential mutable spawn calls starts both calls;
- parent model continuation receives both tool results;
- parent turn may complete independently from child completion;
- child terminal publication may arrive before or after parent completion;
- no successful child may coexist with a permanently running parent spawn
  action.

If tool execution fails, the action and batch must become terminal and the
parent loop must receive a structured tool result. Background runner exceptions
must never be the only record of failure.

## Retry and Activity State

The current transcript passes the global `hasActiveTurn` value to every
completed response action bar. This makes the retry icon spin on historical
responses whenever any turn is active.

Retry state will be turn-scoped:

- `retryingTurnId` identifies the turn whose retry request is in flight;
- only that response shows the retry spinner;
- unrelated completed responses remain enabled or disabled according to the
  active-turn submission policy, but never appear to be regenerating;
- retry state clears on success, failure, session change, and unmount.

Transcript activity also receives a defensive terminal projection. If a turn is
durably `completed` but an older deployment omitted an `action.completed`
event, any residual `building`, `requested`, `waiting`, or `running` activity is
rendered as completed. Failed and cancelled turns retain their current terminal
projection.

## Child-Agent Workspace

The existing workspace sidecar becomes the single detailed child-agent surface.
No new drawer is introduced.

### Environment Summary

`AgentEnvironmentCard` no longer renders full child cards or a duplicate
"subagents and tools" list. It shows one compact summary entry:

- running count;
- completed count;
- an action that opens the Agents sidecar tab.

Environment metadata, progress, background processes, and sources remain
separate concerns.

### Agents Tab

`agents` is added to the existing `AgentTabbedPanelTab` contract and both desktop
and mobile tab strips.

Wide panels use two columns:

- left: stable child list;
- right: selected child detail.

Narrow panels and mobile overlays use push navigation from list to detail with a
Back action. The list and detail own independent vertical scrolling.

### Agent List

- Active agents appear before terminal agents.
- Each group preserves first-seen order so streaming lifecycle events do not
  reorder rows.
- A row contains status icon, short task name, one-line summary/error preview,
  and elapsed/terminal time.
- The full task path is available through `title` or tooltip.
- Each row is a real button and supports click, Enter, Space, Arrow Up/Down,
  Home, and End.
- Selection is keyed by `childSessionId`, not list index.
- Selected state uses only a neutral gray row background (`bg-muted/60`). There
  is no colored left indicator, colored border, or branded selection accent.
- Hover gray is weaker than selection; keyboard focus remains independently
  visible.

### Agent Detail

The read-only V1 detail shows:

- full task path;
- lifecycle status;
- child session and turn IDs;
- effective model;
- requested-to-effective fallback and reason when present;
- complete final text or complete error code/message/termination reason;
- token usage when present;
- explicit empty-final, interrupted, and error states.

No send, follow-up, or interrupt buttons are added until a dedicated frontend
HTTP contract exists. Model-only collaboration tools are not presented as fake
user controls.

## Data Model

`AgentTreeNode` adds stable presentation metadata derived from lifecycle events:

- `firstSequence`;
- `lastSequence` (replacing the ambiguous presentation use of `sequence`);
- `createdAt`;
- `updatedAt`.

Same-turn terminal status remains monotonic. A new child turn clears the prior
turn's final/error/token fields and updates the detail in place.

Sorting and grouping belong in a pure panel view-model, not in the lifecycle
reducer. The reducer remains responsible only for reconstructing canonical
child state.

## Safety and Observability

- Persist parent action and batch terminal states before continuing the model.
- Keep child errors sanitized at durable/public boundaries.
- Log runner exceptions with turn/session identity and safe exception type.
- Add a runtime regression that proves two spawn calls finish the parent batch.
- Add a regression that proves child completion is not required for parent
  action completion.
- Do not mix the separately observed GPU probe container leak into this patch.
  Track it independently because it has a different owner, reproduction, and
  blast radius.

## Verification

Backend:

- focused runtime integration regression for two `spawn_agent` calls;
- collaboration and tool-batch suites;
- full `uv run pytest`;
- `uv run ruff check .`.

Frontend:

- reducer/view-model tests;
- retry-state and stale-activity tests;
- agent workspace interaction/accessibility tests;
- environment summary and sidecar integration tests;
- `bun run lint`, `bun run lint:i18n`, `bun run test`, and
  `bun run lint:dead-code`.

Repository:

- `git diff --check`;
- visual verification at wide, narrow desktop, and mobile widths.
