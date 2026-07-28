# Reliable Plan Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Plan/Act selection atomic with new-turn creation, keep Plan strictly read-only, and automatically continue the same turn in Act after plan approval without transient tool-exposure failures.

**Architecture:** Keep mode as session policy and reuse the existing turn claim, action persistence, permission context, and resume worker. The frontend stores only a local next-turn mode intent and sends a mode snapshot with each immediate or queued turn. The backend derives Plan tools from one policy, applies a deterministic command guard, and distinguishes first-call model visibility from persisted-action resume authorization.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy async, pytest, Next.js 16, React 19, TypeScript, Vitest.

---

## File map

- `backend/app/schemas/agent_core.py`: add the optional turn mode contract.
- `backend/app/api/v1/agent.py`: pass turn mode into the service.
- `backend/app/services/agent_core/service.py`: atomically apply mode with the turn claim and fence ordinary active-turn mode PATCH requests.
- `backend/app/services/agent_core/tools/toolsets.py`: derive the canonical Plan surface and stable tool ordering.
- `backend/app/services/agent_core/tools/executor.py`: enforce the Plan command ceiling, resume persisted actions through the callable surface, and return recoverable authorization failures.
- `backend/app/services/agent_core/context/assembler.py`: move the short mode instruction to the end of the shared prompt.
- `frontend/lib/agent-runtime/client.ts`: serialize mode in new-turn requests.
- `frontend/hooks/use-agent-runtime.ts`: maintain the minimal `pendingMode` intent and remove session mode PATCH calls.
- `frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx`: capture mode at submission time, including queued turns.
- `frontend/components/bioinfoflow/agent-runtime/agent-composer.tsx`: disable only mode selection during an active turn.
- Existing backend and frontend test files listed in each task: cover behavior without introducing new test-only abstractions.

### Task 1: Atomically apply mode when creating a turn

**Files:**
- Modify: `backend/app/schemas/agent_core.py`
- Modify: `backend/app/api/v1/agent.py`
- Modify: `backend/app/services/agent_core/service.py`
- Test: `backend/tests/test_api/test_agent_core_api.py`
- Test: `backend/tests/test_agent_core/test_permission_context.py`

- [ ] **Step 1: Write failing API and service tests**

Add tests that create an execution session, POST a turn with `mode: "plan"`, and assert that the accepted turn and refreshed session coexist with `{ "name": "plan" }`. Add the inverse execution case and an omitted-mode case. Assert that `permission_policy_version` increments only when the normalized policy changes.

```python
@pytest.mark.asyncio
async def test_turn_creation_atomically_applies_requested_mode(async_client):
    created = (await async_client.post("/api/v1/agent/sessions")).json()["data"]
    response = await async_client.post(
        f"/api/v1/agent/sessions/{created['id']}/turns",
        json={"input_text": "Inspect first", "mode": "plan"},
    )
    assert response.status_code == 202
    refreshed = (
        await async_client.get(f"/api/v1/agent/sessions/{created['id']}")
    ).json()["data"]
    assert refreshed["toolset_policy"] == {"name": "plan"}
    assert refreshed["permission_policy_version"] == 2
```

- [ ] **Step 2: Run the focused tests and confirm the red state**

Run from `backend/`:

```bash
rtk uv run pytest tests/test_api/test_agent_core_api.py tests/test_agent_core/test_permission_context.py -k "turn_creation_atomically_applies_requested_mode or turn_mode"
```

Expected: failure because `AgentTurnCreate` and `create_turn_record()` do not accept `mode`.

- [ ] **Step 3: Implement the minimal mode plumbing**

Use the existing literal and policies; do not add a turn column.

```python
class AgentTurnCreate(BaseModel):
    input_text: str
    mode: AgentMode | None = None
    # existing fields remain unchanged
```

Pass `payload.mode` through `create_turn()` and `create_turn_record()`. Before resolving input, normalize the requested policy and merge it into the existing atomic session update:

```python
if mode is not None:
    requested_policy = (
        EXECUTION_TOOLSET_POLICY if mode == "execution" else PLAN_TOOLSET_POLICY
    )
    if session.toolset_policy != requested_policy:
        session_updates["toolset_policy"] = requested_policy
        increment_policy_version = True
```

- [ ] **Step 4: Run the focused tests and confirm green**

Run the command from Step 2. Expected: all selected tests pass.

- [ ] **Step 5: Commit the atomic turn contract**

