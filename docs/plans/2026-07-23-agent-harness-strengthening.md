# Agent Harness Strengthening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strengthen Bioinfoflow AgentCore with immutable per-session custom instructions, a substantially richer system prompt, ordered safe tool parallelism, and a smaller clearer tool surface while preserving manual and agent-selected remote machines.

**Architecture:** Keep the existing canonical transcript, permission executor, and registration/exposure separation. Persist one per-user custom-instructions string, compose it into the prompt snapshot only when a top-level session is created, and make stored snapshots authoritative forever. Refine tools through explicit concurrency metadata, provider-based registration, one patch-oriented file mutation tool, resource-specific inspect tools, and conservative exposure rules rather than a new plugin framework.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Pydantic, pytest, Next.js 16, React 19, TypeScript, next-intl, Vitest.

---

## Scope and invariants

- `rg`, `jq`, and `sed` remain ordinary commands executed through the `bash` tool. They do not become dedicated Agent tools.
- The stable prompt explicitly recommends `rg`/`rg --files` for search and `jq`/`sed` for bounded structured or line-oriented inspection when available.
- Custom instructions are one unstructured text value. There are no company, workspace, project, category, precedence, or scope controls.
- Saving custom instructions affects only top-level sessions created afterwards.
- Existing sessions always use their persisted `prompt_snapshot.content`, even after a prompt version upgrade.
- Child worker sessions inherit the parent prompt snapshot instead of reading the latest user setting.
- `remote.connections.list` remains registered and exposed whenever remote execution is allowed.
- Manual mode restricts remote tools to selected targets. Auto mode allows the Agent to call `remote.connections.list`, choose an available connection, and pass its `connection_id` to a remote tool; the permission snapshot then fences execution to that chosen target.
- Only adjacent explicitly `parallel_safe` tool calls may run concurrently. A serial call, approval, or interaction is an ordering barrier.
- Registration, exposure, authorization, and execution remain separate layers.
- Do not add MCP, prompt-cache work, company instruction hierarchies, knowledge bases, or a generic plugin lifecycle.

## Target file map

### Backend settings and prompt state

- Create `backend/app/models/agent_user_settings.py`: one row per workspace/user with `custom_instructions`.
- Create `backend/app/repositories/agent_user_settings_repo.py`: scoped get/upsert operations.
- Create `backend/alembic/versions/0052_agent_user_custom_instructions.py`: table and unique constraint.
- Modify `backend/app/models/__init__.py`: export the model.
- Modify `backend/app/schemas/agent_core.py`: settings read/update schemas.
- Modify `backend/app/services/agent_core/service.py`: settings access, top-level snapshot composition, child snapshot override.
- Modify `backend/app/api/v1/agent.py`: `GET` and `PUT /agent/settings`.
- Modify `backend/app/services/agent_core/context/system_prompt.py`: v9 prompt, custom-instruction composition, immutable snapshot resolution.

### Frontend settings

- Create `frontend/lib/agent-settings.ts`: typed get/update client.
- Create `frontend/components/bioinfoflow/settings/agent-custom-instructions.tsx`: textarea/save behavior.
- Modify `frontend/components/bioinfoflow/settings/settings-page-client.tsx`: render the panel in the existing Agent section.
- Modify `frontend/messages/en.json` and `frontend/messages/zh-CN.json`: labels, help, save states, errors.

### Tool runtime and catalog

