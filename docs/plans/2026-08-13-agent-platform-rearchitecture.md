# Agent Platform 可替换架构重构计划

> **Superseded / 已废弃：** 本讨论稿已由
> [BioinfoFlow 完整 Agent Harness 重构计划](2026-08-13-complete-agent-harness-rearchitecture.md)
> 取代，不得作为实施依据。

## Status

Discussion draft proposed on 2026-08-13. This is a clean-break redesign:
existing Agent data, internal event shapes, backend implementation modules, and
the legacy demo renderer are not compatibility constraints. The Host/Engine
contract remains subject to design discussion; no implementation should begin
until the contract and terminology are accepted.

## Outcome

Replace the current tightly coupled Agent Core with a **Durable Agent Host**
containing three deep responsibility modules plus replaceable Engine Adapters:

1. **Turn Lifecycle** owns whether a Turn may run, who may publish, suspension,
   resume, cancellation, recovery, and terminalization.
2. **Action Runtime** owns Tool Calls, capability exposure, Tool Actions,
   authorization, approval, effect claims, settlement, audit, and artifacts.
3. **Conversation Projection** owns canonical conversation state and the stable
   client-facing snapshot/progress protocol.
4. **Agent Engine Adapters** own harness-specific reasoning, provider streaming,
   model-loop policy, native continuation, and native-event normalization.

The Capability Registry, Exposure Policy, and Executor remain separate
interfaces inside Action Runtime because they change for different reasons.
They are not a second product orchestrator beside the Host.

The replacement is complete only when a native engine and at least one real
external harness adapter pass the same conformance suite without changing Turn
Lifecycle, Action Runtime, Conversation Projection, HTTP/SSE transport, or
frontend types. Pydantic AI is the current recommended first external adapter;
Pi remains a useful later sidecar candidate, not an architectural dependency.

The bilingual working vocabulary is maintained in
`docs/reference/agent-platform-terminology.md`.

## Review of the Terra proposal

The external review adds several changes that should be adopted:

- make Turn Lifecycle and Action Runtime separate deep Host modules;
- persist Tool Call separately from Tool Action;
- model Decision Request and immutable Decision separately, with Approval as a
  Decision kind unless future multi-party requirements justify more;
- treat opaque Engine Checkpoint as a same-engine optimization only;
- use `snapshot_seq`, a retained-event floor, and explicit `reset_required`;
- do not make Pi the mandatory proof adapter;
- explicitly model uncertain external effects as reconciliation required.

One recommendation is adopted with a qualification: engines need an eventful,
bidirectional semantic interaction, but a wide long-lived callback object should
not be the only stable external SPI. The durable outer contract remains
**run until the next Host-owned barrier**, because it works across an in-process
adapter, sidecar, remote worker, crash, and approval lasting hours or days.

An adapter may use a callback-shaped bridge internally for a harness such as
Pydantic AI. The bridge must translate callback requests into the same typed
Tool Round or Decision barrier and must not expose database identity, leases,
ledger allocation, approval records, or product DTOs. This preserves harness
ergonomics without making process lifetime a durability requirement.

## Replaceability promise

“Pluggable” has four distinct levels:

| Level | Promise | V2 position |
| --- | --- | --- |
| R1 Next-Turn Replaceable | A compatible engine can handle the next Turn from Canonical Conversation. | Required |
| R2 Barrier Replaceable | A compatible engine can continue the same Turn after a durable Tool/Decision barrier. | Required |
| R3 Same-Engine Resumable | The same engine/version can resume faster from an opaque checkpoint. | Optional optimization |
| R4 Live Cross-Engine Migratable | An in-flight model stream can move to a different engine without returning to a barrier. | Explicitly deferred |

Therefore the platform and harness become cleanly decoupled at durable
boundaries, not magically interchangeable at every machine instruction. An
arbitrary harness is replaceable after an Engine Adapter maps its semantics to
the versioned contract and passes conformance; no framework is “drop-in” merely
because it can call an LLM and tools.

## How a harness is installed, upgraded, and replaced

Each adapter registers an immutable `EngineDescriptor`:

```python
EngineDescriptor(
    engine_id="pydantic-ai",
    engine_version="1.4.2",
    contract_version="agent-engine/v1",
    checkpoint_schema_version="3",
    transport="in_process" | "stdio" | "rpc" | "durable_worker",
    supported_features={
        "tool_rounds",
        "decision_requests",
        "streaming_progress",
        "checkpoints",
    },
)
```

The Host selects an adapter from an explicit registry. Registration does not
make it the default, and selecting an engine does not expand tool exposure or
authorization.

Use this replacement workflow:

