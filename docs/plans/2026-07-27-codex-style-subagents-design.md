# Codex-Style Subagents Design

## Goal

Replace BioinfoFlow's synchronous, read-only `task` and `subagent.analyze`
implementations with a durable Codex-style agent tree. A root agent can spawn,
observe, message, reuse, wait for, and interrupt child agents. Child agents run
the normal Agent Core loop but cannot create or coordinate other agents.

The design follows two constraints:

- First principles: an agent is a durable session plus turns, messages, events,
  permissions, and model configuration—not a special RPC result.
- Occam's razor: reuse Agent Core's existing durable primitives instead of
  adding another task runtime, process manager, or orchestration database.

## Reference Contract

The model-visible collaboration surface mirrors Codex's current tools:

- `spawn_agent`
- `send_message`
- `followup_task`
- `wait_agent`
- `list_agents`
- `interrupt_agent`

Hermes contributes bounded concurrency, structured lifecycle events, visible
failure diagnostics, and interrupt discipline. Goose contributes explicit
background task observation and optional provider/model overrides. pi.dev
confirms that per-agent model and tool selection are useful, but its subprocess
isolation is unnecessary because BioinfoFlow already has a durable agent
runtime.

Deliberately omitted from this phase:

- child-to-grandchild spawning;
- arbitrary agent roles or role-routing heuristics;
- cross-root communication;
- separate worker processes;
- a second durable task state machine;
- automatic file partitioning for parallel writers.

## Runtime Modes

The existing Agent Core runtime remains canonical for both root and child
agents. The only runtime distinction is collaboration capability:

- Root/orchestrator sessions may see the six collaboration tools.
- Child sessions use the same turn loop and ordinary tool executor but never
  see collaboration tools.

The default tree concurrency budget is eight live slots including the root, so
one root may have at most seven live children. The limit is configurable and
enforced transactionally before a child session is created.

## Turn Loop

`spawn_agent` creates a child session and queues its first turn through the
existing `AgentCoreService.create_turn()` path. It does not call
`runtime.run_turn()` inline and does not wait for completion.

The existing loop continues to own:

- model invocation and fallback;
- tool execution and approvals;
- steering delivery at safe message boundaries;
- interrupts;
- iteration and token budgets;
- terminal status and startup recovery.

Child completion produces a durable parent-mailbox notification. The parent
can continue useful work and later call `wait_agent`; no polling loop is needed
inside the model.

## Tool Model

### `spawn_agent`

Input:

- `task_name`: lowercase letters, digits, and underscores; unique among live
  siblings.
- `message`: initial child task.
- `fork_turns`: `"none"`, `"all"`, or a positive integer encoded as a string.
- optional `model` and `reasoning_effort` overrides.

Output:

- child session/agent ID;
- canonical task path;
- initial status;
- requested and effective model;
- whether model fallback occurred and a safe fallback reason.

### `send_message`

Persist a message for an existing child. If its turn is active, deliver the
message through the existing steering boundary. If it is idle, retain the
message without starting a turn.

### `followup_task`

Reuse an existing child. If idle, create a new turn. If active, persist the
follow-up and deliver it at a safe boundary; any still-pending follow-up starts
after the active turn becomes terminal.

### `wait_agent`

Wait for a mailbox update from any live child, a parent-turn steer, or a bounded
timeout. Results summarize which agents have updates; the durable notification
content is added to the parent context separately.

### `list_agents`

List the current root tree with canonical task path, latest status, effective
model, current turn, terminal summary/error, and timestamps.

### `interrupt_agent`

Interrupt the target's active turn through the existing interrupt service and
return its previous status. The child session remains reusable.

## Context And Memory Model

Child and parent transcripts remain independent.

- `fork_turns="none"` starts from stable instructions, workspace context, and
  the new task only.
- `fork_turns="all"` copies the parent's filtered model context.
- Numeric `fork_turns` copies the last N user turns and their final assistant
  answers.

Forked context excludes reasoning, historical tool calls/results, approvals,
steers, and intermediate streaming fragments. It retains system/developer
instructions, user messages, final assistant answers, temporal context, and
necessary workspace references.

Agent lineage and task identity belong in durable session metadata/lineage, not
memory. Inter-agent communication belongs in transcript/messages and events,
not memory.

## Model Selection And Availability

If `model` is omitted, the child uses the parent turn's effective resolved
model.

