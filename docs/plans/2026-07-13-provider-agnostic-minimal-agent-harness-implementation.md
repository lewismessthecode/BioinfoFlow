# Provider-Agnostic Minimal Agent Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make AgentCore preserve one bounded turn across approvals and provider fallback, keep tool-call transcripts closed, and present a provider-neutral prompt and target-coherent tool/context surface.

**Architecture:** Reuse the existing `AgentTurn` durability fields and current registry/executor/context layers. Add small loop checkpoint helpers, stop at the first approval boundary, and make the current session execution target authoritative. Keep provider-specific features in adapters and avoid new orchestration abstractions. Final concurrency review proved that one nullable session claim is the minimum additional schema needed to serialize the canonical transcript across workers.

**Tech Stack:** Python 3.12, FastAPI service layer, SQLAlchemy async repositories, LiteLLM, pytest, Ruff.

---

## File Map

- Modify `backend/app/services/agent_core/core/budget.py`: restore an iteration budget from durable turn state.
- Modify `backend/app/services/agent_core/core/loop.py`: checkpoint loop state, enforce one approval boundary, close deferred calls, and preserve progress state.
- Modify `backend/app/services/agent_core/core/guardrails.py`: count repeats only when both calls and results match.
- Modify `backend/app/services/agent_core/context/system_prompt.py`: replace the Bioinfoflow-locked stable prompt with a compact provider-neutral prompt.
- Modify `backend/app/services/agent_core/context/assembler.py`: render target-specific dynamic context and local Bioinfoflow guidance only for local targets.
- Modify `backend/app/services/agent_core/context/instructions.py`: make the current session target override stale turn metadata.
- Modify `backend/tests/test_agent_core/test_harness_invariants.py`: approval batching, transcript closure, and target-coherence regressions.
- Modify `backend/tests/test_agent_core/test_runtime_reliability.py`: durable budget, fallback, token usage, and progress counter regressions.
- Modify `backend/tests/test_agent_core/test_context_compaction.py`: stable prompt and active-skill context assertions.
- Modify `backend/tests/test_agent_core/test_project_instructions.py`: current-target precedence assertions.
- Modify `backend/tests/test_agent_remote_tools.py`: remote environment and Phoenix-like target boundary regression.
- Modify `backend/app/models/agent_core.py` and add migration `0044_agent_session_active_turn.py`: one database-level active-turn claim per session.
- Modify `backend/app/repositories/agent_core_repo.py`: atomic session/turn/action state transitions.
- Modify `backend/app/services/agent_core/transcript/store.py`: deterministic atomic tool-result insertion.
- Modify `backend/tests/test_agent_core/test_durable_hardening.py`: cross-session concurrency, cancellation, identity, and recovery regressions.

## Phase 1: Durable Loop And Atomic Approval

### Task 1: Restore And Checkpoint The Turn Budget

**Files:**
- Modify: `backend/app/services/agent_core/core/budget.py`
- Modify: `backend/app/services/agent_core/core/loop.py`
- Test: `backend/tests/test_agent_core/test_runtime_reliability.py`

- [ ] **Step 1: Add a failing approval-resume budget test**

Add a test named `test_runtime_approval_resume_uses_remaining_turn_budget`.
Set `BIOINFOFLOW_AGENT_MAX_ITERATIONS=2`, make the first model response request
an approval-gated `bash` call, approve it, and make the resumed response request
another tool. Assert the model is called only twice and the turn terminates with
`iteration_budget_exhausted` instead of receiving a third model call.

The core assertions are:

```python
assert model_calls == 2
assert resumed_turn.status == "failed"
assert resumed_turn.error_code == "iteration_budget_exhausted"
assert resumed_turn.iteration_count == 2
assert resumed_turn.budget_snapshot == {
    "used_iterations": 2,
    "max_iterations": 2,
}
```

- [ ] **Step 2: Add a failing cumulative token-usage assertion**

Return usage `{prompt_tokens: 2, completion_tokens: 3, total_tokens: 5}` before
approval and `{prompt_tokens: 7, completion_tokens: 11, total_tokens: 18}` after
resume. Assert the final turn stores:

```python
assert resumed_turn.token_usage == {
    "prompt_tokens": 9,
    "completion_tokens": 14,
    "total_tokens": 23,
}
```

- [ ] **Step 3: Run the new test and verify the current reset behavior fails**

Run from `backend/`:

```bash
rtk uv run pytest \
  tests/test_agent_core/test_runtime_reliability.py::test_runtime_approval_resume_uses_remaining_turn_budget \
  -q
```