1. **Implement the adapter** against a published Engine Contract version. Keep
   all harness-native messages, events, IDs, and tool APIs inside the adapter.
2. **Pass conformance** with the same canonical traces as Native Engine,
   including no-checkpoint recovery, approvals, cancellation, duplicate
   delivery, crash windows, and malformed native output.
3. **Install side by side** with the current adapter. Never replace the old
   binary or registration in place while it still has active Engine Runs.
4. **Canary new Turns** by workspace, conversation, or explicit user choice.
   Pin every Engine Run to exact engine and contract versions for audit and
   deterministic recovery.
5. **Switch at a durable boundary.** New Turns may select the new adapter. An
   existing Turn may switch only when no model stream or Effect is in flight and
   Canonical Conversation contains every committed result through the boundary.
6. **Handle checkpoints conservatively.** Reuse a checkpoint only when engine
   ID, compatible engine version, checkpoint schema, and affinity match.
   Otherwise discard it and rebuild from Canonical Conversation. Cross-engine
   checkpoint conversion requires an explicit, separately tested migrator and
   is never assumed.
7. **Roll back by selection, not data surgery.** Stop assigning new Engine Runs
   to the new adapter and select the previous compatible adapter at the next
   boundary. Canonical Conversation, Host state, HTTP/SSE, and frontend types do
   not roll back.
8. **Retire only after reachability is zero.** Remove the old adapter after no
   active Engine Run or required checkpoint still depends on it and retained
   audit records remain readable without its code.

Harness upgrades that preserve the current contract require only a new adapter
version and conformance run. A harness feature that cannot be represented by
the contract has three acceptable outcomes: keep it adapter-private as an
optimization, project it into an existing semantic type, or propose a new
versioned contract capability. It must not leak a new native event or persistence
field directly to the frontend.

Model access follows the same rule. The Host issues a `ModelGrant` containing
authorized target, credential handle, quota/budget, audit/billing identity, and
fallback constraints. A Native adapter may consume it through a Host ModelPort;
another adapter may use its own provider stack through a scoped credential
broker. The contract governs authority and accounting, not one mandatory model
SDK abstraction.

## First-principles decision

The smallest stable invariant is:

> BioinfoFlow owns durable product facts and side effects. A harness owns how
> to reason until the next durable barrier.

From that invariant:

- A harness must not receive an SQLAlchemy session, repository, ORM model,
  FastAPI request, lease token, durable event sequence, approval record, or
  frontend DTO.
- Tool calls are durable barriers. The engine requests actions; the platform
  persists, authorizes, approves, executes, and audits them; the engine later
  receives normalized results.
- The canonical conversation is sufficient to restart an engine. An opaque
  harness checkpoint or provider continuation may accelerate recovery, but it
  cannot be the only semantic state.
- Native harness events never cross the Agent Engine seam and never reach the
  frontend.
- The frontend receives authoritative conversation items, not an event puzzle
  from which it must infer product state.

## Source-confirmed current problems

These are confirmed by the current checkout, not architectural speculation.

### Harness and durability have no real seam

- `AgentLoopController` constructs repositories, ledger, context assembler,
  transcript store, default tool registry, tool executor, and batch coordinator
  inside its implementation.
- Its apparent `run_turn(...)` interface hides SQL state, owner tokens, action
  resume rules, event publication, and provider continuation ordering.
- `AgentCoreRuntime` constructs `AgentLoopController` directly, and the runner
  hard-codes `AgentCoreRuntime`.
- Tests instantiate the SQL-backed controller and call implementation details,
  so the current implementation, rather than a stable interface, is the test
  surface.

Primary files:

- `backend/app/services/agent_core/core/loop.py`
- `backend/app/services/agent_core/runtime.py`
- `backend/app/services/agent_core/runner.py`
- `backend/tests/test_agent_core/test_model_runtime_integration.py`
- `backend/tests/test_agent_core/test_tool_call_batches.py`

### The tool interface leaks platform implementation

`AgentToolContext` currently includes `AsyncSession`, workspace/user/session/
Turn database identifiers, ownership guards, expected owner tokens, and a raw
permission snapshot. A third-party harness or tool implementation therefore
has to understand the current Host durability implementation.

Primary files:

- `backend/app/services/agent_core/tools/specs.py`
- `backend/app/services/agent_core/tools/executor.py`

### The public event seam is reversed in the frontend

The backend already projects many durable event types into a smaller public
event family, but `frontend/lib/agent-runtime/public-events.ts` converts the
public events back into native durable event names. The renderer therefore
still depends on the native event taxonomy.

Primary files:

- `backend/app/services/agent_core/events.py`
- `backend/app/api/v1/agent.py`
- `frontend/lib/agent-runtime/public-events.ts`