- Modify `backend/app/services/agent_core/tools/specs.py`: add `parallel_safe` and `AgentToolProvider`.
- Modify `backend/app/services/agent_core/tools/registry.py`: add `register_many` and provider registration.
- Create `backend/app/services/agent_core/tools/providers.py`: deterministic grouped providers.
- Modify `backend/app/services/agent_core/tools/__init__.py`: compose providers instead of 58 manual calls.
- Modify `backend/app/services/agent_core/core/loop.py`: ordered contiguous execution segments.
- Modify `backend/app/services/agent_core/tools/files/resources.py`: add `files.apply_patch`.
- Modify `backend/app/services/agent_core/tools/files/__init__.py`: export the patch tool.
- Modify `backend/app/services/agent_core/tools/platform/runs.py`: add `runs.inspect`.
- Modify `backend/app/services/agent_core/tools/platform/workflows.py`: add `workflows.inspect`.
- Modify `backend/app/services/agent_core/tools/toolsets.py`: hide redundant catalog/legacy tools while retaining remote connection discovery.
- Modify tool descriptions for `bash`, remote tools, task, skills, run/workflow inspection.

### Tests

- Modify `backend/tests/test_agent_core/test_harness_invariants.py`.
- Create `backend/tests/test_agent_core/test_agent_settings.py`.
- Modify `backend/tests/test_agent_core/test_tool_call_batches.py`.
- Create `backend/tests/test_agent_core/test_tools/test_file_patch.py`.
- Modify `backend/tests/test_agent_core/test_tools/test_platform_resources.py`.
- Modify `backend/tests/test_agent_core/test_execution_scope.py`.
- Modify `backend/tests/test_agent_core/test_subagents.py`.
- Modify `frontend/tests/unit/components/settings-page.test.tsx`.
- Modify `frontend/tests/integration/pages/settings-page-flow.test.tsx` if API integration coverage is needed.

---

### Task 1: Persist one custom-instructions value and freeze it into new sessions

**Files:**
- Create: `backend/app/models/agent_user_settings.py`
- Create: `backend/app/repositories/agent_user_settings_repo.py`
- Create: `backend/alembic/versions/0052_agent_user_custom_instructions.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/schemas/agent_core.py`
- Modify: `backend/app/api/v1/agent.py`
- Modify: `backend/app/services/agent_core/service.py`
- Modify: `backend/app/services/agent_core/context/system_prompt.py`
- Test: `backend/tests/test_agent_core/test_agent_settings.py`
- Test: `backend/tests/test_agent_core/test_harness_invariants.py`
- Test: `backend/tests/test_agent_core/test_subagents.py`

- [ ] **Step 1: Write failing model/API/snapshot tests**

Add tests proving:

```python
async def test_agent_settings_are_scoped_by_workspace_and_user(...): ...
async def test_new_session_snapshots_current_custom_instructions(...): ...
async def test_updating_settings_does_not_change_existing_session_snapshot(...): ...
async def test_child_session_inherits_parent_prompt_snapshot(...): ...

def test_stored_prompt_snapshot_is_used_verbatim_even_when_older():
    assert resolve_system_prompt_prefix(
        {"id": "bioinfoflow-agent-v8", "content": "frozen"}
    ) == "frozen"
```

API tests must cover `GET /api/v1/agent/settings`, `PUT /api/v1/agent/settings`, trimming, empty text, and the 20,000-character validation limit.

- [ ] **Step 2: Run focused tests and verify RED**

Run from `backend/`:

```bash
rtk uv run pytest tests/test_agent_core/test_agent_settings.py tests/test_agent_core/test_harness_invariants.py tests/test_agent_core/test_subagents.py -q
```

Expected: failures because settings schemas/repository/endpoints do not exist and old snapshots still auto-upgrade.

- [ ] **Step 3: Add the minimal persistence model and migration**

Implement a model equivalent to:

```python
class AgentUserSettings(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agent_user_settings"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "user_id", name="uq_agent_user_settings_workspace_user"
        ),
    )

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    custom_instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
```

The repository must expose scoped `get(workspace_id, user_id)` and atomic `upsert(...)` behavior.

- [ ] **Step 4: Add settings schemas and endpoints**

Use these public shapes:

```python
class AgentSettingsRead(BaseModel):
    custom_instructions: str = ""

class AgentSettingsUpdate(BaseModel):
    custom_instructions: str = Field(default="", max_length=20_000)
```

