# Codex-Style Subagents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace BioinfoFlow's synchronous `task`/`subagent.analyze` path with a durable, shallow Codex-style agent tree supporting spawn, message, follow-up, wait, list, and interrupt.

**Architecture:** Child agents are ordinary persisted Agent Core sessions and turns. A focused collaboration service adds lineage, concurrency, mailbox, context-fork, and model-preflight behavior while reusing existing turn execution, steering, interruption, events, permissions, and startup recovery. Roots receive all six collaboration tools; children receive the five communication/observation tools but cannot spawn.

**Tech Stack:** Python 3.13, FastAPI service layer, SQLAlchemy async, Alembic, Agent Core tool protocol, pytest, Next.js/React public-event runtime, Vitest.

**Command working directories:** Run every `uv`, `pytest`, `ruff`, and `alembic`
command from `backend/`. Run every `bun` command from `frontend/`. Run `git`
and repository-wide `rg` commands from the repository root.

---

## File Structure

### Backend files created

- `backend/alembic/versions/0056_agent_collaboration_tree.py` — indexed parent/root/name lineage and atomic active-slot reservations.
- `backend/app/services/agent_core/collaboration/__init__.py` — public collaboration surface.
- `backend/app/services/agent_core/collaboration/contracts.py` — statuses and structured result types.
- `backend/app/services/agent_core/collaboration/context_fork.py` — filtered parent-history snapshots.
- `backend/app/services/agent_core/collaboration/model_preflight.py` — requested-model probe and parent fallback.
- `backend/app/services/agent_core/collaboration/service.py` — shared root-scoped lifecycle and mailbox logic.
- `backend/app/services/agent_core/tools/collaboration/__init__.py` — six tool exports.
- `backend/app/services/agent_core/tools/collaboration/tools.py` — thin AgentTool handlers.
- `backend/tests/test_agent_core/test_collaboration.py` — service-level lifecycle tests.
- `backend/tests/test_agent_core/test_tools/test_collaboration.py` — tool contract tests.
- `backend/tests/test_migrations/test_agent_collaboration_tree.py` — migration/backfill coverage.

### Backend files modified

- `backend/app/config.py` — default tree capacity of eight.
- `backend/app/models/agent_core.py` — typed indexed lineage columns.
- `backend/app/repositories/agent_core_repo.py` — root tree, target, sibling, mailbox, and capacity queries.
- `backend/app/services/agent_core/service.py` — collaboration finalization hook and reusable follow-up scheduling.
- `backend/app/services/agent_core/runtime.py` — publish child terminal state after turn finalization.
- `backend/app/services/agent_core/events.py` — durable collaboration events and public projection.
- `backend/app/services/agent_core/tools/providers.py` — register new tools and remove legacy tools.
- `backend/app/services/agent_core/tools/toolsets.py` — expose collaboration to roots and strip it from children.
- `backend/app/services/agent_core/context/assembler.py` and transcript helpers only where filtered fork insertion requires a public helper.
- `backend/app/services/llm/catalog.py` — reusable exact-model live availability probe.
- `backend/app/schemas/agent_core.py` — collaboration event payload typing only if existing generic payloads are insufficient.

### Legacy files removed

- `backend/app/services/agent_core/tools/subagents/task.py`
- `backend/app/services/agent_core/tools/subagents/resources.py`
- `backend/app/services/agent_core/tools/subagents/__init__.py`
- `backend/app/services/agent_core/subagents.py`
- `backend/tests/test_agent_core/test_tools/test_task.py`
- legacy delegated-runtime cases in `backend/tests/test_agent_core/test_subagents.py`

### Frontend files created or modified

- `frontend/lib/agent-runtime/types.ts` — public collaboration lifecycle payload.
- `frontend/lib/agent-runtime/public-events.ts` — normalize `agent.lifecycle` events.
- `frontend/lib/agent-runtime/agent-tree.ts` — reduce parent events into a live shallow tree.
- `frontend/components/bioinfoflow/agent-runtime/agent-tree.tsx` — compact task/status/model/error display.
- `frontend/components/bioinfoflow/agent-runtime/agent-environment-card.tsx` — host the live tree.
- `frontend/lib/agent-runtime/tool-activity.ts` — structured collaboration result preview.
- `frontend/messages/en.json`
- `frontend/messages/zh-CN.json`
- focused tests under `frontend/tests/unit/lib/agent-runtime/` and `frontend/tests/unit/components/`.