### The frontend is a second domain interpreter

The formal `/agent` frontend performs legitimate stream reconciliation, but it
also:

- correlates tool calls, actions, and artifacts across low-level events;
- infers action terminal status from Turn terminal status;
- guesses `search/read/write/run/verify` from tool names, arguments, and shell
  command regular expressions;
- exposes native persistence snapshots such as `loop_state`,
  `compression_state`, and `budget_snapshot` in client types.

Primary files:

- `frontend/lib/agent-runtime/segments.ts`
- `frontend/lib/agent-runtime/tool-activity.ts`
- `frontend/lib/agent-runtime/activity-groups.ts`
- `frontend/lib/agent-runtime/types.ts`
- `frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx`

### The demo is a separate renderer

`/demo` consumes `AgentCoreEvent` through `AgentCoreTurnBlock`, while `/agent`
uses the formal runtime renderer. The demo is not a compatibility constraint;
it must consume the new Conversation Feed or be deleted.

## Open-source evidence that constrains the design

The detailed primary-source review is in
`docs/research/2026-08-13-agent-harness-architecture-research.md`.

- **Pi**: the useful seam is its session/runtime and snapshot/progress protocol,
  not the currently incomplete durable harness implementation. Snapshot is
  authoritative; progress is transient. Pi does not provide BioinfoFlow's
  permission platform.
- **Hermes Agent**: its foreign Codex runtime adapter and event projector prove
  that a different harness can feed an existing product transcript. Its tool
  registry/exposure split is useful. Its wide `AIAgent`, callback fan, hard-coded
  runtime branching, and process-memory approval state should not be copied.
- **LangGraph**: checkpoint storage, explicit durability policy,
  interrupt/resume semantics, tool lifecycle events, and ordered event
  envelopes are useful references. Pregel vocabulary and its broad interface
  should not become BioinfoFlow's public model.
- **Pydantic AI**: deferred tools demonstrate action/approval barriers and new
  run resumption; UI adapters demonstrate that native events and frontend
  protocols should be separate. Client-supplied history is not sufficient for
  authorization.

## Target module map

```text
HTTP / worker / scheduler
          |
          v
+------------------ Durable Agent Host -------------------+
| Turn Lifecycle                                            |
| claim / lease / fence / steer / cancel / suspend /       |
| resume / recover / terminalize                            |
|                                                          |
| Action Runtime                                            |
| registry / exposure / Tool Call / policy / Decision /    |
| effect claim / settlement / audit / Artifact             |
|                                                          |
| Conversation Projection                                   |
| Canonical Conversation -> snapshot_seq + typed progress   |
+----------------------+-----------------------------------+
                       | versioned Agent Engine contract
                       v
              +---------------------------+
              | Agent Engine Adapters     |
              | Native / Pydantic AI /    |
              | Pi sidecar / Scripted     |
              +-------------+-------------+
                            |
                            | normalized progress,
                            | barriers, checkpoints,
                            | outcomes
                            v
                 Host persists and projects facts
                       |
                       v
              HTTP snapshot + ordered SSE
                         |
                         v
                 frontend feed store
                         |
                         v
                 transcript renderer
```

## Recommended Agent Engine interface

Use one stable outer entry point: run the harness to the next durable barrier.
This is a versioned semantic SPI, not a Python-only calling convention; the same
messages may cross an in-process call, framed stdio, RPC, or a durable worker
transport.

```python
class AgentEngine(Protocol):
    descriptor: EngineDescriptor

    async def run_until_barrier(
        self,
        request: EngineStart,
        host: EngineHost,
    ) -> EngineOutcome:
        ...
```

```python
@dataclass(frozen=True)
class EngineStart:
    engine_run_id: str
    conversation: tuple[ConversationItem, ...]
    incoming: tuple[ConversationItem, ...]
    tools: tuple[CapabilityDefinition, ...]
    model_grant: ModelGrant
    limits: EngineLimits
    resolved_tool_rounds: tuple[ToolRoundResult, ...] = ()
    resolved_decisions: tuple[DecisionResult, ...] = ()
    checkpoint: EngineCheckpoint | None = None
    resume_material: EngineResumeMaterial | None = None


class EngineHost(Protocol):
    async def publish_progress(self, event: EngineProgress) -> None:
        ...

    async def next_control_signal(self) -> EngineControlSignal | None:
        ...

    async def save_checkpoint(self, checkpoint: EngineCheckpoint) -> None:
        ...


EngineOutcome = (
    Completed
    | ToolRoundRequested
    | DecisionRequested
    | Suspended
    | Cancelled
    | Failed
)
```

`ToolRoundRequested` returns one complete tool round:

```python
@dataclass(frozen=True)
class ToolRoundRequested:
    append: tuple[ConversationItem, ...]
    calls: tuple[ToolCallIntent, ...]
    checkpoint: EngineCheckpoint | None = None
```

The platform then performs:

```text
run_until_barrier
  -> ToolRoundRequested
  -> persist canonical Tool Calls and tool round
  -> permission and approval
  -> execute, reject, or suspend Tool Actions
  -> persist normalized ToolRoundResult values
  -> run_until_barrier again
```

### Why this interface is preferred

It does not expose persistence, approval records, ledger allocation, or effect
execution as engine callbacks. A convenience callback bridge may offer
`resolve_tool_round()` and `request_decision()` to a concrete harness, but that
bridge translates to these durable outcomes and is not the canonical SPI.

It also avoids making a long-lived actor protocol the permanent external
interface. A Pi or Hermes adapter may internally use an actor, sidecar,
callbacks, steering queues, or native checkpoints, but it must present the same
durable-barrier interface to BioinfoFlow.

### Engine invariants

1. Canonical conversation is the semantic source of truth.
2. Every production adapter must recover with `checkpoint=None` by rebuilding
   from canonical conversation.
3. One `engine_run_id` cannot execute concurrently, and duplicate delivery is
   resolved idempotently.
4. `EngineHost.publish_progress()` is awaited; emissions are ordered within an
   Engine Run.
5. The platform assigns durable `seq`; engine events do not contain ledger
   sequence numbers.
6. Outcome return is terminal for the operation; no later emissions are valid.
7. Every `ToolCallIntent.correlation_key` is unique in its round and has a matching
   canonical assistant tool-request part.
8. The next `resolved_tool_rounds` entry matches the prior barrier one-for-one.
9. Denied approval is a normal Tool Result, not an engine exception.
10. Engine Checkpoint carries adapter/version/schema/affinity metadata and is never
    exposed through the public frontend interface.
11. Cancellation is Host-authoritative; an engine outcome cannot terminalize a
    Turn while a claimed Effect remains unresolved.
12. Every adapter must support restart with `checkpoint=None` from Canonical
    Conversation at the supported replaceability boundary.

### Steering and follow-up

Do not add a wide bidirectional harness interface initially.

- `steer` is persisted by Turn Lifecycle as new incoming canonical input.
- The current Engine Run observes cancellation at a safe point.
- The next `run_until_barrier()` receives the steer in `incoming`.
- `follow_up` creates the next Turn after the current Turn reaches a terminal
  state.

An adapter may support faster in-flight steering through an internal seam, but
that optimization is not part of the first stable Agent Engine interface. It
must not change canonical ordering or recovery behavior.

## Action Runtime capability interfaces

Create three distinct interfaces.

### Registry

Owns capability identity and static metadata:

```python
CapabilityDefinition(
    name,
    description,
    input_schema,
    output_schema,
    risk_profile,
    execution_traits,
    display,
)
```

`display` is declared by the capability, not inferred by the frontend:

```python
CapabilityDisplay(
    kind="search" | "read" | "write" | "run" | "verify" |
         "command" | "workspace" | "other",
    label_key="agent.activity.search",
    input_summary_fields=("query",),
    related_resource_fields=("path", "workflow_id"),
)
```

### Exposure policy

Resolves the immutable capability catalog offered to one engine operation from:

- role;
- mode;
- execution target and scope;
- installed skills/plugins;
- platform policy;
- capability availability.

Registration never implies exposure, and exposure never implies authorization.

### Executor

Owns the complete side-effect pipeline:

1. validate and normalize arguments;
2. re-resolve fresh permission context;
3. assess risk and affected resources;
4. persist the Tool Call, Tool Action, and audit facts;
5. suspend for approval when required;
6. execute through the appropriate local/remote adapter;
7. normalize model-facing content and product-facing details separately;
8. record artifacts and terminal status;
9. return a normalized Tool Result.

The new tool implementation context contains scoped product ports, not an
`AsyncSession` or owner token.

## New canonical data model

Use a destructive Agent schema migration. Do not translate old Agent data.

### `agent_conversations`

- identity, workspace/user/project scope;
- title and archived state;
- selected engine and user-facing mode;
- public policy summary;
- canonical revision and timestamps.

### `agent_turns`

- conversation identity;
- normalized user input reference;
- state: queued/running/waiting/completed/failed/cancelled;
- current Engine Run identity;
- model intent and user-visible usage summary;
- terminal outcome/error;
- timestamps.

Do not store native `loop_state`, provider messages, or frontend projection
fields on the Turn.

### `agent_engine_runs`

One call to `AgentEngine.run_until_barrier()`:

