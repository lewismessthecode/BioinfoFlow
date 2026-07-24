# Active-turn Steering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace interrupt-on-follow-up with durable same-turn steering, preserve explicit queue and stop behavior, and flatten the custom-instructions form.

**Architecture:** Pending steering inputs are persisted as draft user messages and promoted into the transcript only at safe agent-loop boundaries. An `accepts_steer` turn flag closes the finalization race, while ledger events drive durable same-turn UI segments.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, pytest, Next.js 16, React 19, TypeScript, next-intl, Vitest, Testing Library.

---

### Task 1: Persist the steer acceptance contract

**Files:**
- Create: `backend/alembic/versions/0054_agent_turn_steering.py`
- Modify: `backend/app/models/agent_core.py`
- Modify: `backend/tests/test_migrations/test_agent_permission_upgrade_compatibility.py`
- Test: `backend/tests/test_agent_core/test_active_turn_steering.py`

- [ ] **Step 1: Write a failing model/repository test**

Add a test that creates a running turn and asserts the wished-for
`accepts_steer` property defaults to `True`, then terminalizes it and asserts the
property becomes `False`.

```python
async def test_running_turn_accepts_steer_until_terminal(db_session):
    service, turn = await create_running_turn(db_session)
    assert turn.accepts_steer is True

    completed = await service.turn_repo.update_all(
        turn,
        status=AgentTurnStatus.COMPLETED,
        accepts_steer=False,
    )

    assert completed.accepts_steer is False
```

- [ ] **Step 2: Run the test and verify RED**

Run: `rtk uv run pytest tests/test_agent_core/test_active_turn_steering.py::test_running_turn_accepts_steer_until_terminal -q`

Expected: FAIL because `AgentTurn` has no `accepts_steer` field.

- [ ] **Step 3: Add the schema field and migration**

Add a non-null boolean `accepts_steer` column with Python and server defaults of
true. Migration `0054_agent_turn_steering` revises the latest main-branch
migration, `0053_remote_connection_jump_host`. Update `EXPECTED_HEAD` to the new
revision.

- [ ] **Step 4: Run the focused test and migration tests**

Run: `rtk uv run pytest tests/test_agent_core/test_active_turn_steering.py::test_running_turn_accepts_steer_until_terminal tests/test_migrations/test_agent_permission_upgrade_compatibility.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add backend/alembic/versions/0054_agent_turn_steering.py backend/app/models/agent_core.py backend/tests/test_migrations/test_agent_permission_upgrade_compatibility.py backend/tests/test_agent_core/test_active_turn_steering.py
rtk git commit -m "feat: add active turn steering state"
```

### Task 2: Add atomic steering persistence and API

**Files:**
- Modify: `backend/app/schemas/agent_core.py`
- Modify: `backend/app/repositories/agent_core_repo.py`
- Modify: `backend/app/services/agent_core/service.py`
- Modify: `backend/app/services/agent_core/events.py`
- Modify: `backend/app/api/v1/agent.py`
- Test: `backend/tests/test_agent_core/test_active_turn_steering.py`

- [ ] **Step 1: Write failing API tests**

Cover these behaviors with real API/service calls:

```python
async def test_steer_active_turn_persists_draft_user_message(async_client, running_turn):
    response = await async_client.post(
        f"/api/v1/agent/turns/{running_turn.id}/steer",
        json={"input_text": "Use the project virtualenv instead."},
    )
    assert response.status_code == 200
    assert response.json()["data"]["delivery"] == "pending"


async def test_steer_rejects_sealed_turn(async_client, sealed_turn):
    response = await async_client.post(
        f"/api/v1/agent/turns/{sealed_turn.id}/steer",
        json={"input_text": "Too late"},
    )
    assert response.status_code == 409
```

Also assert the pending row is a draft user message with ordering index zero and
that `turn.steer.received` contains the stable steer id and display metadata.

- [ ] **Step 2: Run the tests and verify RED**

Run: `rtk uv run pytest tests/test_agent_core/test_active_turn_steering.py -q`

Expected: FAIL with a missing steer route/service method.

- [ ] **Step 3: Implement the minimal endpoint and repository transaction**

Add:

```python
class AgentTurnSteer(BaseModel):
    input_text: str = Field(min_length=1)
    input_parts: list[dict] | None = None
    active_skill_names: list[str] | None = None
    metadata: dict | None = None


class AgentTurnSteerRead(BaseModel):
    steer_id: UUID
    turn_id: UUID
    delivery: Literal["pending"] = "pending"
```

The repository method must lock/claim the active, steerable turn row, insert the
draft `AgentMessage`, append `turn.steer.received` in the same transaction, and
return `None` when the turn is terminal or sealed.

- [ ] **Step 4: Run focused backend tests**