---

### Task 1: Persist the shallow agent tree and capacity invariants

**Files:**

- Create: `backend/alembic/versions/0056_agent_collaboration_tree.py`
- Modify: `backend/app/models/agent_core.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/repositories/agent_core_repo.py`
- Create: `backend/tests/test_migrations/test_agent_collaboration_tree.py`
- Modify: `backend/tests/test_auth/test_config_defaults.py`
- Create: `backend/tests/test_agent_core/test_collaboration.py`

- [ ] **Step 1: Write failing migration and repository tests**

Add tests proving:

```python
def test_agent_collaboration_slots_default_to_eight():
    assert settings.agent_collaboration_max_slots == 8


@pytest.mark.asyncio
async def test_root_tree_queries_are_indexed_and_root_scoped(db_session):
    root = await create_agent_session(db_session, user_id="dev")
    child = await create_agent_session(
        db_session,
        user_id="dev",
        parent_session_id=str(root.id),
        root_session_id=str(root.id),
        agent_name="reader",
    )
    repo = AgentSessionRepository(db_session)
    assert [session.id for session in await repo.list_agent_tree(str(root.id))] == [
        root.id,
        child.id,
    ]


@pytest.mark.asyncio
async def test_duplicate_sibling_agent_name_is_rejected(db_session):
    root = await create_agent_session(db_session, user_id="dev")
    await create_child(db_session, root=root, agent_name="reader")
    with pytest.raises(IntegrityError):
        await create_child(db_session, root=root, agent_name="reader")


@pytest.mark.asyncio
async def test_last_child_slot_is_acquired_atomically(db_session, session_factory):
    root = await root_with_six_active_children(db_session)
    results = await asyncio.gather(
        reserve_child_in_new_session(session_factory, root=root, agent_name="seven_a"),
        reserve_child_in_new_session(session_factory, root=root, agent_name="seven_b"),
        return_exceptions=True,
    )
    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert sum(is_agent_limit_error(result) for result in results) == 1
```

Migration coverage must verify legacy sessions remain valid with null collaboration columns and new sibling uniqueness works on SQLite.

- [ ] **Step 2: Run tests and confirm the expected failures**

Run:

```bash
rtk uv run pytest tests/test_migrations/test_agent_collaboration_tree.py tests/test_auth/test_config_defaults.py tests/test_agent_core/test_collaboration.py -q
```

Expected: failures for missing columns, repository methods, and configuration.

- [ ] **Step 3: Add the minimal schema**

Add nullable collaboration columns to `AgentSession`:

```python
parent_session_id: Mapped[str | None] = mapped_column(
    ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=True, index=True
)
root_session_id: Mapped[str | None] = mapped_column(
    ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=True, index=True
)
agent_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
collaboration_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
spawned_by_turn_id: Mapped[str | None] = mapped_column(
    ForeignKey("agent_turns.id", ondelete="SET NULL"), nullable=True, index=True
)
```

The migration creates a partial unique index on `(parent_session_id, agent_name)` when both values are non-null, a partial unique index on `(root_session_id, collaboration_slot)` when the slot is non-null, and indexes on `(root_session_id, status)` and `(root_session_id, active_turn_id)`. Sibling names are permanently reserved; callers reuse a completed child with `followup_task`. Root sessions keep null `root_session_id`; code treats `coalesce(root_session_id, id)` as the root identity. Child slots use integers `1..7`; slot zero is implicitly reserved for the root.

Add:

```python
agent_collaboration_max_slots: int = 8
```

- [ ] **Step 4: Add repository primitives**

Implement `get_agent_target(root_session_id, target, workspace_id, user_id)`,
`list_agent_tree(root_session_id)`, `reserve_child_slot(root_session_id)`, and
`release_child_slot(child_session_id)`. Target resolution accepts a child UUID,
bare name, `/root/name`, or `/root` when the operation permits the root, but
always constrains workspace, user, and root. Slot reservation tries integers
`1..7` using the unique database constraint and a short savepoint per attempt;
it does not depend on `SELECT FOR UPDATE`, process memory, or a prior count.

- [ ] **Step 5: Run migration/repository tests**

Run:

```bash
rtk uv run alembic upgrade head
rtk uv run pytest tests/test_migrations/test_agent_collaboration_tree.py tests/test_auth/test_config_defaults.py tests/test_agent_core/test_collaboration.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
rtk git add backend/alembic/versions/0056_agent_collaboration_tree.py backend/app/models/agent_core.py backend/app/config.py backend/app/repositories/agent_core_repo.py backend/tests/test_migrations/test_agent_collaboration_tree.py backend/tests/test_auth/test_config_defaults.py backend/tests/test_agent_core/test_collaboration.py
rtk git commit -m "feat: persist agent collaboration tree"
```

---

### Task 2: Add context forking and requested-model preflight

**Files:**

- Create: `backend/app/services/agent_core/collaboration/contracts.py`
- Create: `backend/app/services/agent_core/collaboration/context_fork.py`
- Create: `backend/app/services/agent_core/collaboration/model_preflight.py`
- Modify: `backend/app/services/llm/catalog.py`
- Modify: `backend/tests/test_agent_core/test_collaboration.py`
- Modify: `backend/tests/test_api/test_llm_api.py`

- [ ] **Step 1: Write failing context-fork tests**

Cover `none`, `all`, and numeric modes:

```python
def test_numeric_context_fork_keeps_last_user_turns_and_final_answers():
    items = build_parent_items_with_tools_reasoning_and_three_turns()
    forked = fork_agent_context(items, fork_turns="2")
    assert semantic_texts(forked) == [
        "developer rules",
        "user two",
        "assistant two final",
        "user three",
        "assistant three final",
    ]
    assert not contains_reasoning_or_tool_items(forked)


def test_none_context_fork_returns_no_parent_conversation():
    assert fork_agent_context(build_parent_items(), fork_turns="none") == []
```

Invalid values such as `"0"`, `"-1"`, and `"recent"` raise a stable `invalid_fork_turns` error.

- [ ] **Step 2: Write failing model-preflight tests**

```python
@pytest.mark.asyncio
async def test_available_requested_model_is_selected(db_session, fake_probe):
    result = await AgentModelPreflight(db_session).resolve(
        requested_model="cheap-model",
        parent_model_id="parent-id",
        parent_reasoning_effort="high",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert result.requested_model == "cheap-model"
    assert result.effective_model == "cheap-model"
    assert result.fallback is False


@pytest.mark.asyncio
async def test_explicit_model_always_runs_fresh_probe(
    db_session, successful_saved_test_status, probe_spy
):
    await resolve_requested_child_model(db_session, model="cheap-model")
    assert probe_spy.calls == ["cheap-model"]


@pytest.mark.asyncio
async def test_unavailable_requested_model_falls_back_to_parent(db_session, failing_probe):
    result = await AgentModelPreflight(db_session).resolve(
        requested_model="unavailable-model",
        parent_model_id="parent-id",
        parent_reasoning_effort="high",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert result.effective_model_id == "parent-id"
    assert result.fallback is True
    assert result.fallback_reason == "requested_model_unavailable"
```

Also prove the probe targets the exact requested model and never serializes credentials.

- [ ] **Step 3: Run focused tests and confirm failures**

Run:

```bash
rtk uv run pytest tests/test_agent_core/test_collaboration.py tests/test_api/test_llm_api.py -q
```

Expected: failures for missing fork/preflight APIs.

- [ ] **Step 4: Implement immutable contracts and context filtering**

Add dataclasses/enums for:

```python
@dataclass(frozen=True)
class AgentModelChoice:
    requested_model: str | None
    effective_model: str
    effective_model_id: str
    reasoning_effort: str | None
    fallback: bool
    fallback_reason: str | None


@dataclass(frozen=True)
class AgentStatusView:
    status: str
    final_text: str | None = None
    error_code: str | None = None
    error_message: str | None = None
```

`fork_agent_context()` filters canonical transcript items without provider-specific request shaping.

- [ ] **Step 5: Expose exact-model probe reuse**

Add a catalog method that resolves a caller-visible active model, verifies tool capability, and calls `LlmProviderProbe` for that exact model on every explicit child override. Existing provider test status is informational and never suppresses this spawn-time probe. The method returns a safe structured availability result, never credential material.

`AgentModelPreflight.resolve()` probes only explicit overrides. Missing, unauthorized, disabled, unsupported, authentication-failed, or runtime-failed requested models return the parent model with safe fallback metadata. Unsupported explicit reasoning effort remains a validation error unless the model itself falls back, in which case parent effort is used.