`PUT` trims surrounding whitespace and persists an empty string when cleared.

- [ ] **Step 5: Compose and freeze snapshots**

Change the prompt API to:

```python
def default_system_prompt_snapshot(
    custom_instructions: str | None = None,
) -> SystemPromptSnapshot: ...

def resolve_system_prompt_prefix(stored_snapshot: dict | None) -> str:
    stored_content = str((stored_snapshot or {}).get("content") or "")
    return stored_content or default_system_prompt_snapshot().content
```

Top-level `create_session()` reads current user settings unless an explicit `prompt_snapshot` override is supplied. Child-session creation passes the parent's complete snapshot through that override.

- [ ] **Step 6: Run migration and focused tests and verify GREEN**

```bash
rtk uv run alembic upgrade head
rtk uv run pytest tests/test_agent_core/test_agent_settings.py tests/test_agent_core/test_harness_invariants.py tests/test_agent_core/test_subagents.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
rtk git add backend/app backend/alembic/versions/0052_agent_user_custom_instructions.py backend/tests/test_agent_core
rtk git commit -m "feat: add immutable agent custom instructions"
```

---

### Task 2: Add the single custom-instructions textarea

**Files:**
- Create: `frontend/lib/agent-settings.ts`
- Create: `frontend/components/bioinfoflow/settings/agent-custom-instructions.tsx`
- Modify: `frontend/components/bioinfoflow/settings/settings-page-client.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`
- Test: `frontend/tests/unit/components/settings-page.test.tsx`

- [ ] **Step 1: Write failing UI tests**

Tests must prove that the Agent settings section:

```typescript
it("loads and displays saved custom instructions", async () => {})
it("saves the textarea value through the agent settings API", async () => {})
it("allows clearing custom instructions", async () => {})
it("keeps the save button disabled while unchanged or saving", async () => {})
it("shows a localized error when loading or saving fails", async () => {})
```

- [ ] **Step 2: Run the focused test and verify RED**

```bash
rtk bun run test -- frontend/tests/unit/components/settings-page.test.tsx
```

Expected: FAIL because the textarea and API client do not exist.

- [ ] **Step 3: Implement the API client and focused panel**

Expose:

```typescript
export type AgentSettings = { custom_instructions: string }
export async function getAgentSettings(): Promise<AgentSettings>
export async function updateAgentSettings(
  customInstructions: string,
): Promise<AgentSettings>
```

The component contains one textarea, one save button, loading/error states, and no scope/category/personality controls.

- [ ] **Step 4: Add bilingual copy and mount it in the existing Agent section**

English and Chinese copy must state that changes apply to new sessions only. Do not describe the feature as company or workspace policy.

- [ ] **Step 5: Run tests, i18n lint, and verify GREEN**

```bash
rtk bun run test -- frontend/tests/unit/components/settings-page.test.tsx
rtk bun run lint:i18n
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
rtk git add frontend/lib/agent-settings.ts frontend/components/bioinfoflow/settings frontend/messages frontend/tests/unit/components/settings-page.test.tsx
rtk git commit -m "feat: add agent custom instructions settings"
```

---

### Task 3: Replace the compact prompt with a comprehensive Bioinfoflow agent contract

**Files:**
- Modify: `backend/app/services/agent_core/context/system_prompt.py`
- Modify: `backend/tests/test_agent_core/test_harness_invariants.py`
- Modify: `backend/tests/test_agent_core/test_context_file_refs.py`

- [ ] **Step 1: Write failing prompt contract tests**

The tests must require `bioinfoflow-agent-v9`, a provider-neutral prompt of roughly 350-700 non-empty lines, and sections covering:

```text
Identity and mission
Instruction authority
Request types and authorization
Outcome and completion contract
Evidence-first workflow
Planning and persistence
Tool selection
Shell command guidance
Parallelism and ordering
File and code changes
Bioinfoflow platform operations
Workflow and run lifecycle
Remote execution and target selection
Failure recovery
Verification
Communication
Project instructions, skills, and custom instructions
```

Assert explicit guidance that `rg`/`rg --files`, `jq`, and `sed` are commands used through `bash`; dedicated platform tools beat shell; `remote.connections.list` is used in auto mode before choosing a `connection_id`; manual mode never escapes selected targets; submitting a run is not completion; approval is not proof of success; existing user changes are preserved.

- [ ] **Step 2: Run prompt tests and verify RED**

```bash
rtk uv run pytest tests/test_agent_core/test_harness_invariants.py tests/test_agent_core/test_context_file_refs.py -q
```

Expected: FAIL against v8 and the compact prompt.

- [ ] **Step 3: Write the v9 prompt without copying third-party text**

Write original Bioinfoflow wording. Keep project-specific build commands in AGENTS.md, not in the stable prompt. Keep tool schemas out of the handwritten prompt. Include the exact custom-instruction wrapper:

```text
## User-provided custom instructions
The following text was saved by the user for new sessions. Apply it as user
guidance when it does not conflict with platform safety, permission decisions,
tool contracts, project instructions, or the user's latest explicit request.

<verbatim trimmed custom instructions>
```

- [ ] **Step 4: Run focused tests and verify GREEN**

```bash
rtk uv run pytest tests/test_agent_core/test_harness_invariants.py tests/test_agent_core/test_context_file_refs.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/services/agent_core/context/system_prompt.py backend/tests/test_agent_core
rtk git commit -m "feat: strengthen the agent system prompt"
```

---

### Task 4: Preserve tool-call order while parallelizing safe adjacent calls

**Files:**
- Modify: `backend/app/services/agent_core/tools/specs.py`
- Modify: read-only tool specifications under `backend/app/services/agent_core/tools/`
- Modify: `backend/app/services/agent_core/core/loop.py`
- Modify: `backend/tests/test_agent_core/test_tool_call_batches.py`

- [ ] **Step 1: Write failing concurrency tests**

Add real timing/order tests for:

```python
async def test_adjacent_parallel_safe_calls_overlap(): ...
async def test_write_then_read_preserves_order(): ...
async def test_read_write_read_respects_both_barriers(): ...
async def test_waiting_approval_stops_later_segments(): ...
async def test_interaction_call_remains_exclusive(): ...
```

- [ ] **Step 2: Run the focused tests and verify RED**

```bash
rtk uv run pytest tests/test_agent_core/test_tool_call_batches.py -q
```

Expected: the write/read ordering regression fails because all read candidates currently execute before the ordered loop.

- [ ] **Step 3: Add explicit concurrency metadata**

Add:

```python
parallel_safe: bool = False
```

to `AgentToolSpec`. Mark only proven read-only tools safe. Add validation or tests preventing a `parallel_safe` tool from declaring `write_scope` or a non-read risk level.

- [ ] **Step 4: Execute ordered contiguous segments**

Replace the global read gather with an algorithm equivalent to:

```python
for segment in contiguous_execution_segments(prepared):
    if segment.parallel:
        results = await asyncio.gather(*(execute(item) for item in segment.items))
        append_results_in_original_ordinal_order(results)
    else:
        result = await execute(segment.items[0])
        append_result(result)
    if batch_is_waiting_or_interrupted():
        break
```

Preparation may remain atomic and serial. Execution must not cross a serial, approval, or interaction barrier.

- [ ] **Step 5: Run focused tests and verify GREEN**

```bash
rtk uv run pytest tests/test_agent_core/test_tool_call_batches.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
rtk git add backend/app/services/agent_core/tools backend/app/services/agent_core/core/loop.py backend/tests/test_agent_core/test_tool_call_batches.py
rtk git commit -m "fix: preserve ordered parallel tool execution"
```