Run: `rtk uv run pytest tests/test_agent_core/test_active_turn_steering.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/schemas/agent_core.py backend/app/repositories/agent_core_repo.py backend/app/services/agent_core/service.py backend/app/services/agent_core/events.py backend/app/api/v1/agent.py backend/tests/test_agent_core/test_active_turn_steering.py
rtk git commit -m "feat: accept guidance for active agent turns"
```

### Task 3: Deliver steering inputs at safe loop boundaries

**Files:**
- Modify: `backend/app/repositories/agent_core_repo.py`
- Modify: `backend/app/services/agent_core/transcript/store.py`
- Modify: `backend/app/services/agent_core/core/loop.py`
- Modify: `backend/app/services/agent_core/runtime.py`
- Modify: `backend/app/services/agent_core/service.py`
- Test: `backend/tests/test_agent_core/test_active_turn_steering.py`
- Test: `backend/tests/test_agent_core/test_model_runtime_integration.py`

- [ ] **Step 1: Write failing FIFO promotion tests**

Create two pending steering messages and assert the wished-for drain method:

```python
delivered = await transcript.deliver_pending_steers(
    session_id=str(turn.session_id),
    turn_id=str(turn.id),
    expected_owner_token=turn.owner_token,
)

assert [parts_to_text(item.content_parts) for item in delivered] == ["First", "Second"]
assert all(item.status == AgentMessageStatus.COMMITTED for item in delivered)
assert [item.ordering_index for item in delivered] == sorted(
    item.ordering_index for item in delivered
)
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `rtk uv run pytest tests/test_agent_core/test_active_turn_steering.py::test_pending_steers_are_delivered_fifo -q`

Expected: FAIL because the drain method does not exist.

- [ ] **Step 3: Implement owner-fenced promotion and delivery events**

Promote all draft steer messages in creation order, assign indexes after the
current transcript tail, mark them committed, and append one
`turn.steer.delivered` event per message in the same owned transaction.

- [ ] **Step 4: Write failing loop-boundary integration tests**

Use a controlled model gateway and blocking tool to prove:

1. the first model request emits a tool call;
2. steering is accepted while the tool is running;
3. the tool is not cancelled;
4. the second model request contains tool results followed by the steering user
   message;
5. the original turn completes rather than becoming cancelled.

Add a text-only response test where a steer arrives during streaming and the
first assistant text is committed before the steer, followed by another model
iteration in the same turn.

- [ ] **Step 5: Run the integration tests and verify RED**

Run: `rtk uv run pytest tests/test_agent_core/test_model_runtime_integration.py -k 'steer' -q`

Expected: FAIL because the loop currently returns after the first final response
and never drains pending steer messages.

- [ ] **Step 6: Implement safe-boundary draining and sealing**

Add a loop helper that delivers pending messages after tool-result persistence
and after final assistant-text persistence. If delivery returns messages, continue
the loop. If none remain, atomically set `accepts_steer=False`; retry the drain if
sealing loses to a concurrent steer insert.

Terminalization and hard cancellation must mark remaining draft steers
superseded and emit `turn.steer.cancelled`.

- [ ] **Step 7: Run focused backend suites**

Run: `rtk uv run pytest tests/test_agent_core/test_active_turn_steering.py tests/test_agent_core/test_model_runtime_integration.py -k 'steer or active_turn' -q`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
rtk git add backend/app/repositories/agent_core_repo.py backend/app/services/agent_core/transcript/store.py backend/app/services/agent_core/core/loop.py backend/app/services/agent_core/runtime.py backend/app/services/agent_core/service.py backend/tests/test_agent_core/test_active_turn_steering.py backend/tests/test_agent_core/test_model_runtime_integration.py
rtk git commit -m "feat: steer agent turns at safe boundaries"
```

### Task 4: Project steering events into the transcript

**Files:**
- Modify: `frontend/lib/agent-runtime/types.ts`
- Modify: `frontend/lib/agent-runtime/segments.ts`
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-transcript.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`
- Create: `frontend/tests/unit/lib/agent-runtime/timeline.test.ts`
- Test: `frontend/tests/unit/components/agent-transcript.test.tsx`

- [ ] **Step 1: Write failing segment projection tests**

Build received and delivered events with the same `steer_id` and assert one
`user_steer` segment is produced at the received sequence with delivered state.
Add received-only and cancelled variants.

```typescript
expect(entry.segments).toContainEqual(
  expect.objectContaining({
    kind: "user_steer",
    steer: expect.objectContaining({ text: "Use uv", status: "delivered" }),
  }),
)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `rtk bun run test -- frontend/tests/unit/lib/agent-runtime/timeline.test.ts frontend/tests/unit/components/agent-transcript.test.tsx`