- [ ] **Step 6: Run tests**

Run:

```bash
rtk uv run pytest tests/test_agent_core/test_collaboration.py tests/test_api/test_llm_api.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
rtk git add backend/app/services/agent_core/collaboration/contracts.py backend/app/services/agent_core/collaboration/context_fork.py backend/app/services/agent_core/collaboration/model_preflight.py backend/app/services/llm/catalog.py backend/tests/test_agent_core/test_collaboration.py backend/tests/test_api/test_llm_api.py
rtk git commit -m "feat: resolve child context and model fallback"
```

---

### Task 3: Implement asynchronous spawn, list, and tool exposure

**Files:**

- Create: `backend/app/services/agent_core/collaboration/service.py`
- Create: `backend/app/services/agent_core/collaboration/__init__.py`
- Create: `backend/app/services/agent_core/tools/collaboration/tools.py`
- Create: `backend/app/services/agent_core/tools/collaboration/__init__.py`
- Modify: `backend/app/services/agent_core/service.py`
- Modify: `backend/app/repositories/agent_core_repo.py`
- Modify: `backend/app/services/agent_core/tools/providers.py`
- Modify: `backend/app/services/agent_core/tools/toolsets.py`
- Create: `backend/tests/test_agent_core/test_tools/test_collaboration.py`
- Modify: `backend/tests/test_agent_core/test_harness_invariants.py`
- Modify: `backend/tests/test_agent_core/test_collaboration.py`

- [ ] **Step 1: Write failing spawn/list tests**

```python
@pytest.mark.asyncio
async def test_spawn_agent_returns_before_child_completes(db_session, blocked_gateway):
    result = await SpawnAgentTool().run(
        {"task_name": "reader", "message": "Inspect README", "fork_turns": "none"},
        root_tool_context(db_session),
    )
    assert result["task_name"] == "/root/reader"
    assert result["status"] in {"pending_init", "running"}
    assert result["child_session_id"]
    assert child_turn_is_queued_or_running(db_session, result["child_session_id"])


@pytest.mark.asyncio
async def test_spawn_enforces_eight_total_active_slots(db_session):
    root = await root_with_seven_active_children(db_session)
    with pytest.raises(ConflictError, match="agent_limit_reached"):
        await collaboration(root).spawn_agent(task_name="eighth", message="work")


def test_child_toolset_hides_spawn_but_keeps_coordination_tools():
    names = ToolsetExposure(build_default_tool_registry()).exposed_names(
        policy={"name": "execution"}, role="subagent"
    )
    assert "spawn_agent" not in names
    assert {
        "send_message",
        "followup_task",
        "wait_agent",
        "list_agents",
        "interrupt_agent",
    } <= names
```

Also cover invalid names, duplicate siblings, non-root spawn rejection, user/workspace isolation, requested-model fallback metadata, and deterministic list ordering.

- [ ] **Step 2: Run tests and confirm failures**

Run:

```bash
rtk uv run pytest tests/test_agent_core/test_tools/test_collaboration.py tests/test_agent_core/test_collaboration.py tests/test_agent_core/test_harness_invariants.py -q
```

Expected: failures for missing tools/service and old exposure.

- [ ] **Step 3: Implement `AgentCollaborationService.spawn_agent()`**

The method signature is `spawn_agent(*, parent_session_id, parent_turn_id,
task_name, message, fork_turns="all", model=None,
reasoning_effort=None) -> SpawnAgentResult`.

Resolve and live-probe the optional requested model before entering the database critical section. Then use non-committing repository/service primitives to reserve one unique child slot, create the child session, insert filtered fork messages, create and claim the initial queued turn, and commit them atomically. Only after commit call `enqueue_turn_run()`. A failed commit leaves neither child nor turn; an enqueue failure leaves a recoverable queued turn for startup recovery.

Refactor the existing session/turn creation internals just enough to accept `commit=False`; preserve current public behavior when omitted. Do not call the commit-owning `create_session()` or `create_turn()` from inside the collaboration transaction.

- [ ] **Step 4: Implement `list_agents()` and status projection**

Map internal states to:

```text
pending_init
running
interrupted
completed
errored
not_found
```

Completed and errored sessions remain addressable for follow-ups. Return safe final text/error/model fields.

- [ ] **Step 5: Register only the new collaboration tools**