- Turn and engine identity/version;
- input conversation revision;
- status and idempotency key;
- execution claim generation, lease expiry, and heartbeat;
- opaque Engine Checkpoint;
- replay-safety and failure metadata;
- start/finish timestamps.

Execution Claim and Lease belong here, not in the Engine interface.

### `agent_conversation_items`

The canonical transcript as a closed union:

- user message;
- assistant message;
- assistant tool request;
- tool result;
- system/context note when semantically required.

Each item has a stable ID, Turn ID, ordering key, status, typed payload, and
optional internal annotations. Provider-specific fields are forbidden outside
opaque adapter annotations.

### `agent_tool_rounds`

- Engine Run and Turn identity;
- round ordinal;
- status and completion rule;
- optional Engine Checkpoint reference;
- timestamps.

Keep the Tool Round because “the model continues only after every Tool Call has
one resolved result” is a real invariant.

### `agent_tool_calls`

- stable platform Tool Call ID;
- engine-local correlation key as mapping metadata;
- Engine Run, Turn, and Tool Round identity;
- capability name and normalized arguments;
- finalized canonical status and ordering;
- optional namespaced engine/provider annotations.

Persisting a Tool Call records finalized intent before any Effect is eligible.

### `agent_actions`

- platform action ID;
- Tool Call identity and attempt ordinal;
- display metadata copied from the capability definition;
- permission/risk snapshots;
- effect intent, claim, idempotency/replay policy, settlement, result/error;
- timestamps.

The frontend sees a stable Activity ID equal to the platform Tool Call ID. The
projection summarizes the latest or relevant Tool Action attempt without
turning an attempt ID into public identity. Engine correlation keys remain
internal.

### `agent_decision_requests`

- durable subject, kind, prompt, allowed response schema, and redacted context;
- Turn identity and optional Tool Call/Action identity;
- request version, requester, authorized decider scope, status, and expiry;
- suspension and resume metadata.

### `agent_decisions`

- immutable resolution linked to one Decision Request version;
- decider identity, response, rationale, and timestamp;
- idempotency key and stale-resolution protection.

Approval is represented as `DecisionRequest(kind="approval")` plus its Decision
unless delegated approvers, multi-party quorum, or approval delegation later
justify an additional aggregate.

### `agent_action_audit_entries`

- append-only structured policy, effect, settlement, reconciliation, and
  administrative evidence;
- correlation to Turn, Tool Call, Tool Action, Decision, and actor;
- redaction/version metadata.

### `agent_events`

Retain an internal durable event ledger for audit, worker wakeup, and recovery.
It is not the frontend protocol and not the canonical transcript.

### `agent_feed_items`

Persist the authoritative public read model so the frontend does not reconstruct
terminal product state from low-level events. The projector updates feed items
in the same transaction as the durable fact whenever possible.

## Conversation Feed protocol

### Snapshot

`GET /agent/conversations/{id}` returns:

```typescript
type ConversationSnapshot = {
  conversation: ConversationSummary
  turns: TurnSummary[]
  items: ConversationFeedItem[]
  pendingDecisions: DecisionItem[]
  snapshotSeq: number
  minAvailableSeq: number
  revision: number
}
```

### Closed feed item union

```typescript
type ConversationFeedItem =
  | UserMessageItem
  | AssistantMessageItem
  | ThinkingSummaryItem
  | ActivityItem
  | DecisionItem
  | NoticeItem
  | TurnErrorItem
```

`ActivityItem` contains explicit semantics:

```typescript
type ActivityItem = {
  kind: "activity"
  id: string                 // platform tool_call_id
  turnId: string
  displayKind: "search" | "read" | "write" | "run" |
               "verify" | "command" | "workspace" | "other"
  name: string
  status: "requested" | "waiting" | "running" | "completed" |
          "failed" | "rejected" | "cancelled"
  inputSummary?: string
  outputSummary?: string
  errorMessage?: string
  relatedResources: ResourceRef[]
  artifactIds: string[]
}
```

### SSE envelope

```typescript
type FeedEvent = {
  seq: number
  type: "feed.item.upsert" | "feed.item.delta" |
        "turn.updated" | "conversation.updated"
  entityId: string
  revision: number
  payload: unknown
  occurredAt: string
}
```

Rules:

- Snapshot is authoritative; progress events are incremental delivery.
- A snapshot represents state through exactly `snapshot_seq`; progress begins
  strictly after it.
- `seq` is the total order and replay cursor used for reconnect. Event UUID and
  wall-clock time are not cursors.
- If `after_seq < min_available_seq`, return
  `reset_required(snapshot_url, min_available_seq)` rather than incomplete
  replay.