Expected: FAIL because `user_steer` is not a transcript segment.

- [ ] **Step 3: Add the segment type and renderer**

Add `AgentRuntimeUserSteerSegment` and merge steer lifecycle events by
`steer_id`. Render the segment as a right-aligned user bubble. Pending text is
"Will be considered after the current step" / "将在当前步骤结束后参考";
cancelled text is "Not processed because the response stopped" /
"回复已停止，未处理此消息".

- [ ] **Step 4: Run tests and i18n lint**

Run: `rtk bun run test -- frontend/tests/unit/lib/agent-runtime/timeline.test.ts frontend/tests/unit/components/agent-transcript.test.tsx`

Run: `rtk bun run lint:i18n`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/lib/agent-runtime/types.ts frontend/lib/agent-runtime/segments.ts frontend/components/bioinfoflow/agent-runtime/agent-transcript.tsx frontend/messages/en.json frontend/messages/zh-CN.json frontend/tests/unit/lib/agent-runtime/timeline.test.ts frontend/tests/unit/components/agent-transcript.test.tsx
rtk git commit -m "feat: show guidance inside active turns"
```

### Task 5: Replace interrupt-on-submit with steering

**Files:**
- Modify: `frontend/lib/agent-runtime/client.ts`
- Modify: `frontend/hooks/use-agent-runtime.ts`
- Modify: `frontend/lib/agent-runtime/turn-policy.ts`
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-composer.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx`
- Modify: `frontend/components/bioinfoflow/settings/settings-page-client.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`
- Test: `frontend/tests/unit/lib/agent-runtime/client.test.ts`
- Test: `frontend/tests/unit/hooks/use-agent-runtime.test.tsx`
- Test: `frontend/tests/unit/components/agent-composer.test.tsx`
- Test: `frontend/tests/unit/components/agent-workbench.test.tsx`
- Test: `frontend/tests/unit/components/settings-page.test.tsx`

- [ ] **Step 1: Write failing client and hook tests**

Assert `steerAgentRuntimeTurn` posts to `/agent/turns/{turnId}/steer` with text,
parts, active skills, and display metadata. Assert `useAgentRuntime().steer`
selects the latest active turn and refreshes state after acceptance.

- [ ] **Step 2: Run tests and verify RED**

Run: `rtk bun run test -- frontend/tests/unit/lib/agent-runtime/client.test.ts frontend/tests/unit/hooks/use-agent-runtime.test.tsx`

Expected: FAIL with missing client/hook functions.

- [ ] **Step 3: Implement client and hook steering**

Expose:

```typescript
steer(text, {
  inputParts,
  activeSkillNames,
  metadata,
}): Promise<AgentTurnSteerResult | null>
```

Return a typed conflict result for sealed-turn races so the workbench can keep
the optimistic draft and fall back after idle.

- [ ] **Step 4: Write failing workbench/composer tests**

Replace the old interrupt test with assertions that:

- Enter during a running turn calls `steer`, not `interrupt` or `send`;
- the draft clears and appears optimistically within the active turn;
- a sealed-turn conflict waits for idle and then calls `send` exactly once;
- queue mode remains FIFO;
- stop still calls interrupt and discards undelivered local drafts;
- both send and stop controls are available while running.

- [ ] **Step 5: Run tests and verify RED**

Run: `rtk bun run test -- frontend/tests/unit/components/agent-composer.test.tsx frontend/tests/unit/components/agent-workbench.test.tsx frontend/tests/unit/components/settings-page.test.tsx`

Expected: FAIL because active submissions still interrupt and the composer swaps
send for stop.

- [ ] **Step 6: Implement the steering policy and controls**

Rename policy value `interrupt` to `steer`, migrate the legacy localStorage value
to `steer`, and make it the default. Keep `queue` unchanged. Render a send button
when the draft is non-empty and a separate stop button whenever `isRunning`.

Use labels:

- EN: "Guide current response" / "Add this message to the active response at
  the next safe step."
- ZH: "融入当前回复" / "在下一个安全步骤把这条消息交给当前回复继续处理。"

- [ ] **Step 7: Run focused frontend tests**