Replace `task` in `_EXECUTION_TOOLS` with:

```python
COLLABORATION_TOOL_NAMES = frozenset(
    {
        "spawn_agent",
        "send_message",
        "followup_task",
        "wait_agent",
        "list_agents",
        "interrupt_agent",
    }
)
```

Root execution sessions receive the set. Child exposure receives the ordinary tools allowed by policy plus the five communication/observation tools, while subtracting `spawn_agent` and user-interaction tools that would deadlock an unattended child. Spawn enforcement is duplicated in the service so exposure mistakes fail closed.

- [ ] **Step 6: Run tests**

Run:

```bash
rtk uv run pytest tests/test_agent_core/test_tools/test_collaboration.py tests/test_agent_core/test_collaboration.py tests/test_agent_core/test_harness_invariants.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
rtk git add backend/app/services/agent_core/collaboration backend/app/services/agent_core/tools/collaboration backend/app/services/agent_core/tools/providers.py backend/app/services/agent_core/tools/toolsets.py backend/app/services/agent_core/service.py backend/app/repositories/agent_core_repo.py backend/tests/test_agent_core/test_tools/test_collaboration.py backend/tests/test_agent_core/test_collaboration.py backend/tests/test_agent_core/test_harness_invariants.py
rtk git commit -m "feat: spawn and list child agents"
```

---

### Task 4: Implement durable messaging, follow-up, wait, interrupt, and terminal notifications

**Files:**

- Modify: `backend/app/services/agent_core/collaboration/service.py`
- Modify: `backend/app/services/agent_core/tools/collaboration/tools.py`
- Modify: `backend/app/services/agent_core/transcript/store.py`
- Modify: `backend/app/services/agent_core/service.py`
- Modify: `backend/app/services/agent_core/runtime.py`
- Modify: `backend/app/services/agent_core/events.py`
- Modify: `backend/tests/test_agent_core/test_collaboration.py`
- Modify: `backend/tests/test_agent_core/test_tools/test_collaboration.py`
- Modify: `backend/tests/test_agent_core/test_active_turn_steering.py`
- Modify: `backend/tests/test_agent_core/test_runtime_reliability.py`

- [ ] **Step 1: Write failing messaging and follow-up tests**

```python
@pytest.mark.asyncio
async def test_send_message_to_idle_child_does_not_start_turn(db_session):
    child = await completed_child(db_session)
    await collaboration_for_root(db_session).send_message(
        target="/root/reader", message="Extra context"
    )
    assert await latest_turn_id(db_session, child.id) == child.latest_turn_id
    assert await pending_agent_messages(db_session, child.id) == ["Extra context"]


@pytest.mark.asyncio
async def test_followup_task_reuses_idle_child_and_starts_turn(db_session):
    child = await completed_child(db_session)
    await collaboration_for_root(db_session).followup_task(
        target="/root/reader", message="Now inspect pyproject.toml"
    )
    assert await active_turn_input(db_session, child.id) == "Now inspect pyproject.toml"


@pytest.mark.asyncio
async def test_child_can_message_parent_and_follow_up_sibling(db_session):
    root, sender, sibling = await root_with_two_children(db_session)
    child_api = collaboration_for_session(db_session, sender.id)
    await child_api.send_message(target="/root", message="I found the config")
    await child_api.followup_task(
        target="/root/reviewer", message="Check the config I found"
    )
    assert await pending_agent_messages(db_session, root.id) == ["I found the config"]
    assert await active_turn_input(db_session, sibling.id) == "Check the config I found"
```

Cover active-turn steer delivery, queued follow-up races, single-active-turn invariant, cross-root rejection, `followup_task` rejection for `/root`, and interrupt rejection for root/self. `list_agents` and `wait_agent` always use the caller's root tree, whether the caller is root or child.

- [ ] **Step 2: Write failing wait/interrupt/notification tests**