```bash
rtk git add backend/app/schemas/agent_core.py backend/app/api/v1/agent.py backend/app/services/agent_core/service.py backend/tests/test_api/test_agent_core_api.py backend/tests/test_agent_core/test_permission_context.py
rtk git commit -m "fix: apply agent mode with turn creation"
```

### Task 2: Prevent ordinary mode changes during an active turn

**Files:**
- Modify: `backend/app/services/agent_core/service.py`
- Modify: `backend/app/repositories/agent_core_repo.py`
- Test: `backend/tests/test_api/test_agent_core_api.py`
- Test: `backend/tests/test_agent_core/test_runtime_target_and_resume_guards.py`
- Test: `backend/tests/test_agent_core/test_harness_invariants.py`

- [ ] **Step 1: Replace the old mid-turn mode-switch expectation with a failing fence test**

Create a running turn, PATCH `{ "mode": "plan" }`, and expect HTTP 409 while non-mode metadata updates retain their existing behavior. Rewrite `test_loop_refreshes_permission_context_before_each_model_iteration` so it no longer relies on an illegal execution-to-plan switch during a turn.

```python
response = await async_client.patch(
    f"/api/v1/agent/sessions/{session_id}",
    json={"mode": "plan"},
)
assert response.status_code == 409
assert "active turn" in response.json()["error"]["message"].lower()
```

- [ ] **Step 2: Run the focused tests and confirm the red state**

```bash
rtk uv run pytest tests/test_api/test_agent_core_api.py tests/test_agent_core/test_harness_invariants.py -k "active_turn and mode"
```

Expected: PATCH currently succeeds.

- [ ] **Step 3: Add one service-level guard**

Generalize the repository's existing target/scope mutability fence to a `require_no_active_turn` option, and use it for effective mode changes as well as target/scope changes. Keep the internal `exit_plan_mode` approval transaction unchanged because it does not call this public update path.

```python
require_no_active_turn = target_changed or scope_changed or mode_changed
updated = await self.session_repo.update_with_policy_version(
    session,
    require_no_active_turn=require_no_active_turn,
    **update_data,
)
```

Return the existing conflict error when the guarded update loses its compare-and-set. Do not add a second active-turn query or state machine.

- [ ] **Step 4: Run the focused tests and confirm green**

Run the Step 2 command. Expected: selected tests pass.

- [ ] **Step 5: Commit the active-turn fence**

```bash
rtk git add backend/app/services/agent_core/service.py backend/app/repositories/agent_core_repo.py backend/tests/test_api/test_agent_core_api.py backend/tests/test_agent_core/test_harness_invariants.py
rtk git commit -m "fix: fence mode updates during active turns"
```

### Task 3: Derive one safe Plan tool surface

**Files:**
- Modify: `backend/app/services/agent_core/tools/toolsets.py`
- Modify: `backend/app/services/agent_core/tools/executor.py`
- Test: `backend/tests/test_agent_core/test_toolsets.py`
- Test: `backend/tests/test_agent_core/test_execution_scope.py`
- Test: `backend/tests/test_agent_core/test_command_risk.py`
- Test: `backend/tests/test_agent_core/test_permission_context.py`
- Test: `backend/tests/test_agent_core/test_tools/test_execution_shell.py`

- [ ] **Step 1: Write failing surface and command-ceiling tests**

Assert that Plan exposes every registered non-hidden static read tool with no write scope, plus root `ask_user` and `exit_plan_mode`; explicitly assert that `todo_write`, edit/write tools, lifecycle mutations, and collaboration mutations are absent. Assert `bash` is visible for an allowed local target and `remote.exec` for an allowed remote target, but execution accepts only risk assessments with read-only effects and no explicit approval requirement.

```python
plan = exposure.exposed_names(policy=PLAN_TOOLSET_POLICY)
read_only = {
    spec.name
    for spec in registry.list_specs()
    if spec.risk_level == "read" and not spec.write_scope
}
assert read_only - MODEL_HIDDEN_TOOL_NAMES <= plan
assert {"ask_user", "exit_plan_mode"} <= plan
assert {"todo_write", "write", "edit", "runs.submit"}.isdisjoint(plan)
```

Use commands such as `pwd`, `git status --short`, and `cat file` for allowed cases; use output redirection, file mutation, network/mutation commands, and an unknown command for denied cases. A denied Plan command must not create a waiting approval.