Run: `rtk bun run test -- frontend/tests/unit/lib/agent-runtime/client.test.ts frontend/tests/unit/hooks/use-agent-runtime.test.tsx frontend/tests/unit/components/agent-composer.test.tsx frontend/tests/unit/components/agent-workbench.test.tsx frontend/tests/unit/components/settings-page.test.tsx`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
rtk git add frontend/lib/agent-runtime/client.ts frontend/hooks/use-agent-runtime.ts frontend/lib/agent-runtime/turn-policy.ts frontend/components/bioinfoflow/agent-runtime/agent-composer.tsx frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx frontend/components/bioinfoflow/settings/settings-page-client.tsx frontend/messages/en.json frontend/messages/zh-CN.json frontend/tests/unit/lib/agent-runtime/client.test.ts frontend/tests/unit/hooks/use-agent-runtime.test.tsx frontend/tests/unit/components/agent-composer.test.tsx frontend/tests/unit/components/agent-workbench.test.tsx frontend/tests/unit/components/settings-page.test.tsx
rtk git commit -m "fix: keep active conversations continuous"
```

### Task 6: Flatten custom instructions

**Files:**
- Modify: `frontend/components/bioinfoflow/settings/agent-custom-instructions.tsx`
- Modify: `frontend/components/bioinfoflow/settings/settings-page-client.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`
- Test: `frontend/tests/unit/components/agent-custom-instructions.test.tsx`
- Test: `frontend/tests/unit/components/settings-page.test.tsx`

- [ ] **Step 1: Write failing layout/copy tests**

Assert the settings page has one shared agent settings group, the instructions
form does not render another card section, and the concise text is present:

```typescript
expect(screen.getByText("Add lasting context for new conversations.")).toBeInTheDocument()
expect(screen.getByTestId("agent-custom-instructions")).toHaveAttribute("data-layout", "flat")
```

- [ ] **Step 2: Run tests and verify RED**

Run: `rtk bun run test -- frontend/tests/unit/components/agent-custom-instructions.test.tsx frontend/tests/unit/components/settings-page.test.tsx`

Expected: FAIL because the component still owns padded card-like layout and old
copy.

- [ ] **Step 3: Implement the flat form**

Place `AgentCustomInstructions` as the second row of the existing agent
`SettingsGroup`. Use one concise description, move the new-session helper beside
the count, and keep the textarea as the only bordered inner surface.

- [ ] **Step 4: Run tests and i18n checks**

Run: `rtk bun run test -- frontend/tests/unit/components/agent-custom-instructions.test.tsx frontend/tests/unit/components/settings-page.test.tsx`

Run: `rtk bun run lint:i18n`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/components/bioinfoflow/settings/agent-custom-instructions.tsx frontend/components/bioinfoflow/settings/settings-page-client.tsx frontend/messages/en.json frontend/messages/zh-CN.json frontend/tests/unit/components/agent-custom-instructions.test.tsx frontend/tests/unit/components/settings-page.test.tsx
rtk git commit -m "fix: simplify agent instruction settings"
```

### Task 7: Full verification and review fixes

**Files:**
- Modify: only files required by review findings

- [ ] **Step 1: Run backend verification**

Run from `backend/`:

```bash
rtk uv run alembic upgrade head
rtk uv run pytest
rtk uv run ruff check .
```

Expected: all commands pass.

- [ ] **Step 2: Run frontend verification**

Run from `frontend/`:

```bash
rtk bun run lint
rtk bun run lint:i18n
rtk bun run lint:dead-code
rtk bun run test
```

Expected: all commands pass.

- [ ] **Step 3: Run diff hygiene checks**

```bash
rtk git diff --check
rtk git status --short
```

Expected: no whitespace errors; only intended files are modified.

- [ ] **Step 4: Perform code review**

Review the complete diff for concurrency races, duplicate delivery, transcript
role ordering, cancellation behavior, optimistic-state cleanup, accessibility,
and locale parity. Fix every P0-P2 issue with a new failing regression test
before changing production code.

- [ ] **Step 5: Re-run affected and full verification**

Repeat Steps 1-3 after review fixes.

- [ ] **Step 6: Commit review fixes if needed**

```bash
rtk git add $(rtk git diff --name-only)
rtk git commit -m "fix: address active turn steering review"
```

### Task 8: Rebase, push, and create the PR

**Files:**
- No source files unless the rebase requires conflict resolution

- [ ] **Step 1: Sync remote main**

```bash
rtk git fetch origin --prune
rtk git rebase origin/main
```

Expected: rebase completes without unresolved conflicts.

- [ ] **Step 2: Re-run smoke verification after rebase**

```bash
rtk git diff --check origin/main...HEAD
rtk uv run pytest tests/test_agent_core/test_active_turn_steering.py
rtk bun run test -- frontend/tests/unit/components/agent-workbench.test.tsx frontend/tests/unit/components/agent-custom-instructions.test.tsx
```

Run backend and frontend commands from their respective package directories.

Expected: PASS.

- [ ] **Step 3: Push and create a ready PR**

```bash
rtk git push -u origin codex/steer-active-turn
rtk gh pr create --base main --title "fix: keep active agent conversations continuous" --body-file /tmp/bioinfoflow-active-turn-steering-pr.md
```

The PR body must summarize the steer state machine, the custom-instructions UI
change, TDD coverage, review outcome, and exact verification commands.
