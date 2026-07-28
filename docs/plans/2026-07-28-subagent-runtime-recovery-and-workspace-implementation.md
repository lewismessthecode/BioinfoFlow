# Subagent Runtime Recovery and Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make asynchronous child spawning terminally consistent with the parent turn, scope regenerate progress to the retried response, and deliver a compact Codex-style child-agent list/detail workspace.

**Architecture:** `SpawnAgentTool` runs the complete child-spawn domain transaction in a short-lived database session, so collaboration commits and rollbacks cannot expire executor-owned ORM state. Frontend lifecycle events remain the single source of child state; a pure view-model feeds one Agents sidecar tab, and the environment card retains only counts plus an entry action.

**Tech Stack:** Python 3.13, SQLAlchemy async, Agent Core loop/tool executor, pytest, Next.js 16, React 19, TypeScript, next-intl, Tailwind CSS, Vitest, Testing Library.

**Command working directories:** Run backend commands from `backend/`, frontend commands from `frontend/`, and Git/repository checks from the repository root. Prefix every command with `rtk`.

---

## File Structure

### Backend files modified

- `backend/app/services/agent_core/tools/collaboration/tools.py` — run the entire spawn domain transaction in an isolated `AsyncSession`.
- `backend/tests/test_agent_core/test_model_runtime_integration.py` — reproduce two model-issued spawn calls and assert parent action/batch/turn completion.
- `backend/tests/test_agent_core/test_collaboration.py` — prove duplicate/error rollbacks terminalize the parent action without `MissingGreenlet`.

### Frontend files created

- `frontend/components/bioinfoflow/agent-runtime/agent-workspace.tsx` — responsive list/detail child-agent workspace with local selection and keyboard navigation.
- `frontend/lib/agent-runtime/agent-workspace.ts` — pure grouping, stable ordering, count, display-name, and preview helpers.
- `frontend/tests/unit/components/agent-workspace.test.tsx` — list/detail, selection, keyboard, responsive, overflow, and terminal-state coverage.
- `frontend/tests/unit/lib/agent-runtime/agent-workspace.test.ts` — pure view-model coverage.

### Frontend files modified

- `frontend/lib/agent-runtime/types.ts` — stable first/last lifecycle sequence and timestamps.
- `frontend/lib/agent-runtime/agent-tree.ts` — preserve first-seen metadata without mixing presentation sorting into the reducer.
- `frontend/lib/agent-runtime/index.ts` — export workspace helpers.
- `frontend/lib/agent-runtime/segments.ts` — terminalize stale activity for completed turns.
- `frontend/components/bioinfoflow/agent-runtime/agent-transcript.tsx` — separate retry progress from global response-action disablement.
- `frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx` — own `retryingTurnId`, open the Agents tab, and pass responsive workspace state.
- `frontend/components/bioinfoflow/agent-runtime/agent-tabbed-panel.tsx` — add the Agents tab and render the workspace with full-height overflow boundaries.
- `frontend/components/bioinfoflow/agent-runtime/agent-workspace-tabs.tsx` — add the desktop Agents tab to the canonical tab order.
- `frontend/components/bioinfoflow/agent-runtime/agent-environment-card.tsx` — replace the duplicate tree/activity area with counts and an Agents entry.
- `frontend/components/bioinfoflow/agent-runtime/agent-tree.tsx` — remove after all callers migrate.
- `frontend/messages/en.json` and `frontend/messages/zh-CN.json` — synchronized labels and states.
- `frontend/tests/unit/components/agent-transcript.test.tsx`
- `frontend/tests/unit/components/agent-workbench.test.tsx`
- `frontend/tests/unit/components/agent-runtime-panel.test.tsx`
- `frontend/tests/unit/components/agent-runtime-cards.test.tsx`
- `frontend/tests/unit/components/agent-workspace-tabs.test.tsx`
- `frontend/tests/unit/lib/agent-runtime/agent-tree.test.ts`
- `frontend/tests/unit/lib/agent-runtime/timeline.test.ts`