If `model` is provided:

1. Resolve it against the caller-visible active catalog.
2. Require provider/model enablement and tool support.
3. Resolve the credential without exposing secret material.
4. Reuse a fresh successful probe only when its provider, endpoint,
   credential, and model fingerprint still match.
5. Otherwise run the existing minimal `LlmProviderProbe` request.

If the requested model is unavailable, spawning continues with the parent
turn's effective model. The fallback is explicit in the tool result and audit
events. The child must never silently switch models, and probe errors must not
leak credentials or raw provider responses.

## Delegation And Orchestration Model

The root owns a shallow fork-join tree. Child sessions carry:

- parent session and parent turn IDs;
- root session ID;
- task name and canonical task path;
- collaboration depth of one;
- inherited workspace and execution boundaries;
- requested/effective model metadata.

Children cannot see any collaboration tools. This is enforced by tool exposure,
not prompt text.

No new orchestration table is introduced. Agent sessions and turns remain the
source of truth. Repository queries provide live-tree listing, sibling-name
checks, concurrency counting, and mailbox cursors. A small schema/index change
is acceptable only where metadata queries cannot enforce these invariants
reliably across SQLite and PostgreSQL.

## Extension Model

The six tools live in a focused collaboration subpackage and implement the
existing `AgentTool` protocol. A collaboration service owns shared validation,
target resolution, status projection, context forking, model preflight, and
mailbox behavior so individual tool handlers remain small.

The ordinary tool registry and exposure layer stay unchanged except for:

- registering the six collaboration tools;
- exposing them in root execution sessions;
- excluding them for child sessions;
- removing `task` and `subagent.analyze` completely.

## Safety And Observability

- Enforce root ownership on every target lookup.
- Enforce workspace/user boundaries on every operation.
- Enforce the eight-slot budget before session creation.
- Validate canonical task names and reject live sibling collisions.
- Child sessions inherit cwd, workspace roots, execution target/scope,
  permission mode, automation mode, and prompt snapshot.
- Inherited permissions do not bypass approval or destructive-action checks.
- Store structured requested/effective model and fallback events.
- Store structured spawn, message, follow-up, wait, interrupt, completion, and
  failure events.
- Every terminal notification includes status, final text, error code, safe
  error message, termination reason, token usage, and model.
- Never return `failed` with an empty explanation when an error is persisted.

## API And UI

The first implementation keeps collaboration model-driven and reuses the
generic tool-call UI. Public event projection must retain safe lifecycle and
terminal notifications so users can understand what each child is doing.

The UI should display, at minimum:

- task name/path;
- queued/running/completed/failed/interrupted status;
- requested/effective model and fallback marker;
- final summary or error message;
- tool progress when already available through safe public events.

All new copy must be present in English and Chinese locale files.

## Migration

- Delete the synchronous `TaskTool` implementation and tests.
- Delete `SubagentAnalyzeTool` and the legacy `ReadOnlySubagentRunner`.
- Remove `task` and `subagent.analyze` from registration and exposure.
- Add the six Codex-style tools and focused tests.
- Update prompts, tool documentation, API schemas, public events, frontend
  rendering, and locale strings as required.
- Do not retain a model-visible compatibility alias.

## Verification Strategy

Use TDD for each behavior. Required regression coverage includes:

- spawn returns before child completion;
- total concurrency budget of eight including root;
- duplicate live sibling task names are rejected;
- child cannot access collaboration tools;
- requested model succeeds after a real/fresh probe;
- unavailable requested model falls back to the parent model;
- parent model selection fixes the observed authentication regression;
- each failure returns structured error details;
- `send_message` does not start an idle turn;
- `followup_task` starts an idle turn and queues safely while running;
- wait wakes on child updates, parent steer, and timeout;
- interrupt leaves the child reusable;
- list is root-scoped and exposes safe status/model data;
- fork modes copy only allowed context;
- startup recovery preserves child turns and notifications;
- public events and frontend output never collapse failures to empty text.

Backend completion checks:

- focused Agent Core tests during iteration;
- full `uv run pytest`;
- `uv run ruff check .`;
- Alembic migration checks if schema changes.

Frontend completion checks when frontend files change:

- `bun run lint`;
- `bun run lint:i18n`;
- `bun run test`;
- `bun run lint:dead-code` for dead-code-sensitive migration cleanup.

Repository completion check:

- `git diff --check`.