- [ ] **Step 2: Run the focused tests and confirm the red state**

```bash
rtk uv run pytest tests/test_agent_core/test_toolsets.py tests/test_agent_core/test_execution_scope.py tests/test_agent_core/test_permission_context.py tests/test_agent_core/test_tools/test_execution_shell.py -k "plan"
```

Expected: Plan remains a handwritten small allowlist and command tools are unavailable or approval-gated.

- [ ] **Step 3: Implement the canonical surface and Plan command guard**

Replace `_PLAN_TOOLS` as a product allowlist with one helper derived from specs:

```python
def _plan_static_names(specs: Iterable[AgentToolSpec]) -> set[str]:
    return {
        spec.name
        for spec in specs
        if spec.risk_level == "read" and not spec.write_scope
    } | {"ask_user", "exit_plan_mode"}
```

Apply the same helper to model-visible and host-callable Plan surfaces, then run existing target/scope and hidden-tool filters. Add `bash` or `remote.exec` to the visible surface only when the resolved target/scope supports it.

In the executor, after producing the concrete command risk but before general approval routing, enforce:

```python
def _plan_command_allowed(risk: RiskAssessment) -> bool:
    return (
        risk.level in {"read", "act_low"}
        and risk.effects == ["read"]
        and not risk.requires_explicit_approval
        and not risk.hard_blocked
    )
```

If the session policy is Plan and the dynamic tool is `bash` or `remote.exec`, fail the action directly when this predicate is false. Do not let user approval widen Plan.

- [ ] **Step 4: Run the focused tests and confirm green**

Run the Step 2 command. Expected: selected tests pass.

- [ ] **Step 5: Commit the unified Plan policy**

```bash
rtk git add backend/app/services/agent_core/tools/toolsets.py backend/app/services/agent_core/tools/executor.py backend/tests/test_agent_core/test_toolsets.py backend/tests/test_agent_core/test_execution_scope.py backend/tests/test_agent_core/test_permission_context.py backend/tests/test_agent_core/test_tools/test_execution_shell.py
rtk git commit -m "fix: derive safe plan mode tools"
```

### Task 4: Resume plan decisions through the callable surface

**Files:**
- Modify: `backend/app/services/agent_core/tools/executor.py`
- Test: `backend/tests/test_agent_core/test_approval_idempotency.py`
- Test: `backend/tests/test_agent_core/test_harness_invariants.py`
- Test: `backend/tests/test_agent_core/test_tools/test_interaction.py`

- [ ] **Step 1: Write a failing full-loop approval test**

Drive a Plan turn through model tool call `exit_plan_mode`, waiting approval, approval, resume, and a second model invocation. Assert the approval transaction changes the session to execution before enqueueing resume, the persisted action completes even though Act does not advertise `exit_plan_mode`, the second invocation contains Act tools, and the same turn completes.

```python
assert waiting.status == AgentTurnStatus.WAITING_APPROVAL
await service.decide_action(..., decision="approve")
resumed = await runtime.resume_turn(str(turn.id))
assert resumed.status == AgentTurnStatus.COMPLETED
assert gateway.invocations[1].tools_by_name["write"]
```

Add the matching rejection path: policy remains Plan, the same turn resumes with the decision result, and the next invocation still has Plan tools. Retain the existing duplicate-decision idempotency assertions for both decisions.

- [ ] **Step 2: Run the focused tests and confirm the red state**

```bash
rtk uv run pytest tests/test_agent_core/test_harness_invariants.py tests/test_agent_core/test_tools/test_interaction.py -k "plan_approval_switches or exit_plan_mode"
```

Expected: resumed `exit_plan_mode` is rejected against the new Act-visible surface.

- [ ] **Step 3: Separate first-call visibility from persisted-action resume checks**

Keep `execute(... require_model_exposure=True)` as the only model-visible gate before action persistence. In `_run_action()`, always decide against `callable_names()`:

```python
exposure = self.exposure.decide(
    tool_name=tool.spec.name,
    policy=snapshot["toolset_policy"],
    role=permission_context.role,
    execution_target=snapshot["execution_target"],
    execution_scope=snapshot.get("execution_scope"),
    model_visible=False,
)
```

Retain fresh target, scope, risk, ownership, and permission checks. A persisted action is trusted only as proof that the original model-visible gate already passed, not as permission to bypass current authorization.

- [ ] **Step 4: Run the focused tests and confirm green**