Expected: FAIL because `run_turn()` starts a new zeroed budget and token usage
after resume.

- [ ] **Step 4: Allow `IterationBudget` to start from persisted usage**

Change the dataclass to validate a restored count without adding another state
type:

```python
@dataclass
class IterationBudget:
    max_iterations: int = 6
    used_iterations: int = 0

    def __post_init__(self) -> None:
        self.max_iterations = max(int(self.max_iterations), 0)
        self.used_iterations = min(
            max(int(self.used_iterations), 0),
            self.max_iterations,
        )
```

- [ ] **Step 5: Load and checkpoint durable loop state in `AgentLoopController`**

Initialize the budget and usage from the turn:

```python
budget = IterationBudget(
    max_iterations=_max_iterations(),
    used_iterations=int(getattr(turn, "iteration_count", 0) or 0),
)
token_usage = dict(turn.token_usage or {}) or None
```

Add a focused helper that updates only existing turn columns:

```python
async def _checkpoint_loop_state(
    self,
    turn,
    *,
    budget: IterationBudget,
    token_usage: dict[str, Any] | None,
    progress: dict[str, Any] | None = None,
):
    loop_state = dict(getattr(turn, "loop_state", None) or {})
    if progress is not None:
        loop_state["progress"] = progress
    return await self.turns.update_all(
        turn,
        iteration_count=budget.used_iterations,
        budget_snapshot=budget.snapshot(),
        token_usage=token_usage,
        loop_state=loop_state,
    )
```

Checkpoint immediately after `budget.consume()` and again after merging model
usage. All returned `LoopResult` objects must use the cumulative values.

- [ ] **Step 6: Run focused and existing runtime reliability tests**

```bash
rtk uv run pytest \
  tests/test_agent_core/test_runtime_reliability.py::test_runtime_approval_resume_uses_remaining_turn_budget \
  tests/test_agent_core/test_runtime_reliability.py::test_runtime_stops_on_repeated_tool_calls_without_progress \
  tests/test_agent_core/test_runtime_reliability.py::test_runtime_allows_repeated_tool_polling_when_results_change \
  -q
```

Expected: PASS.

### Task 2: Stop At The First Approval Boundary And Close The Batch

**Files:**
- Modify: `backend/app/services/agent_core/core/loop.py`
- Test: `backend/tests/test_agent_core/test_harness_invariants.py`

- [ ] **Step 1: Add failing interaction and mutation batch tests**

Add these tests:

```python
async def test_tool_batch_stops_at_first_interaction_and_defers_later_calls(...):
    # Model emits ask_user followed by projects.list.
    # Assert ask_user is the only action and projects.list never runs.

async def test_tool_batch_stops_at_first_approval_and_defers_later_mutation(...):
    # Model emits approval-gated bash followed by files.write.
    # Assert the write action is never created or executed.
```

For each test, inspect transcript provider messages and assert every emitted
tool-call ID is represented by either the pending action or a structured
deferred result before resume. After resolving the pending action, assert the
next provider request has no unresolved tool-call IDs.

- [ ] **Step 2: Run the tests and verify current batching fails**

```bash
rtk uv run pytest \
  tests/test_agent_core/test_harness_invariants.py::test_tool_batch_stops_at_first_interaction_and_defers_later_calls \
  tests/test_agent_core/test_harness_invariants.py::test_tool_batch_stops_at_first_approval_and_defers_later_mutation \
  -q
```

Expected: FAIL because the current loop continues executing after
`requires_resume` and treats interaction tools as concurrent reads.

- [ ] **Step 3: Exclude interaction tools from concurrent read batching**

Change the predicate to:

```python
def _is_concurrent_read_only_tool(self, tool_name: str) -> bool:
    spec = self.registry.get(tool_name).spec
    return (
        spec.risk_level == "read"
        and not spec.write_scope
        and spec.interaction is None
    )
```

- [ ] **Step 4: Add one structured deferred-result constructor**

Use the existing `ToolExecutionResult` rather than adding a new model:

```python
def _deferred_tool_result(tool_name: str) -> ToolExecutionResult:
    return ToolExecutionResult(
        action_id="",
        status="deferred",
        error={
            "type": "DeferredToolCall",
            "message": (
                f"{tool_name} was not executed because an earlier tool call "
                "is waiting for user input or approval. Call it again if it "
                "is still needed after the turn resumes."
            ),
        },
    )
```

- [ ] **Step 5: Stop execution and close remaining call IDs**