---

### Task 1: Reproduce the parent spawn action crash

**Files:**

- Modify: `backend/tests/test_agent_core/test_model_runtime_integration.py`
- Modify: `backend/tests/test_agent_core/test_collaboration.py`

- [ ] **Step 1: Write the failing two-spawn runtime regression**

Add a fake gateway sequence that first emits two `spawn_agent` calls and then a
final answer:

```python
@pytest.mark.asyncio
async def test_two_spawn_actions_finish_parent_batch_and_turn(
    db_session,
    monkeypatch,
) -> None:
    root, turn = await _turn(db_session, input_text="Delegate two checks.")
    gateway = FakeModelGateway(
        (
            ToolCallDelta(
                index=0,
                call_id="spawn-reader",
                name="spawn_agent",
                arguments_delta=json.dumps(
                    {"task_name": "reader", "message": "Inspect README."}
                ),
            ),
            ToolCallDelta(
                index=1,
                call_id="spawn-config",
                name="spawn_agent",
                arguments_delta=json.dumps(
                    {"task_name": "config", "message": "Inspect pyproject.toml."}
                ),
            ),
            CompletionMetadata(response_id="spawn-batch", finish_reason="tool_calls"),
        ),
        (
            TextDelta(text="Both child tasks were started."),
            CompletionMetadata(response_id="parent-final", finish_reason="stop"),
        ),
    )
    queued: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.enqueue_turn_run",
        lambda turn_id, session_id=None: queued.append((turn_id, session_id)),
    )

    result = await AgentLoopController(db_session, model_gateway=gateway).run_turn(
        turn_id=str(turn.id),
        target=_target(),
        capabilities=RuntimeCapabilities(supports_tools=True),
        strategy=RuntimeStrategy(allow_tools=True),
    )

    assert result.termination_reason == "assistant_final"
    assert result.final_text == "Both child tasks were started."
    assert len(queued) == 2
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    assert [action.status for action in actions] == [
        AgentActionStatus.COMPLETED,
        AgentActionStatus.COMPLETED,
    ]
    batches = await AgentToolCallBatchRepository(db_session).list_for_turn(str(turn.id))
    assert [batch.status for batch in batches] == [AgentToolCallBatchStatus.COMPLETED]
    fresh_turn = await AgentTurnRepository(db_session).get_fresh(str(turn.id))
    assert fresh_turn.status == AgentTurnStatus.COMPLETED
```

Also assert the public event order contains both `action.completed` events
before `turn.completed`, and that no child turn needs to run for the parent to
finish.

- [ ] **Step 2: Write the failing duplicate-spawn rollback regression**

Use the real tool executor twice so the second spawn reaches the collaboration
service's duplicate-name rollback path:

```python
@pytest.mark.asyncio
async def test_duplicate_spawn_agent_tool_fails_action_without_missing_greenlet(
    db_session,
    monkeypatch,
) -> None:
    root, turn = await _create_parent_turn(db_session)
    monkeypatch.setattr(
        "app.services.agent_core.collaboration.service.enqueue_turn_run",
        lambda *_: None,
    )
    executor = AgentToolExecutor(db_session, build_default_tool_registry())
    context = AgentToolContext(
        db=db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        session_id=str(root.id),
        turn_id=str(turn.id),
    )

    first = await _execute_spawn_action(
        executor,
        context=context,
        task_name="reader",
        tool_call_id="spawn-reader-1",
    )
    second = await _execute_spawn_action(
        executor,
        context=context,
        task_name="reader",
        tool_call_id="spawn-reader-2",
    )

    assert first.status == AgentActionStatus.COMPLETED
    assert second.status == AgentActionStatus.FAILED
    assert second.error["message"] == "agent_name_reserved"
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    assert [action.status for action in actions] == [
        AgentActionStatus.COMPLETED,
        AgentActionStatus.FAILED,
    ]
```

- [ ] **Step 3: Run the focused tests and confirm failure**

Run:

```bash
rtk uv run pytest tests/test_agent_core/test_model_runtime_integration.py::test_two_spawn_actions_finish_parent_batch_and_turn tests/test_agent_core/test_collaboration.py::test_duplicate_spawn_agent_tool_fails_action_without_missing_greenlet -q
```

Expected: fail with `MissingGreenlet`, a non-terminal first action, or only one
queued child.

- [ ] **Step 4: Commit the red tests**

```bash
rtk git add backend/tests/test_agent_core/test_model_runtime_integration.py backend/tests/test_agent_core/test_collaboration.py
rtk git commit -m "test: reproduce stalled parent spawn batch"
```

---

### Task 2: Isolate the complete spawn domain transaction

**Files:**

- Modify: `backend/app/services/agent_core/tools/collaboration/tools.py`

- [ ] **Step 1: Give `SpawnAgentTool` its own session boundary**

Add:

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
```

Run the full service operation in the isolated session:

```python
async def run(self, input: dict, context: AgentToolContext) -> dict:
    from app.services.agent_core.collaboration.service import (
        AgentCollaborationService,
    )

    session_factory = async_sessionmaker(
        bind=context.db.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    async with session_factory() as spawn_session:
        result = await AgentCollaborationService(spawn_session).spawn_agent(
            parent_session_id=context.session_id,
            parent_turn_id=context.turn_id,
            task_name=input.get("task_name"),
            message=input.get("message"),
            fork_turns=input.get("fork_turns", "all"),
            model=input.get("model"),
            reasoning_effort=input.get("reasoning_effort"),
        )
    return asdict(result)
```

Do not change the collaboration service's domain commits/rollbacks and do not
catch or suppress `MissingGreenlet` in the generic executor.

- [ ] **Step 2: Run the red tests until green**

```bash
rtk uv run pytest tests/test_agent_core/test_model_runtime_integration.py::test_two_spawn_actions_finish_parent_batch_and_turn tests/test_agent_core/test_collaboration.py::test_duplicate_spawn_agent_tool_fails_action_without_missing_greenlet -q
```

Expected: `2 passed`.

- [ ] **Step 3: Run collaboration and batch regression suites**

```bash
rtk uv run pytest tests/test_agent_core/test_collaboration.py tests/test_agent_core/test_tool_call_batches.py tests/test_agent_core/test_model_runtime_integration.py -q
rtk uv run ruff check app/services/agent_core/tools/collaboration/tools.py tests/test_agent_core/test_collaboration.py tests/test_agent_core/test_model_runtime_integration.py
```

Expected: all pass.

- [ ] **Step 4: Commit the runtime fix**

```bash
rtk git add backend/app/services/agent_core/tools/collaboration/tools.py backend/tests/test_agent_core/test_collaboration.py backend/tests/test_agent_core/test_model_runtime_integration.py
rtk git commit -m "fix: isolate subagent spawn transactions"
```

---

### Task 3: Scope retry progress and terminalize stale completed activity

**Files:**

- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-transcript.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx`
- Modify: `frontend/lib/agent-runtime/segments.ts`
- Modify: `frontend/tests/unit/components/agent-transcript.test.tsx`
- Modify: `frontend/tests/unit/components/agent-workbench.test.tsx`
- Modify: `frontend/tests/unit/lib/agent-runtime/timeline.test.ts`

- [ ] **Step 1: Write failing retry-state tests**

Render two completed turns and pass the first turn as retrying:

```tsx
render(
  <AgentTranscript
    timeline={[completedEntry("turn-1"), completedEntry("turn-2")]}
    onRetryTurn={onRetryTurn}
    retryingTurnId="turn-1"
    responseActionsDisabled
  />,
)

const actions = screen.getAllByTestId("assistant-response-actions")
expect(within(actions[0]).getByRole("button", { name: "Regenerating response" }))
  .toHaveAttribute("aria-busy", "true")
expect(within(actions[1]).getByRole("button", { name: "Retry response" }))
  .toHaveAttribute("aria-busy", "false")
```

Add a workbench test proving failed submission clears `retryingTurnId` and a
second click cannot enqueue a duplicate retry.

- [ ] **Step 2: Write the stale completed-activity regression**

```ts
const timeline = buildAgentRuntimeTimeline(
  [turn({ id: "turn-1", status: "completed" })],
  [
    event("assistant.tool_call.completed", 1, { call_id: "spawn-1", name: "spawn_agent" }),
    event("action.started", 2, {
      action_id: "action-1",
      tool_call_id: "spawn-1",
      name: "spawn_agent",
    }),
  ],
)

expect(activityGroups(timeline[0]).map((group) => group.status)).toEqual([
  "completed",
])
```

- [ ] **Step 3: Run tests and confirm failure**

```bash
rtk bun run test tests/unit/components/agent-transcript.test.tsx tests/unit/components/agent-workbench.test.tsx tests/unit/lib/agent-runtime/timeline.test.ts
```

Expected: retry busy applies to both responses and completed activity remains
running.

- [ ] **Step 4: Split retry progress from disablement**

Change transcript props to:

```ts
retryingTurnId?: string | null
responseActionsDisabled?: boolean
```

For each response:

```tsx
const retrying = retryingTurnId === entry.turn.id
<ResponseActionBar
  busy={retrying}
  disabled={responseActionsDisabled || retrying}
  {...otherProps}
/>
```

In the workbench:

```ts
const [retryingTurnId, setRetryingTurnId] = useState<string | null>(null)

const retryTurn = useCallback(async (turn: AgentRuntimeTurn) => {
  if (retryingTurnId) return
  setRetryingTurnId(turn.id)
  try {
    await submitRetriedTurn(turn)
  } finally {
    setRetryingTurnId(null)
  }
}, [retryingTurnId, submitRetriedTurn])
```

Pass `responseActionsDisabled={hasActiveTurn}` without using it to select the
spinner.

- [ ] **Step 5: Terminalize stale activity for all terminal turns**

```ts
function finalizeToolActivities(turn: AgentRuntimeTurn, activities: AgentRuntimeToolActivity[]) {
  const terminalStatus =
    turn.status === "completed"
      ? "completed"
      : turn.status === "failed"
        ? "failed"
        : turn.status === "cancelled"
          ? "cancelled"
          : null
  if (!terminalStatus) return activities
  return activities.map((activity) =>
    ["building", "requested", "waiting", "running"].includes(activity.status)
      ? { ...activity, status: terminalStatus }
      : activity,
  )
}
```

- [ ] **Step 6: Run focused tests and commit**

```bash
rtk bun run test tests/unit/components/agent-transcript.test.tsx tests/unit/components/agent-workbench.test.tsx tests/unit/lib/agent-runtime/timeline.test.ts
rtk git add frontend/components/bioinfoflow/agent-runtime/agent-transcript.tsx frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx frontend/lib/agent-runtime/segments.ts frontend/tests/unit/components/agent-transcript.test.tsx frontend/tests/unit/components/agent-workbench.test.tsx frontend/tests/unit/lib/agent-runtime/timeline.test.ts
rtk git commit -m "fix: scope agent retry progress"
```

---

### Task 4: Build a stable child-agent workspace model

**Files:**

- Create: `frontend/lib/agent-runtime/agent-workspace.ts`
- Modify: `frontend/lib/agent-runtime/types.ts`
- Modify: `frontend/lib/agent-runtime/agent-tree.ts`
- Modify: `frontend/lib/agent-runtime/index.ts`
- Create: `frontend/tests/unit/lib/agent-runtime/agent-workspace.test.ts`
- Modify: `frontend/tests/unit/lib/agent-runtime/agent-tree.test.ts`

- [ ] **Step 1: Write failing reducer metadata tests**

Assert first-seen order survives later lifecycle updates and a new turn clears
old terminal detail:

```ts
expect(tree[0]).toMatchObject({
  childSessionId: "child-a",
  firstSequence: 2,
  lastSequence: 9,
  createdAt: "2026-07-28T00:00:02Z",
  updatedAt: "2026-07-28T00:00:09Z",
})
```

- [ ] **Step 2: Write failing grouping/count tests**

```ts
const model = buildAgentWorkspaceModel([
  agent("running", { firstSequence: 4 }),
  agent("completed", { firstSequence: 1 }),
  agent("errored", { firstSequence: 3 }),
])

expect(model.counts).toEqual({ total: 3, active: 1, completed: 1, terminal: 2 })
expect(model.active.map((item) => item.childSessionId)).toEqual(["running"])
expect(model.terminal.map((item) => item.childSessionId)).toEqual([
  "completed",
  "errored",
])
```

- [ ] **Step 3: Implement canonical metadata**

Extend `AgentTreeNode`:

```ts
firstSequence: number
lastSequence: number
createdAt: string
updatedAt: string
```

The reducer sets `firstSequence`/`createdAt` only on first observation and updates
`lastSequence`/`updatedAt` for accepted later events. Remove alphabetical sorting
from `reduceAgentTree`; return canonical first-seen order.

- [ ] **Step 4: Implement the pure workspace model**

```ts
export function buildAgentWorkspaceModel(agents: AgentTreeNode[]) {
  const ordered = [...agents].sort(
    (left, right) => left.firstSequence - right.firstSequence,
  )
  const active = ordered.filter((agent) => !isTerminalAgent(agent.status))
  const terminal = ordered.filter((agent) => isTerminalAgent(agent.status))
  return {
    active,
    terminal,
    counts: {
      total: ordered.length,
      active: active.length,
      completed: terminal.filter((agent) => agent.status === "completed").length,
      terminal: terminal.length,
    },
  }
}
```

Add `agentDisplayName`, `agentPreview`, and `isTerminalAgent` as pure helpers.

- [ ] **Step 5: Run tests and commit**

```bash
rtk bun run test tests/unit/lib/agent-runtime/agent-tree.test.ts tests/unit/lib/agent-runtime/agent-workspace.test.ts
rtk git add frontend/lib/agent-runtime/types.ts frontend/lib/agent-runtime/agent-tree.ts frontend/lib/agent-runtime/agent-workspace.ts frontend/lib/agent-runtime/index.ts frontend/tests/unit/lib/agent-runtime/agent-tree.test.ts frontend/tests/unit/lib/agent-runtime/agent-workspace.test.ts
rtk git commit -m "refactor: model agent workspace state"
```

---

### Task 5: Implement the Codex-style Agents list and detail

**Files:**

- Create: `frontend/components/bioinfoflow/agent-runtime/agent-workspace.tsx`
- Create: `frontend/tests/unit/components/agent-workspace.test.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`

- [ ] **Step 1: Write failing component tests**

Cover:

```tsx
render(<AgentWorkspace agents={agents} variant="desktop" />)
expect(screen.getByRole("listbox", { name: "Child agents" })).toBeInTheDocument()
expect(screen.getByRole("region", { name: "Agent details" })).toBeInTheDocument()

fireEvent.click(screen.getByRole("option", { name: /Task4 quality review/ }))
expect(screen.getByRole("option", { name: /Task4 quality review/ }))
  .toHaveAttribute("aria-selected", "true")
expect(screen.getByRole("region", { name: "Agent details" }))
  .toHaveTextContent("child-session-2")
```

Add tests for empty state, completed without final text, full error diagnostics,
model fallback, long text truncation with full `title`, Arrow Up/Down,
Home/End, selection stability after event updates, mobile list-to-detail, Back,
and focus restoration.

Assert selected styling contains `bg-muted/60` and contains no left-border,
inset-shadow, or primary/accent selection class.

- [ ] **Step 2: Implement the component boundary**

```tsx
export function AgentWorkspace({
  agents,
  variant,
}: {
  agents: AgentTreeNode[]
  variant: "desktop" | "mobile"
}) {
  const model = buildAgentWorkspaceModel(agents)
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(
    model.active[0]?.childSessionId ?? model.terminal[0]?.childSessionId ?? null,
  )
  // Reconcile by childSessionId when events update.
  // Desktop renders list and detail; mobile renders one view at a time.
}
```

Rows are real buttons with `role="option"`, `aria-selected`, neutral gray hover,
and selected `bg-muted/60`. Do not add a colored left indicator, border, shadow,
or per-row card chrome.

The list shows only status icon/text, short task name, elapsed/terminal label,
and one-line final/error preview. Model and full identifiers belong in detail.

- [ ] **Step 3: Add synchronized copy**

Add identical key structure to both locale files:

```json
"agentWorkspace": {
  "title": "Child agents",
  "open": "Open child agents",
  "active": "Active",
  "completed": "Completed · {count}",
  "back": "Back to child agents",
  "listLabel": "Child agents",
  "detailLabel": "Agent details",
  "empty": "No child agents",
  "select": "Select an agent",
  "sessionId": "Session",
  "turnId": "Turn",
  "model": "Model",
  "requestedModel": "Requested model",
  "terminationReason": "Termination reason",
  "tokenUsage": "Token usage",
  "noFinalText": "Completed without a final response"
}
```

Use natural Chinese equivalents in `zh-CN.json`.

- [ ] **Step 4: Run focused tests and i18n lint**

```bash
rtk bun run test tests/unit/components/agent-workspace.test.tsx
rtk bun run lint:i18n
```

Expected: pass.

- [ ] **Step 5: Commit the workspace component**

```bash
rtk git add frontend/components/bioinfoflow/agent-runtime/agent-workspace.tsx frontend/tests/unit/components/agent-workspace.test.tsx frontend/messages/en.json frontend/messages/zh-CN.json
rtk git commit -m "feat: add agent workspace detail"
```

---

### Task 6: Integrate Agents into the existing sidecar and environment summary

**Files:**

- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-tabbed-panel.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-workspace-tabs.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-environment-card.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx`
- Delete: `frontend/components/bioinfoflow/agent-runtime/agent-tree.tsx`
- Modify: `frontend/tests/unit/components/agent-runtime-panel.test.tsx`
- Modify: `frontend/tests/unit/components/agent-workspace-tabs.test.tsx`
- Modify: `frontend/tests/unit/components/agent-runtime-cards.test.tsx`
- Modify: `frontend/tests/unit/components/agent-workbench.test.tsx`

- [ ] **Step 1: Write failing tab and environment integration tests**

Assert the tab contract:

```tsx
expect(screen.getByRole("tab", { name: "tabs.agents" })).toHaveAttribute(
  "aria-controls",
  "agent-sidecar-panel-agents",
)
```

Assert the environment card renders only counts and an entry button:

```tsx
expect(screen.getByRole("button", { name: "agentWorkspace.open" }))
  .toHaveTextContent("1 · 1")
expect(screen.queryByText("/root/reader")).not.toBeInTheDocument()
expect(screen.queryByText("README found")).not.toBeInTheDocument()
```

Assert clicking the entry closes the floating environment, opens the sidecar,
and activates `agents` on desktop and mobile.

- [ ] **Step 2: Add `agents` to both tab strips**

```ts
export type AgentTabbedPanelTab = "files" | "preview" | "agents" | "browser"
```

Use one `Bot`/agent icon and the same order in
`agent-tabbed-panel.tsx` and `agent-workspace-tabs.tsx`. Update existing
Arrow/Home/End expectations for four tabs.

- [ ] **Step 3: Render the workspace with correct overflow ownership**

```tsx
{activeTab === "agents" ? (
  <AgentWorkspace
    agents={reduceAgentTree(events)}
    variant={variant === "mobile" ? "mobile" : "desktop"}
  />
) : null}
```

For the agents tab, use `overflow-hidden p-0`; list and detail manage their own
scroll areas. Other tabs retain current padding and behavior.

- [ ] **Step 4: Replace duplicate environment content with a summary entry**

Change the environment card contract:

```ts
type AgentEnvironmentCardProps = {
  // existing props
  onOpenAgents?: () => void
}
```

Render counts from `buildAgentWorkspaceModel(reduceAgentTree(events))` and call
`onOpenAgents`. Remove the full `<AgentTree>` section and exclude collaboration
tools from the generic activity list so the screenshot cannot show both child
lifecycle and duplicate `spawn_agent` rows.

- [ ] **Step 5: Wire the workbench action**

```ts
const openAgentsWorkspace = useCallback(() => {
  setEnvironmentOpen(false)
  setActiveSidecarTab("agents")
  setSidecarOpen(true)
}, [])
```

Pass this callback to `AgentEnvironmentCard` in desktop/mobile render paths.

- [ ] **Step 6: Remove the obsolete card component**

After `rtk rg "AgentTree" frontend` shows no runtime caller, delete
`agent-tree.tsx` and its card-specific tests/imports.

- [ ] **Step 7: Run focused integration tests and commit**

```bash
rtk bun run test tests/unit/components/agent-runtime-panel.test.tsx tests/unit/components/agent-workspace-tabs.test.tsx tests/unit/components/agent-runtime-cards.test.tsx tests/unit/components/agent-workbench.test.tsx tests/unit/components/agent-workspace.test.tsx
rtk bun run lint:i18n
rtk git add frontend/components/bioinfoflow/agent-runtime frontend/tests/unit/components frontend/messages/en.json frontend/messages/zh-CN.json
rtk git commit -m "feat: integrate agent workspace sidecar"
```

---

### Task 7: Verify the full change and complete independent review

**Files:**

- Inspect all modified files.
- Update: `docs/plans/2026-07-28-subagent-runtime-recovery-and-workspace-design.md` only if implementation decisions materially differ.

- [ ] **Step 1: Run full backend verification**

```bash
rtk uv run pytest
rtk uv run ruff check .
```

Expected: all pass.

- [ ] **Step 2: Run full frontend verification**

```bash
rtk bun run lint
rtk bun run lint:i18n
rtk bun run lint:dead-code
rtk bun run test
rtk bun run build
```

Expected: all pass, or record an already-known dead-code baseline with exact
unchanged findings.

- [ ] **Step 3: Run repository checks**

```bash
rtk git diff --check
rtk git status --short
```

Expected: no whitespace errors and only intended files changed.

- [ ] **Step 4: Perform visual verification**

Verify in a real browser at:

- wide desktop: list/detail split;
- narrow desktop: list-to-detail push navigation;
- mobile overlay: list, detail, Back, Escape/focus restoration;
- long task path, long final text, long error, empty final text;
- selected row uses only neutral gray background with no colored left edge.

- [ ] **Step 5: Dispatch independent review**

Review must cover:

- spawn/executor transaction ownership;
- exactly-once terminal action/batch behavior;
- child/parent independence;
- retry-state race and cleanup;
- lifecycle reducer monotonicity;
- keyboard/focus behavior;
- overflow and responsive layout;
- duplicate child/tool information removal.

Address all Critical and Important findings and rerun affected verification.

- [ ] **Step 6: Sync main, push, and open the PR**

```bash
rtk git fetch origin --prune
rtk git rebase origin/main
rtk git push -u origin codex/fix-subagent-runtime-ux
rtk gh pr create --title "fix: recover subagent runtime and workspace" --body-file /tmp/subagent-runtime-pr.md
```

The PR body must include the production evidence, root cause, UX before/after,
test matrix, and the separately excluded GPU probe leak.

- [ ] **Step 7: Rebase-merge after CI and review**

After required checks pass and review is clean:

```bash
rtk gh pr merge --rebase --delete-branch
```

Verify `origin/main` contains the merge result and the feature branch is deleted.

---

## Explicitly Out of Scope

- Nested child spawning.
- New collaboration HTTP actions for send/follow-up/interrupt.
- A second child transcript API.
- GPU probe container cleanup; track this as a separate fix because 631 leaked
  probe containers are operationally important but unrelated to the
  `MissingGreenlet` transaction failure.