Run the Step 2 command. Expected: the full loop and stale-call tests pass.

- [ ] **Step 5: Commit reliable approval resume behavior**

```bash
rtk git add backend/app/services/agent_core/tools/executor.py backend/tests/test_agent_core/test_harness_invariants.py backend/tests/test_agent_core/test_tools/test_interaction.py
rtk git commit -m "fix: resume approved plan actions safely"
```

### Task 5: Recover only genuinely stale offered tool calls

**Files:**
- Modify: `backend/app/services/agent_core/core/loop.py`
- Modify: `backend/app/services/agent_core/tools/batches.py`
- Test: `backend/tests/test_agent_core/test_runtime_reliability.py`
- Test: `backend/tests/test_agent_core/test_tool_call_batches.py`

- [ ] **Step 1: Write failing recoverable-versus-hallucinated tests**

Add `test_runtime_recovers_when_previously_offered_tool_becomes_unexposed`, keep or rename the existing never-offered tool test, and add `test_recoverable_stale_exposure_persists_matching_tool_result_atomically`.

The recoverable test must capture the exact tool names offered in an invocation, change external authorization before dispatch, and verify a failed continuable tool result is added before the next model iteration. The fail-closed test must call a registered tool absent from the invocation's offered set and retain terminal `tool_not_exposed` behavior.

```python
assert stale_call_name in invocation_tool_names
assert persisted_result.error["continuable"] is True
assert next_model_invocation_count == 2

assert hallucinated_call_name not in invocation_tool_names
assert completed.status == AgentTurnStatus.FAILED
```

- [ ] **Step 2: Run the focused tests and confirm the red state**

```bash
rtk uv run pytest tests/test_agent_core/test_runtime_reliability.py -k "offered_tool_becomes_unexposed or never_offered" -q
rtk uv run pytest tests/test_agent_core/test_tool_call_batches.py -k "recoverable_stale_exposure" -q
```

Expected: stale and never-offered calls currently share one terminal preparation-failure path.

- [ ] **Step 3: Preserve the invocation's offered set through dispatch**

In the loop, capture the canonical exposed names used to build each model invocation and pass that immutable set into tool-call preparation. When current exposure denies a call:

```python
recoverable_stale_exposure = tool_name in offered_tool_names
```

If true, reuse the existing batch repair path to persist a matching failed tool result with `category="tool_result"` and `continuable=True`, then allow the batch barrier and next model iteration to proceed. If false, keep the existing terminal `tool_not_exposed` failure. Do not make all registered-but-unexposed tools recoverable.

- [ ] **Step 4: Run the focused tests and confirm green**

Run both commands from Step 2. Expected: stale offered calls recover and never-offered calls still fail closed.

- [ ] **Step 5: Commit bounded stale-exposure recovery**

```bash
rtk git add backend/app/services/agent_core/core/loop.py backend/app/services/agent_core/tools/batches.py backend/tests/test_agent_core/test_runtime_reliability.py backend/tests/test_agent_core/test_tool_call_batches.py
rtk git commit -m "fix: recover stale offered tool calls"
```

### Task 6: Preserve the prompt and tool cache prefix

**Files:**
- Modify: `backend/app/services/agent_core/context/assembler.py`
- Modify: `backend/app/services/agent_core/tools/toolsets.py`
- Test: `backend/tests/test_agent_core/test_harness_invariants.py`
- Test: `backend/tests/test_agent_core/test_toolsets.py`

- [ ] **Step 1: Write failing prefix tests**

Build otherwise-identical Plan and Act contexts. Assert their instruction strings share the complete prefix before a final `## Mode` section. Build both tool definition lists and assert common tools have identical schemas and relative order, with mode-only tools appended after the common tier.

```python
plan_prefix, plan_mode = plan_instructions.rsplit("\n\n## Mode\n", 1)
act_prefix, act_mode = act_instructions.rsplit("\n\n## Mode\n", 1)
assert plan_prefix == act_prefix
assert plan_mode != act_mode
```

- [ ] **Step 2: Run the focused tests and confirm the red state**

```bash
rtk uv run pytest tests/test_agent_core/test_harness_invariants.py tests/test_agent_core/test_toolsets.py -k "instructions_share_prefix or shared_tools_as_identical_prefix"
```

Expected: mode text interrupts the environment and alphabetical sorting interleaves Act-only tools.