```python
@pytest.mark.asyncio
async def test_wait_wakes_for_child_terminal_notification(db_session):
    waiter = asyncio.create_task(collaboration_for_root(db_session).wait_agent(5_000))
    await publish_child_completed(db_session, task_name="reader", final_text="README found")
    result = await waiter
    assert result.timed_out is False
    assert result.updated_agents == ["/root/reader"]


@pytest.mark.asyncio
async def test_failed_child_notification_never_has_empty_error(db_session):
    await publish_child_failed(
        db_session,
        error_code="model_request_failed",
        error_message="Model provider authentication failed.",
    )
    event = await latest_parent_agent_event(db_session)
    assert event.payload["error_code"] == "model_request_failed"
    assert event.payload["error_message"]


@pytest.mark.asyncio
async def test_waited_child_result_enters_parent_model_context_once(
    db_session, session_factory
):
    root, parent_turn, child = await running_parent_with_child(db_session)
    await publish_child_completed(
        db_session, task_name="reader", final_text="README found"
    )
    await collaboration_for_root(db_session).wait_agent(5_000)
    first = await assembled_parent_context(session_factory, parent_turn.id)
    second = await assembled_parent_context(session_factory, parent_turn.id)
    assert count_text(first, "README found") == 1
    assert count_text(second, "README found") == 1


@pytest.mark.asyncio
async def test_idle_parent_consumes_child_result_on_next_turn_after_restart(
    db_session, session_factory
):
    root, child = await idle_parent_with_child(db_session)
    await publish_child_completed(
        db_session, task_name="reader", final_text="README found"
    )
    await simulate_backend_restart()
    turn = await create_next_root_turn(session_factory, root.id, "Continue")
    context = await assembled_parent_context(session_factory, turn.id)
    assert count_text(context, "README found") == 1


@pytest.mark.asyncio
async def test_interrupt_keeps_child_reusable(db_session):
    previous = await collaboration_for_root(db_session).interrupt_agent("/root/reader")
    assert previous.status == "running"
    await collaboration_for_root(db_session).followup_task(
        target="/root/reader", message="Try a smaller task"
    )
    assert await child_status(db_session, "reader") in {"pending_init", "running"}
```

- [ ] **Step 3: Run tests and confirm failures**

Run:

```bash
rtk uv run pytest tests/test_agent_core/test_tools/test_collaboration.py tests/test_agent_core/test_collaboration.py tests/test_agent_core/test_active_turn_steering.py tests/test_agent_core/test_runtime_reliability.py -q
```

Expected: failures for missing mailbox and terminal hooks.

- [ ] **Step 4: Implement durable mailbox behavior**

Persist inter-agent messages with explicit metadata:

```python
{
    "kind": "inter_agent_message",
    "root_session_id": root_id,
    "sender_session_id": sender_id,
    "delivery": "queued" | "steer" | "followup",
    "consumed": False,
}
```

Consumption must atomically mark messages so restart/retry cannot deliver them twice. `send_message` never creates a turn. `followup_task` creates a turn only when idle and a unique child slot is acquired; otherwise it steers or queues exactly one follow-up. Children can message `/root` and target siblings, but cannot spawn or create a follow-up turn on the root.

- [ ] **Step 5: Add one child-terminal publication hook**

After any child turn reaches completed, internally failed, or interrupted, publish a parent-session collaboration event. Internal failed status is normalized to the external `errored` status. The payload contains:

```python
{
    "child_session_id": child_id,
    "task_name": canonical_name,
    "status": status,
    "final_text": turn.final_text,
    "error_code": turn.error_code,
    "error_message": turn.error_message or fallback_terminal_message(status),
    "termination_reason": turn.termination_reason,
    "token_usage": turn.token_usage,
    "effective_model": resolved_model_name(turn),
}
```

The hook releases the child's collaboration slot, schedules one pending follow-up if present, and enqueues the terminal notification for the parent. Active parents receive it as a durable steer so the existing loop injects it before the next model call; idle parents receive a committed unseen mailbox message consumed by the next turn.

- [ ] **Step 6: Implement bounded `wait_agent()`**

Use parent event/mailbox sequence as the durable cursor. Wait is a replayable observation: check for unseen updates, await a bounded notification, then re-check durable state. It ends on child update, parent steer, or timeout and does not return full mailbox content in the tool result. Before the loop's next model invocation, unseen mailbox items are atomically appended to canonical parent context and marked consumed.

- [ ] **Step 7: Implement interrupt through the existing service**

Resolve the child under the caller's root, snapshot previous status, interrupt its active turn idempotently, and leave the session active and reusable.

- [ ] **Step 8: Run tests**

Run:

```bash
rtk uv run pytest tests/test_agent_core/test_tools/test_collaboration.py tests/test_agent_core/test_collaboration.py tests/test_agent_core/test_active_turn_steering.py tests/test_agent_core/test_runtime_reliability.py -q
```