When a sequential or concurrent result has `requires_resume=True`, append a
deferred tool result for each later call in provider order, do not invoke the
executor for those calls, and return `waiting=True` immediately. Keep the
pending call without a tool result until its action is resolved; no model
request occurs during that wait.

- [ ] **Step 6: Run approval, rejection, stale-target, and new batch tests**

```bash
rtk uv run pytest \
  tests/test_agent_core/test_harness_invariants.py::test_approval_resume_executes_tool_and_continues_turn \
  tests/test_agent_core/test_harness_invariants.py::test_rejected_tool_decision_continues_turn_with_tool_result \
  tests/test_agent_core/test_harness_invariants.py::test_resume_stale_local_tool_for_remote_session_records_failed_result \
  tests/test_agent_core/test_harness_invariants.py::test_tool_batch_stops_at_first_interaction_and_defers_later_calls \
  tests/test_agent_core/test_harness_invariants.py::test_tool_batch_stops_at_first_approval_and_defers_later_mutation \
  -q
```

Expected: PASS.

### Task 3: Persist Result-Aware Progress State

**Files:**
- Modify: `backend/app/services/agent_core/core/loop.py`
- Modify: `backend/app/services/agent_core/core/guardrails.py`
- Test: `backend/tests/test_agent_core/test_runtime_reliability.py`

- [ ] **Step 1: Add a failing changing-then-stable polling test**

Add `test_runtime_resets_repeat_grace_when_tool_results_change`. Return identical
tool calls with results `running-1`, `running-2`, `running-3`, `running-3`, then
a final assistant response. Assert the turn completes rather than stopping on
the first stable repeat.

- [ ] **Step 2: Run the test and verify it fails**

```bash
rtk uv run pytest \
  tests/test_agent_core/test_runtime_reliability.py::test_runtime_resets_repeat_grace_when_tool_results_change \
  -q
```

Expected: FAIL because the repeat counter currently advances on call signatures
alone.

- [ ] **Step 3: Restore and persist the compact progress payload**

Store only JSON-safe signatures and a count in `turn.loop_state["progress"]`:

```python
progress = {
    "previous_tool_calls": list(...),
    "previous_tool_results": list(...),
    "repeat_count": int(...),
}
```

Load this payload at `run_turn()` start. Increment `repeat_count` only when both
the call signatures and result signatures match; otherwise reset it to `1`.
Checkpoint the payload with the durable budget.

- [ ] **Step 4: Keep `no_progress_detected` as a cheap exact guardrail**

Retain the existing predicate and documentation, but pass it the corrected
result-aware count. Do not add fuzzy matching, embeddings, or a semantic
classifier.

- [ ] **Step 5: Run the Phase 1 test set**

```bash
rtk uv run pytest \
  tests/test_agent_core/test_harness_invariants.py \
  tests/test_agent_core/test_runtime_reliability.py \
  -q
rtk uv run ruff check \
  app/services/agent_core/core \
  tests/test_agent_core/test_harness_invariants.py \
  tests/test_agent_core/test_runtime_reliability.py
```

Expected: all tests and Ruff pass.

- [ ] **Step 6: Commit Phase 1**

```bash
rtk git add \
  backend/app/services/agent_core/core/budget.py \
  backend/app/services/agent_core/core/guardrails.py \
  backend/app/services/agent_core/core/loop.py \
  backend/tests/test_agent_core/test_harness_invariants.py \
  backend/tests/test_agent_core/test_runtime_reliability.py
rtk git commit -m "fix: preserve agent turn control across approvals"
```

## Phase 2: Neutral Prompt And Target-Coherent Context

### Task 4: Replace The Stable Prompt With The Minimal Neutral Core

**Files:**
- Modify: `backend/app/services/agent_core/context/system_prompt.py`
- Modify: `backend/app/services/agent_core/context/assembler.py`
- Test: `backend/tests/test_agent_core/test_context_compaction.py`
- Test: `backend/tests/test_agent_core/test_harness_invariants.py`

- [ ] **Step 1: Add failing prompt-boundary tests**

Assert the default stable prompt:

```python
prompt = default_system_prompt_snapshot().content
assert "You are an agent operating through" in prompt
assert "observe" in prompt.lower()
assert "verify" in prompt.lower()
assert "Bioinfoflow platform workflow" not in prompt
assert "Before submitting a run" not in prompt
assert len(prompt) < 6000
```

Also assert local dynamic context still contains a short Bioinfoflow platform
section so local run behavior is not lost.

- [ ] **Step 2: Run the prompt tests and verify they fail**

```bash
rtk uv run pytest \
  tests/test_agent_core/test_context_compaction.py \
  tests/test_agent_core/test_harness_invariants.py -q
```