- `feed.item.delta` may update only declared streaming fields.
- A cumulative `feed.item.upsert` supersedes all prior deltas for that item.
- Terminal status is emitted by the backend; the frontend never infers it from
  a parent Turn.
- Unknown union variants fail visibly in development and are ignored with a
  diagnostic notice in production; arbitrary string event types are forbidden.
- HTTP snapshot and SSE use the same public types. There is no frontend reverse
  mapping to internal event names.

## Frontend target

Create `frontend/lib/agent-feed/` with one deep client module:

- fetch snapshot;
- connect/reconnect SSE with `after_seq`;
- deduplicate and order events;
- apply item delta/upsert operations;
- expose immutable `ConversationViewState`.

React receives feed items and renders them. It does not correlate tool calls to
actions, parse action results, infer terminal states, inspect persistence
snapshots, or classify shell commands.

Retain the useful renderer split in `agent-transcript.tsx`, but replace its
input with the closed feed union. Split `AgentWorkbench` by independent change
axes after the feed migration:

- conversation controller;
- composer and attachments;
- transcript;
- decisions/permissions;
- workspace/artifacts;
- secondary panels.

The split is not a directory-cleanup exercise. Each new module must have a
small interface and own a coherent behavior cluster.

## Extension model

Do not create one universal plugin interface.

Use separate seams for:

- Agent Engine adapters;
- model provider adapters;
- capability providers;
- exposure/policy middleware;
- execution middleware;
- observers/telemetry;
- context sources;
- optional feed item projectors/renderers.

Rules:

- each extension category has its own typed interface and failure policy;
- observers fail open, authorization fails closed;
- overrides require explicit configuration;
- plugins receive scoped ports, never the global runtime or ORM session;
- extension payloads are namespaced and versioned;
- extension payloads cannot change Turn, Action, approval, or audit state unless
  promoted into a formal platform contract.

## Runtime modes

The same Durable Agent Host powers:

- HTTP/API turns;
- background workers;
- local CLI or future desktop transports;
- collaboration child Turns.

Only transport adapters vary. Runtime state that survives a process restart is
stored in the canonical tables and event ledger. Engine objects, callbacks,
provider streams, and sidecar processes are disposable.

## Migration campaign

This is one architectural campaign on a dedicated branch. Do not ship partial
compatibility architecture as a permanent state.

### Phase 0: Freeze the replacement contract

Create:

- `backend/app/services/agent_platform/contracts/engine.py`
- `backend/app/services/agent_platform/contracts/conversation.py`
- `backend/app/services/agent_platform/contracts/capabilities.py`
- `backend/app/services/agent_platform/contracts/feed.py`
- focused contract tests and JSON fixtures shared with the frontend.

Deliverables:

- the `run_until_barrier()` interface and invariants;
- closed canonical conversation union;
- closed feed item/event union;
- engine error taxonomy;
- engine conformance suite using a scripted adapter;
- a decision record that the old Agent database and event protocol are not
  compatible.

Gate: no runtime implementation work starts until the contracts can express
plain chat, streaming, multiple tools, approval rejection, restart after an
action barrier, cancellation, and terminal failure.

### Phase 1: Reset the Agent schema

- Add one destructive Alembic migration that drops current Agent tables and
  recreates the new schema.
- Do not write data converters, dual readers, or fallback queries.
- Create repositories only for the new canonical entities.
- Enforce foreign keys and idempotency constraints in SQLite tests.

Gate: repository tests prove Engine Run leasing, ordered items, Tool Round
resolution, Decision idempotency, and event/feed sequence monotonicity.

### Phase 2: Build Turn Lifecycle and Action Runtime with a scripted engine

Create the runtime around `ScriptedEngineAdapter` before connecting a model.

Scenarios:

- text streaming to completion;
- multiple action intents in one barrier;
- mixed allow/deny/approval outcomes;
- worker crash before and after an external effect;
- lease loss;
- cancellation;
- replay with duplicate Engine Run/progress IDs;
- recovery without Engine Checkpoint.

Gate: all platform behavior is testable without a provider or native loop.

### Phase 3: Complete Action Runtime capability interfaces

- Preserve useful capability implementations, but replace their external
  context with scoped product ports.
- Move registration metadata, exposure policy, and execution into separate
  modules.
- Put display semantics in capability definitions.
- Keep remote execution, sandbox, path policy, permission, approval, artifact,
  and audit behavior behind the executor interface.
- Delete frontend-derived activity classification as soon as the feed exposes
  `displayKind`.

Gate: capability tests run through Action Runtime interfaces and do not
construct `AgentToolContext` with an `AsyncSession`.

### Phase 4: Implement the new Native Engine adapter