Expected: pass.

- [ ] **Step 9: Commit**

```bash
rtk git add backend/app/services/agent_core/collaboration backend/app/services/agent_core/tools/collaboration backend/app/services/agent_core/transcript/store.py backend/app/services/agent_core/service.py backend/app/services/agent_core/runtime.py backend/app/services/agent_core/events.py backend/tests/test_agent_core/test_tools/test_collaboration.py backend/tests/test_agent_core/test_collaboration.py backend/tests/test_agent_core/test_active_turn_steering.py backend/tests/test_agent_core/test_runtime_reliability.py
rtk git commit -m "feat: coordinate child agent lifecycle"
```

---

### Task 5: Project live child lifecycle into the frontend

**Files:**

- Modify: `backend/app/services/agent_core/events.py`
- Modify: `backend/tests/test_agent_core/test_public_events.py`
- Modify: `backend/tests/test_api/test_agent_core_api.py`
- Modify: `frontend/lib/agent-runtime/types.ts`
- Modify: `frontend/lib/agent-runtime/public-events.ts`
- Create: `frontend/lib/agent-runtime/agent-tree.ts`
- Create: `frontend/components/bioinfoflow/agent-runtime/agent-tree.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-environment-card.tsx`
- Modify: `frontend/lib/agent-runtime/tool-activity.ts`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`
- Modify: `frontend/tests/unit/lib/agent-runtime/public-events.test.ts`
- Create: `frontend/tests/unit/lib/agent-runtime/agent-tree.test.ts`
- Modify: `frontend/tests/unit/components/agent-runtime-cards.test.tsx`

- [ ] **Step 1: Write failing public-event tests**

Assert internal collaboration events project to `agent.lifecycle`, remain user-safe, and appear through both state replay and SSE. Failed payloads must contain a safe non-empty error; credential data and raw provider bodies must be absent.

- [ ] **Step 2: Write failing frontend reducer/component tests**

```ts
it("reduces child lifecycle events into a stable shallow tree", () => {
  const tree = reduceAgentTree([], [
    lifecycle("reader", "running", { effectiveModel: "cheap-model" }),
    lifecycle("reader", "completed", { finalText: "README found" }),
  ])
  expect(tree).toEqual([
    expect.objectContaining({ taskName: "/root/reader", status: "completed" }),
  ])
})