---

### Task 5: Refine registration, file mutation, inspection tools, and exposure

**Files:**
- Modify: `backend/app/services/agent_core/tools/specs.py`
- Modify: `backend/app/services/agent_core/tools/registry.py`
- Create: `backend/app/services/agent_core/tools/providers.py`
- Modify: `backend/app/services/agent_core/tools/__init__.py`
- Modify: `backend/app/services/agent_core/tools/files/resources.py`
- Modify: `backend/app/services/agent_core/tools/files/__init__.py`
- Modify: `backend/app/services/agent_core/tools/platform/runs.py`
- Modify: `backend/app/services/agent_core/tools/platform/workflows.py`
- Modify: `backend/app/services/agent_core/tools/toolsets.py`
- Modify: `backend/app/services/agent_core/tools/execution/shell.py`
- Modify: `backend/app/services/agent_core/tools/remote/resources.py`
- Modify: `backend/app/services/agent_core/tools/subagents/__init__.py`
- Test: `backend/tests/test_agent_core/test_tools/test_file_patch.py`
- Test: `backend/tests/test_agent_core/test_tools/test_platform_resources.py`
- Test: `backend/tests/test_agent_core/test_execution_scope.py`
- Test: `backend/tests/test_agent_core/test_subagents.py`
- Test: `backend/tests/test_agent_core/test_harness_invariants.py`

- [ ] **Step 1: Write failing catalog and behavior tests**

Require:

```text
files.apply_patch is exposed; files.write and files.edit are not exposed
task is exposed; subagent.analyze is not exposed
skills.load is exposed; skills.list and plugins.list are not exposed by normal execution
memory tools remain registered but are not exposed by normal execution
remote.connections.list remains exposed whenever remote scope is allowed
runs.inspect replaces run summary/logs/outputs/dag/audit exposure
workflows.inspect replaces workflow summary/source/dag/form_spec exposure
provider order is deterministic
```

Compatibility implementations may remain registered only when existing internal callers require them, but legacy names must not be sent to the model.

- [ ] **Step 2: Run focused tests and verify RED**

```bash
rtk uv run pytest tests/test_agent_core/test_tools/test_file_patch.py tests/test_agent_core/test_tools/test_platform_resources.py tests/test_agent_core/test_execution_scope.py tests/test_agent_core/test_subagents.py tests/test_agent_core/test_harness_invariants.py -q
```

Expected: FAIL because new tools/providers/exposure rules do not exist.

- [ ] **Step 3: Add the thin provider seam**

Use:

```python
class AgentToolProvider(Protocol):
    def tools(self) -> Iterable[AgentTool]: ...
```

Create deterministic providers for core, platform, remote, web, and agent-support tools. `AgentToolRegistry.register_many()` must reject duplicate names instead of silently replacing a tool.

- [ ] **Step 4: Add `files.apply_patch`**

Use one structured JSON mutation contract rather than a free-form shell patch:

```json
{
  "operations": [
    {"op": "replace", "path": "a.txt", "old_text": "before", "new_text": "after", "replace_all": false},
    {"op": "create", "path": "b.txt", "content": "new file\n"},
    {"op": "delete", "path": "c.txt"}
  ]
}
```

Validate every path and every replacement before writing anything. Apply the batch atomically from the tool's perspective: if validation fails, no file changes. Return per-file operation summaries. Reject duplicate/conflicting operations for the same path in one call.

- [ ] **Step 5: Add resource-specific inspect tools**

`runs.inspect` accepts `run_id`, `view` (`summary`, `logs`, `outputs`, `dag`, `audit`), plus view-specific bounded options such as `tail`.

`workflows.inspect` accepts `workflow_id` and `view` (`summary`, `source`, `dag`, `form_spec`).

Reuse existing services/repositories and preserve current result payloads under a stable wrapper containing `view` and the selected data.