- [ ] **Step 3: Append only a short mode suffix and tier tool ordering**

Remove both `Toolset policy` and `PLAN MODE` from `_environment_context()`. Append them together as the only final mode-specific section in `_instructions()`:

```python
system_sections.append(
    "## Mode\n"
    + (
        "Toolset policy: plan. Investigate with read-only tools, then call "
        "exit_plan_mode with a concrete plan."
        if toolset == "plan"
        else "Toolset policy: execution. Execute the requested work using the "
        "available tools and permission policy."
    )
)
```

In `exposed_specs()`, order a deterministic shared tier first and append deterministic mode-only names. Do not add cache keys or provider-specific cache code.

- [ ] **Step 4: Run the focused tests and confirm green**

Run the Step 2 command. Expected: selected tests pass.

- [ ] **Step 5: Commit cache-stable context construction**

```bash
rtk git add backend/app/services/agent_core/context/assembler.py backend/app/services/agent_core/tools/toolsets.py backend/tests/test_agent_core/test_harness_invariants.py backend/tests/test_agent_core/test_toolsets.py
rtk git commit -m "perf: stabilize agent mode prompt prefix"
```

### Task 7: Send next-turn mode without a session PATCH

**Files:**
- Modify: `frontend/lib/agent-runtime/client.ts`
- Modify: `frontend/hooks/use-agent-runtime.ts`
- Test: `frontend/tests/unit/lib/agent-runtime/client.test.ts`
- Test: `frontend/tests/unit/hooks/use-agent-runtime.test.tsx`

- [ ] **Step 1: Write failing client and hook tests**

Add `serializes the selected agent mode when creating a turn`, `sends the selected next-turn mode without patching the session`, `keeps a pending mode across a stale session refresh`, `clears the pending mode when refreshed session state confirms it`, and `refreshes session mode when an action decision is recorded`.

```ts
act(() => result.current.setMode("plan"))
await act(() => result.current.send("Inspect this"))
expect(mocks.updateAgentRuntimeSessionMode).not.toHaveBeenCalled()
expect(mocks.createAgentRuntimeTurn).toHaveBeenCalledWith(
  expect.objectContaining({ mode: "plan" }),
)
```

- [ ] **Step 2: Run the focused tests and confirm the red state**

Run from `frontend/`:

```bash
rtk bun run test -- tests/unit/lib/agent-runtime/client.test.ts tests/unit/hooks/use-agent-runtime.test.tsx -t "selected agent mode|next-turn mode|pending mode|action decision"
```

Expected: turn requests omit mode and `setMode()` calls PATCH.

- [ ] **Step 3: Implement the minimal pending intent**

Add `mode?: AgentMode` to `createAgentRuntimeTurn()` and serialize it. In the hook, replace `draftMode` as session truth with:

```ts
const [pendingMode, setPendingMode] = useState<AgentMode | null>(null)
const serverMode: AgentMode =
  activeSession?.toolset_policy?.name === "plan" ? "plan" : "execution"
const mode = pendingMode ?? serverMode
const setMode = useCallback((next: AgentMode) => setPendingMode(next), [])
```

Pass a captured mode into `send()` and `createAgentRuntimeTurn()`. Clear pending mode when switching sessions or when refreshed server mode equals it. Preserve pending mode across a stale refresh. Keep new-session creation consistent with the captured mode. Remove the `updateAgentRuntimeSessionMode` import and call. Treat `action.decision_recorded` as a state-refresh event.

- [ ] **Step 4: Run the focused tests and confirm green**

Run the Step 2 command. Expected: selected tests pass.

- [ ] **Step 5: Commit next-turn mode intent**

```bash
rtk git add frontend/lib/agent-runtime/client.ts frontend/hooks/use-agent-runtime.ts frontend/tests/unit/lib/agent-runtime/client.test.ts frontend/tests/unit/hooks/use-agent-runtime.test.tsx
rtk git commit -m "fix: send agent mode with each turn"
```

### Task 8: Snapshot queued mode and disable only mode controls