it("renders requested model fallback and child errors", () => {
  render(<AgentTree agents={[failedAgentWithModelFallback()]} />)
  expect(screen.getByText(/fell back/i)).toBeInTheDocument()
  expect(screen.getByText("Model provider authentication failed.")).toBeInTheDocument()
})
```

- [ ] **Step 3: Run focused tests and confirm failures**

Run:

```bash
rtk uv run pytest tests/test_agent_core/test_public_events.py tests/test_api/test_agent_core_api.py -q
rtk bun run test --run tests/unit/lib/agent-runtime/public-events.test.ts tests/unit/lib/agent-runtime/agent-tree.test.ts tests/unit/components/agent-runtime-cards.test.tsx
```

Expected: failures for missing event family and UI reducer.

- [ ] **Step 4: Add safe public projection**

Add `PublicAgentEventType.AGENT_LIFECYCLE = "agent.lifecycle"` and project spawn, running, model fallback, message/follow-up, completed, errored, and interrupted events. Preserve only the safe payload fields defined in the design.

- [ ] **Step 5: Add the shallow tree reducer and compact UI**

`reduceAgentTree()` keys nodes by child session id, applies events by sequence, and sorts by canonical task path. The compact component shows status, task path, effective model, fallback badge, final summary, and error. Reuse existing card styles and status primitives; do not add a separate polling API.

- [ ] **Step 6: Add bilingual copy and structured tool previews**

Add matching English and Chinese keys for agent status, model fallback, no final text, and interruption. Extend `outputPreview()` to read collaboration fields rather than showing an empty generic result.

- [ ] **Step 7: Run focused backend/frontend tests**

Run:

```bash
rtk uv run pytest tests/test_agent_core/test_public_events.py tests/test_api/test_agent_core_api.py -q
rtk bun run test --run tests/unit/lib/agent-runtime/public-events.test.ts tests/unit/lib/agent-runtime/agent-tree.test.ts tests/unit/components/agent-runtime-cards.test.tsx
rtk bun run lint:i18n
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
rtk git add backend/app/services/agent_core/events.py backend/tests/test_agent_core/test_public_events.py backend/tests/test_api/test_agent_core_api.py frontend/lib/agent-runtime/types.ts frontend/lib/agent-runtime/public-events.ts frontend/lib/agent-runtime/agent-tree.ts frontend/components/bioinfoflow/agent-runtime/agent-tree.tsx frontend/components/bioinfoflow/agent-runtime/agent-environment-card.tsx frontend/lib/agent-runtime/tool-activity.ts frontend/messages/en.json frontend/messages/zh-CN.json frontend/tests/unit/lib/agent-runtime/public-events.test.ts frontend/tests/unit/lib/agent-runtime/agent-tree.test.ts frontend/tests/unit/components/agent-runtime-cards.test.tsx
rtk git commit -m "feat: show child agent lifecycle"
```

---

### Task 6: Remove the legacy subagent path and verify the migration

**Files:**

- Delete: `backend/app/services/agent_core/tools/subagents/task.py`
- Delete: `backend/app/services/agent_core/tools/subagents/resources.py`
- Delete: `backend/app/services/agent_core/tools/subagents/__init__.py`
- Delete: `backend/app/services/agent_core/subagents.py`
- Delete: `backend/tests/test_agent_core/test_tools/test_task.py`
- Modify/Delete: `backend/tests/test_agent_core/test_subagents.py`
- Modify: `backend/app/services/agent_core/__init__.py`
- Modify: relevant docs/tool snapshots found by `rtk rg -n "subagent\.analyze|TaskTool|ReadOnlySubagentRunner|\"task\"" backend frontend docs`

- [ ] **Step 1: Write/extend the regression that reproduces the original failure**

The test creates a parent turn with an explicitly working model while the catalog default is configured but authentication-failing. Spawning without a model override must use the parent model and complete; spawning with the failing catalog model must probe, fall back to the parent model, and expose fallback metadata. An errored child must surface its persisted error instead of `final_text=""` with no explanation.

- [ ] **Step 2: Run the regression before cleanup**

Run:

```bash
rtk uv run pytest tests/test_agent_core/test_collaboration.py -k "authentication or parent_model or fallback" -q
```

Expected: pass with the new implementation.

- [ ] **Step 3: Delete legacy code and remove all registrations/references**

Run searches after deletion:

```bash
rtk rg -n "subagent\.analyze|TaskTool|ReadOnlySubagentRunner" backend frontend docs
rtk rg -n '"task"' backend/app/services/agent_core backend/tests/test_agent_core
```

Expected: no legacy implementation references; ordinary workflow/task-domain strings outside Agent Core are allowed.

- [ ] **Step 4: Run backend verification**

Run from `backend/`:

```bash
rtk uv run alembic upgrade head
rtk uv run pytest
rtk uv run ruff check .
```

Expected: all pass.

- [ ] **Step 5: Run frontend verification**

Run from `frontend/`:

```bash
rtk bun run lint
rtk bun run lint:i18n
rtk bun run lint:dead-code
rtk bun run test
```

Expected: new work passes. If `lint:dead-code` reports only the documented pre-existing landing-component/icon baseline, record it explicitly in the PR.

- [ ] **Step 6: Run repository checks**

Run:

```bash
rtk git diff --check origin/main...HEAD
rtk git status --short
```

Expected: no whitespace errors and no uncommitted files.

- [ ] **Step 7: Commit cleanup**

```bash
rtk git add -A
rtk git commit -m "refactor: replace legacy subagent task"
```

- [ ] **Step 8: Request final review**

Provide the reviewer with the design, this plan, `origin/main`, and `HEAD`. Resolve every Critical or Important issue, rerun affected tests, and request re-review until approved.

- [ ] **Step 9: Rebase, verify, push, and create the PR**

```bash
rtk git fetch origin --prune
rtk git rebase origin/main
```

Rerun the backend/frontend verification matrix after rebase, then:

```bash
rtk git push -u origin codex/codex-style-subagents
rtk gh pr create --title "feat: add Codex-style subagents" --body-file /tmp/bioinfoflow-subagents-pr.md
```

The PR body must include summary, original root cause, architecture, model fallback behavior, migration notes, full verification results, and any unchanged baseline warnings.