- [ ] **Step 6: Refine exposure without removing remote discovery**

Normal execution excludes legacy file mutation tools, `subagent.analyze`, `skills.list`, `plugins.list`, and memory tools. It includes `remote.connections.list` whenever the execution scope permits remote targets, including auto mode. Remote operation tools remain unavailable when scope forbids remote execution.

- [ ] **Step 7: Strengthen tool descriptions**

The `bash` description states that `rg`, `jq`, and `sed` are ordinary commands inside this tool and that structured platform tools should be preferred for Bioinfoflow resources. Remote descriptions explain manual versus auto target selection and opaque `connection_id` copying. Inspect tools describe views and completion semantics.

- [ ] **Step 8: Run focused tests and verify GREEN**

```bash
rtk uv run pytest tests/test_agent_core/test_tools/test_file_patch.py tests/test_agent_core/test_tools/test_platform_resources.py tests/test_agent_core/test_execution_scope.py tests/test_agent_core/test_subagents.py tests/test_agent_core/test_harness_invariants.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
rtk git add backend/app/services/agent_core/tools backend/tests/test_agent_core
rtk git commit -m "refactor: simplify agent tool capabilities"
```

---

### Task 6: Full verification, documentation review, and PR preparation

**Files:**
- Modify as needed based on review findings.
- Verify: `docs/plans/2026-07-23-agent-harness-strengthening.md`

- [ ] **Step 1: Run backend migration, tests, and lint**

From `backend/`:

```bash
rtk uv run alembic upgrade head
rtk uv run pytest
rtk uv run ruff check .
rtk uv run ruff format --check .
```

- [ ] **Step 2: Run frontend tests, lint, i18n, and build**

From `frontend/`:

```bash
rtk bun run lint
rtk bun run lint:i18n
rtk bun run test
rtk bun run build
```

- [ ] **Step 3: Run repository hygiene checks**

From repo root:

```bash
rtk git diff --check
rtk git status --short
rtk git log --oneline origin/main..HEAD
```

- [ ] **Step 4: Independent spec and code-quality review**

Review the complete `origin/main..HEAD` range against this plan. Fix every Critical or Important finding with a failing regression test first, then re-run the relevant focused and full checks.

- [ ] **Step 5: Commit review fixes if needed**

```bash
rtk git add backend/app backend/tests frontend/components frontend/lib frontend/messages frontend/tests
rtk git commit -m "fix: address agent harness review findings"
```

- [ ] **Step 6: Rebase, reverify, push, and create PR**

```bash
rtk git fetch origin --prune
rtk git rebase origin/main
rtk git push -u origin codex/strengthen-agent-harness
rtk gh pr create --title "feat: strengthen the agent harness" --body "## Summary
- add per-user custom instructions frozen into new session snapshots
- strengthen AgentCore behavior and ordered safe tool execution
- simplify tool exposure while preserving manual and automatic remote targets

## Test Plan
- backend pytest and Ruff checks
- frontend lint, i18n, tests, and production build
- Alembic upgrade and repository diff checks"
```

The PR body must summarize custom instructions, immutable snapshots, prompt behavior, ordered parallel execution, tool-surface changes, preserved remote auto/manual selection, migration, and exact verification commands/results.

---

## Self-review of this plan

- Spec coverage: custom textarea, new-session-only semantics, comprehensive prompt, command-line guidance, parallel correctness, provider seam, tool additions/removals, and remote auto/manual selection are each assigned to a task.
- YAGNI: no company instruction model, MCP, cache implementation, knowledge base, generic plugin lifecycle, or interactive shell process manager is included.
- Type consistency: settings use `custom_instructions`; prompt snapshots remain `{id, content}`; remote selection continues to use `execution_scope.mode` plus `connection_id`; tool concurrency uses `parallel_safe`.
- Safety: file patch batches validate before mutation; old session prompts remain immutable; remote actions retain fresh permission and target revision checks.