Expected: FAIL on the domain-locked stable prompt assertions.

- [ ] **Step 3: Replace `_SYSTEM_PROMPT` and bump the snapshot ID**

Set `PROMPT_SNAPSHOT_ID = "bioinfoflow-agent-v8"` and organize the prompt into
these compact sections:

```text
Identity and scope
Operating loop: understand -> observe -> act -> verify -> finish
Tool discipline
Safety and state
Communication
```

The exact prompt must include these behaviors:

```text
- The latest user request defines the task; supplied target context defines
  where actions occur.
- Inspect the minimum evidence needed, make reasonable assumptions, and persist
  until the task is handled or a concrete blocker remains.
- Use the smallest sufficient dedicated tool. Use shell only when no dedicated
  tool fits. Match schemas and identifiers exactly.
- Parallelize only independent read-only work when the runtime supports it.
- Do not repeat unchanged failures or reread the same evidence without progress.
- Approval authorizes an action but does not prove it succeeded. Verify state
  changes before claiming completion.
- Preserve unrelated user changes and ask only when authority or a materially
  different product choice is missing.
```

- [ ] **Step 4: Move the local platform playbook into dynamic context**

Add a concise `_local_platform_context()` section in `assembler.py` covering
the existing dedicated-tool preference, exact workflow form keys, explicit
lifecycle mutations, and read-back verification. Keep it below 2,500
characters and inject it only for local execution targets.

- [ ] **Step 5: Remove duplicated exposed-tool prose**

Stop calling `_exposed_tool_lines()` from environment context because the
provider already receives authoritative schemas in `tools`. Remove the helper
if no tests or callers remain.

- [ ] **Step 6: Run prompt and context tests**

```bash
rtk uv run pytest \
  tests/test_agent_core/test_context_compaction.py \
  tests/test_agent_core/test_harness_invariants.py -q
```

Expected: PASS.

### Task 5: Make The Current Execution Target Authoritative

**Files:**
- Modify: `backend/app/services/agent_core/context/assembler.py`
- Modify: `backend/app/services/agent_core/context/instructions.py`
- Test: `backend/tests/test_agent_core/test_project_instructions.py`
- Test: `backend/tests/test_agent_remote_tools.py`

- [ ] **Step 1: Add failing current-target precedence tests**

Create a turn with stale local metadata, update the session to
`{"type": "remote_ssh", "connection_id": "conn-1"}`, and assert:

```python
assert "## Remote connection" in system_message
assert "Working directory:" not in system_message
assert "Allowed filesystem roots:" not in system_message
assert "## Platform inventory" not in system_message
assert "## Bioinfoflow local platform" not in system_message
```

Add the inverse instruction resolver test: a stale remote turn snapshot must
not override a current local session target.

- [ ] **Step 2: Run the tests and verify the context contradiction fails**

```bash
rtk uv run pytest \
  tests/test_agent_core/test_project_instructions.py \
  tests/test_agent_remote_tools.py -q
```

Expected: FAIL because turn metadata currently overrides session metadata and
remote context still includes local inventory.

- [ ] **Step 3: Resolve one current target in the assembler**

Use `execution_target_from_session(agent_session)` once per provider request and
pass it into environment rendering. For remote targets:

- render workspace, permission mode, runtime mode, role, toolset, and remote
  connection context;
- omit local repository paths, allowed roots, local project inventory, and the
  local platform playbook.

For local targets, retain local paths, inventory, and platform guidance.

- [ ] **Step 4: Change instruction policy precedence**

Build the merged instruction target from low to high priority:

```text
stale turn metadata
toolset policy
context policy
current session metadata / execution target
```

The final current session target must override all earlier target fields while
retaining non-target instruction snapshot fields.

- [ ] **Step 5: Add a Phoenix-like regression assertion**

In `test_agent_remote_tools.py`, construct a remote session with an active
`phoenixcli-operator`-style skill summary and a user task mentioning
`Deaf_20`. Assert that provider messages expose only remote/neutral tools and
do not contain local `runs.submit`, workflow-registration guidance, or local
platform inventory. This is an offline context/exposure regression and must not
submit a real Phoenix task.

- [ ] **Step 6: Run Phase 2 validation**

```bash
rtk uv run pytest \
  tests/test_agent_remote_tools.py \
  tests/test_agent_core/test_context_compaction.py \
  tests/test_agent_core/test_harness_invariants.py \
  tests/test_agent_core/test_project_instructions.py \
  -q
rtk uv run ruff check \
  app/services/agent_core/context \
  app/services/agent_core/tools/toolsets.py \
  tests/test_agent_remote_tools.py \
  tests/test_agent_core
```