Rebuild the native engine from the existing protocol-neutral model runtime and
canonical conversation types. Do not wrap `AgentLoopController` as the final
implementation.

The adapter owns:

- context assembly and prompt snapshot selection;
- provider request shaping through `ModelGateway`;
- streaming normalization;
- model retry/fallback policy;
- no-progress and iteration budgets;
- extraction of action intents;
- opaque provider continuation.

The adapter does not own:

- repositories or transaction commit;
- Turn lease or recovery;
- capability permission/approval/execution;
- audit or artifact ownership;
- durable sequence allocation;
- frontend projection.

Gate: Native Engine passes the shared conformance suite and end-to-end Durable
Agent Host scenarios.

### Phase 5: Replace the backend transport

- Route session/Turn creation, decision, cancel, steer, state, and stream
  endpoints through the new Durable Agent Host.
- Rename public HTTP resources to conversation/Turn terms where useful; no old
  endpoint compatibility adapter is required.
- Replace `event_view=full|public` with one public feed endpoint and separate
  internal diagnostics endpoints guarded for development/admin use.
- Export and review the OpenAPI contract.

Gate: API tests cover snapshot + SSE replay, approval resume, cancel, steer,
and recovery using only the new runtime.

### Phase 6: Rebuild the formal frontend on Conversation Feed

- Add generated or shared TypeScript feed types.
- Implement the `agent-feed` store.
- Migrate transcript, activity, decision, error, source, and artifact rendering
  to feed items.
- Delete `public-events.ts`, native event reverse mapping, tool/action correlation,
  tool-name/command classification, and terminal-state inference.
- Remove persistence implementation fields from client types.
- Migrate `/demo` to the same feed fixtures or delete the old demo renderer.

Gate: reconnect, duplicate delivery, delta/upsert, action lifecycle, approval,
failure, and demo tests all use the same feed contract.

### Phase 7: Prove the seam with a real external harness

Implement a Pydantic AI adapter as the first external proof because its Python
agent API already supports history, deferred tool results, cancellation, usage,
tools, and event handling.

- Wrap its Toolset with a governed adapter that yields Tool Calls to Action
  Runtime; do not let Pydantic AI directly own product tool execution.
- Do not enable a second durability authority beneath the Host.
- Native events and message objects remain inside the adapter.
- Deferred tools, cancellation, unreadable checkpoints, duplicate/late
  progress, and restart without checkpoint are conformance cases.

After that proof, a Pi Node sidecar remains a valuable transport and
cross-language test. JSON-RPC or framed JSON over stdio is an internal adapter
transport, not part of the public product contract.

Gate: Native and at least one external adapter pass the same chat, multi-tool,
approval, rejection, cancellation, crash recovery, and no-checkpoint recovery
suite.
Until this gate passes, the harness seam is a design hypothesis rather than a
proven seam.

### Phase 8: Delete the old architecture

Delete, rather than deprecate:

- `backend/app/services/agent_core/core/loop.py`;
- the old `AgentCoreRuntime`, old runner wiring, and old facade methods;
- old action/tool batch coordination implementation replaced by the new runtime;
- old ORM models, repositories, schemas, events, and compatibility helpers;
- tests that assert old implementation details or call private controller
  methods;
- `frontend/lib/agent-runtime/` modules superseded by `agent-feed`;
- legacy `/demo` `AgentCoreTurnBlock` and old `frontend/lib/agent-core` paths
  once reachability is zero.

Run dead-code and reachability searches before deletion, then require the old
package names to have zero production imports.

### Phase 9: Split remaining oversized UI modules

Only after the feed seam is stable:

- split `AgentWorkbench` by behavior clusters;
- split the runtime hook into feed connection, mutation commands, composer
  state, and workspace panels;
- keep orchestration in a small page-level controller;
- test each module through its public props/hook interface.

This phase must not reintroduce native event or persistence knowledge into UI
modules.

## Test strategy

### Engine conformance suite

Every engine adapter must pass:

- text-only completion;
- commentary and answer ordering;
- one and multiple action intents;
- malformed tool arguments;
- rejected and failed action results;
- approval suspension and restart;
- cancellation during model wait;
- duplicate Engine Run delivery idempotency;
- crash before outcome;
- recovery with and without Engine Checkpoint;
- terminal outcome followed by illegal emission;
- retryable versus replay-safe failure.

### Durable Agent Host tests

- lease acquisition, renewal, loss, and reclaim;
- exactly one active Engine Run per Turn;
- Tool Round resolution before engine continuation;
- approval decision idempotency and stale-decision rejection;
- external-effect intent/settlement uncertainty windows;
- canonical item ordering and revision checks;
- internal event and feed sequence monotonicity;
- projector transaction failure behavior;
- recovery never repeats a settled side effect.