**Files:**
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-composer.tsx`
- Test: `frontend/tests/unit/components/agent-workbench.test.tsx`
- Test: `frontend/tests/unit/components/agent-composer.test.tsx`

- [ ] **Step 1: Write failing queue and control tests**

Add `sends the currently selected mode with an immediate turn`, `keeps the selected mode snapshot when a queued turn is released`, `does not switch modes with Shift+Tab when mode selection is disabled`, and `disables only the mode control while a turn is active`.

```ts
expect(screen.getByTestId("agent-mode-chip")).toBeDisabled()
expect(screen.getByRole("textbox")).toBeEnabled()
fireEvent.keyDown(screen.getByRole("textbox"), { key: "Tab", shiftKey: true })
expect(onModeChange).not.toHaveBeenCalled()
```

For the queue test, submit while mode is Plan, rerender the runtime as Act before releasing the queue, and assert the eventual `send()` receives Plan.

- [ ] **Step 2: Run the focused tests and confirm the red state**

```bash
rtk bun run test -- tests/unit/components/agent-composer.test.tsx tests/unit/components/agent-workbench.test.tsx -t "selected mode|mode snapshot|mode selection is disabled|disables only the mode control"
```

Expected: queued submissions reread current mode and active turns leave the mode chip enabled.

- [ ] **Step 3: Implement explicit mode snapshots and a dedicated disable prop**

Add `mode: AgentMode` to `PendingSubmission`. Add a mode argument to `sendTurn()` and pass it into `send(..., { mode })`. Capture `agentMode` in immediate, queued, and steer-fallback submissions; release queued submissions using `next.mode`.

Add `modeDisabled?: boolean` to `AgentComposerProps`, use `disabled || modeDisabled` on the mode trigger, and require `!modeDisabled` in the Shift+Tab branch. Pass `modeDisabled={hasActiveTurn}` from the workbench. Do not disable the textarea or submission behavior.

- [ ] **Step 4: Run the focused tests and confirm green**

Run the Step 2 command. Expected: selected tests pass.

- [ ] **Step 5: Commit the seamless mode UX**

```bash
rtk git add frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx frontend/components/bioinfoflow/agent-runtime/agent-composer.tsx frontend/tests/unit/components/agent-workbench.test.tsx frontend/tests/unit/components/agent-composer.test.tsx
rtk git commit -m "fix: preserve mode across queued turns"
```

### Task 9: Integration verification, independent review, and PR delivery

**Files:**
- Modify only files required by valid review findings.

- [ ] **Step 1: Run focused backend and frontend suites**

```bash
rtk uv run pytest tests/test_api/test_agent_core_api.py tests/test_agent_core/test_permission_context.py tests/test_agent_core/test_runtime_target_and_resume_guards.py tests/test_agent_core/test_harness_invariants.py tests/test_agent_core/test_toolsets.py tests/test_agent_core/test_execution_scope.py tests/test_agent_core/test_tools/test_execution_shell.py tests/test_agent_core/test_runtime_reliability.py tests/test_agent_core/test_tool_call_batches.py tests/test_agent_core/test_tools/test_interaction.py
rtk bun run test -- tests/unit/lib/agent-runtime/client.test.ts tests/unit/hooks/use-agent-runtime.test.tsx tests/unit/components/agent-composer.test.tsx tests/unit/components/agent-workbench.test.tsx
```

Expected: all selected tests pass.

- [ ] **Step 2: Run repository-required verification**

From `backend/`:

```bash
rtk uv run pytest
rtk uv run ruff check .
```

From `frontend/`:

```bash
rtk bun run lint
rtk bun run lint:i18n
rtk bun run test
```

From the repository root:

```bash
rtk git diff --check
```

Expected: every command passes. Record any environment-only command that cannot run.

- [ ] **Step 3: Request two-stage independent review**

Dispatch a spec-compliance review against both plan documents, then a code-quality review. Fix only evidenced correctness, regression, or maintainability findings. Re-run the narrow tests for each correction and then the verification matrix.

- [ ] **Step 4: Synchronize with the remote default branch**

```bash
rtk git fetch origin --prune
rtk git rebase origin/main
```

Expected: rebase succeeds. If conflicts occur, preserve the approved design and unrelated upstream changes, then repeat all verification.

- [ ] **Step 5: Push, create the PR, and enable rebase automerge**

```bash
rtk git push -u origin codex/fix-plan-mode
rtk gh pr create --base main --head codex/fix-plan-mode --title "fix: make plan mode transition reliable" --body-file /tmp/plan-mode-pr.md
rtk gh pr merge --auto --rebase
```

The PR body must summarize the atomic turn-mode contract, safe Plan surface, automatic approval resume, cache-prefix preservation, and exact verification results. Confirm the PR reports rebase automerge enabled.