Expected: all tests and Ruff pass.

- [ ] **Step 7: Commit Phase 2**

```bash
rtk git add \
  backend/app/services/agent_core/context/system_prompt.py \
  backend/app/services/agent_core/context/assembler.py \
  backend/app/services/agent_core/context/instructions.py \
  backend/tests/test_agent_remote_tools.py \
  backend/tests/test_agent_core/test_context_compaction.py \
  backend/tests/test_agent_core/test_harness_invariants.py \
  backend/tests/test_agent_core/test_project_instructions.py
rtk git commit -m "refactor: make agent harness target coherent"
```

## Phase 3: Independent Review, Completion Audit, And PR

### Task 6: Review And Fix The Completed Harness

**Files:**
- Modify: only files implicated by validated review findings.

- [ ] **Step 1: Dispatch parallel read-only reviews**

Assign independent agents to:

1. loop budget, fallback, and approval transcript correctness;
2. execution-target security and stale-target behavior;
3. prompt/provider compatibility and skill precedence.

Each reviewer must create a dedicated goal and return findings ordered by
severity with file/line evidence and missing tests.

- [ ] **Step 2: Fix every critical or important finding with a regression test**

For each accepted finding, first add or adjust the smallest failing test, then
patch the implementation and rerun the affected focused suite. Reject findings
that contradict the design with written evidence.

Accepted final-review invariants:

- serialize turn creation with `AgentSession.active_turn_id` plus a conditional
  database update; retain the claim through approval and release it only at a
  terminal turn state;
- use the existing turn lease columns as a second CAS so duplicate workers
  cannot run the same turn concurrently;
- treat the existing `claimed_at` value as the immutable owner token for lease
  renewal, checkpoints, and terminal writes; recovery must not take over an
  unexpired lease;
- make action terminal states monotonic with expected-status CAS updates;
- derive canonical tool-call IDs from `(turn, iteration, call index)` rather
  than trusting provider IDs;
- derive tool-result message IDs from `(turn, canonical call ID)` and use
  database conflict-ignore for exactly-once insertion;
- allow a new turn to atomically replace a stale session claim only when the
  referenced turn is absent or terminal.
- commit the session claim, turn, initial user transcript, and created event as
  one aggregate; commit successful action result, artifact, and completion
  events as one aggregate;
- watch claimed actions from an independent database session so cross-process
  cancellation cancels cooperative tools, with explicit subprocess cleanup for
  shell, Docker build, and ripgrep tools;
- bind action creation, execution start, and aggregate completion to the
  original turn owner token, including isolated read workers;
- heartbeat the turn lease while a healthy long-running tool is active so
  another process cannot falsely recover it;
- require resume requests to match the turn's one pending observation; and
- serialize assistant events and canonical transcript commits against the
  execution-target row so a response from a superseded target is discarded.

- [ ] **Step 3: Commit review fixes when changes exist**

```bash
rtk git add backend/app backend/tests
rtk git commit -m "fix: address agent harness review findings"
```

Skip the commit only when all reviewers report no actionable finding and the
working tree is clean.

- [ ] **Step 4: Run full backend verification**

From `backend/`:

```bash
rtk uv run pytest
rtk uv run ruff check .
```

Expected: PASS with no test failures or Ruff diagnostics.

- [ ] **Step 5: Audit every completion criterion**

Inspect current code, tests, git diff, and command output to prove:

- every tool-call ID is closed before a subsequent model request;
- iteration and token budgets are cumulative across resume and fallback;
- no-progress grace is result-aware;
- remote context and tools contain no local target leakage;
- local Bioinfoflow guidance remains available dynamically;
- the stable prompt is compact and provider-neutral;
- exactly one evidence-driven migration was introduced for session
  serialization; no tool-search framework, Phoenix tool, provider rewrite, or
  unrelated redesign was introduced.

- [ ] **Step 6: Rebase, rerun affected checks, and push**

```bash
rtk git fetch origin --prune
rtk git rebase origin/main
rtk uv run pytest
rtk uv run ruff check .
rtk git push -u origin codex/minimal-provider-agnostic-harness
```

Expected: rebase and verification pass; branch push succeeds.

- [ ] **Step 7: Open a ready pull request**

Use this Conventional Commit title:

```text
refactor: strengthen the provider-agnostic agent harness
```

The PR body must summarize the two implementation phases, list focused and
full verification commands, link the design and implementation plans, and call
out the explicit non-goals.