### Action Runtime capability tests

- registered but unexposed capability;
- exposed but unauthorized capability;
- fresh permission re-resolution at execution;
- hard approval floor;
- output size limits and structured errors;
- remote target and scope enforcement;
- parallel execution only for declared independent capabilities;
- model-facing content separated from product-facing detail.

### Frontend tests

- authoritative snapshot load;
- SSE `after_seq` reconnect and duplicate suppression;
- delta followed by cumulative upsert;
- explicit activity display kind;
- approval and user-input decisions;
- terminal action and Turn states without inference;
- unknown protocol variant diagnostics;
- `/agent` and `/demo` consuming the same fixtures.

## Verification commands by phase

Backend phases:

```bash
rtk uv run pytest tests/test_agent_platform -q
rtk uv run pytest tests/test_api/test_agent_platform_api.py -q
rtk uv run ruff check .
rtk uv run pytest
```

Schema phases:

```bash
rtk uv run alembic upgrade head
rtk uv run pytest tests/test_agent_platform/test_repositories.py -q
```

Frontend phases:

```bash
rtk bun run test tests/unit/lib/agent-feed
rtk bun run test tests/unit/components/agent-transcript.test.tsx
rtk bun run lint
rtk bun run lint:i18n
rtk bun run lint:dead-code
rtk bun run test
rtk bun run build
```

Contract phases:

```bash
rtk uv run python scripts/export_openapi_contract.py --check ../docs/contracts/openapi-v1.json
rtk git diff --check
```

## Non-goals for the first replacement

- preserving old Agent rows or replaying old event history;
- preserving old HTTP event names or frontend DTOs;
- exposing every Pydantic AI/Pi/Hermes feature through the first Engine
  interface;
- general-purpose graph execution semantics;
- one universal plugin framework;
- cross-engine migration of an in-flight opaque checkpoint;
- provider-native UI payloads;
- rewriting unrelated workflow scheduler/runtime modules.

## Decisions to keep explicit

The following are architecture decisions, not source-confirmed facts:

1. `AgentEngine.run_until_barrier()` is the stable outer SPI; callback-shaped
   bridges are adapter conveniences.
2. Tool execution is a returned durable barrier, not an Engine port.
3. Canonical Conversation restart without Engine Checkpoint is mandatory for
   every production adapter at its supported replacement boundary.
4. The frontend consumes persisted feed items plus ordered progress, not raw
   durable events.
5. Public Activity identity is the platform `tool_call_id`; the engine
   correlation key and Tool Action attempt IDs are internal.
6. The current Agent schema is destructively replaced.
7. The seam is proven by conformance from one real external adapter; Pydantic AI
   is the recommended first candidate, while Pi is not required.

## Product decisions still open

These questions do not change the Host/Engine separation, but they do change
state machines, retention, and product policy. Resolve them before freezing the
V2 contracts:

1. Which capabilities may automatically retry an uncertain Effect through a
   verified idempotency key, and which always enter `reconciliation_required`?
2. Are arbitrary user questions first-class Decision Requests, or only
   platform-governed interaction capabilities such as approval and plan
   confirmation?
3. May one Tool Round contain multiple simultaneous Decision Requests? If one
   is rejected or expires, do independent sibling Tool Calls continue?
4. Does Approval need delegated approvers, expiry, quorum, or multi-party
   decisions in V2? If yes, Approval may require its own aggregate instead of
   remaining only a Decision kind.
5. Which thinking summaries and token deltas have durable product value, and
   which are transient display data eligible for compaction?
6. Is model fallback a Host-level product guarantee expressed in Model Grant,
   or an adapter policy constrained only by the grant?
7. Is multi-agent collaboration part of the V2 kernel, or a later capability
   pack built on ordinary child Conversations/Turns?
8. How long must internal ledger entries and public feed progress be retained
   for audit, support, and UI replay?

## Completion criteria

The campaign is complete when:

- Native and at least one external adapter pass one conformance suite.
- Neither adapter imports Agent ORM/repository or frontend types.
- Capability implementations receive no SQLAlchemy session or owner token.
- A Turn can pause for approval, restart the backend, and resume without
  repeating a settled side effect.
- The formal frontend renders only the closed Conversation Feed union.
- No frontend code classifies tool semantics from names or command strings.
- No public client type contains `loop_state`, `compression_state`,
  `budget_snapshot`, provider continuation, or lease fields.
- `/agent` and `/demo` share the same feed model, or the legacy demo is deleted.
- Production imports of the old `agent_core` loop/runtime/event projection and
  legacy frontend runtime are zero.
- Full backend and frontend verification passes.
