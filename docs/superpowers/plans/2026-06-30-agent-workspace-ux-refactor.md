# Agent Workspace UX Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor Bioinfoflow Agent workspace UX to match Codex-style right drawer, deliverable-only artifacts, blank browser start, remote-aware bottom terminal, and simplified SSH cards.

**Architecture:** Keep the existing Next.js/FastAPI boundaries, but move semantics into explicit helpers instead of one-off UI filters. Backend artifact creation must stop generating command/log artifacts; frontend artifact counts and review lists must use a deliverable predicate. The terminal API gains target metadata and optional remote execution without moving terminal UI into the drawer.

**Tech Stack:** FastAPI, SQLAlchemy async repositories/services, Next.js 16, React 19, Tailwind, Vitest, pytest.

---

## File Map

- `backend/app/services/agent_core/*`: audit artifact creation and remove command/log artifact creation.
- `backend/tests/test_agent_runtime_artifacts.py` or adjacent existing tests: prove command/log events do not create review artifacts.
- `frontend/lib/agent-runtime.ts`: expose a deliverable artifact predicate/count helper.
- `frontend/components/bioinfoflow/agent-runtime/artifact-preview-drawer.tsx`: render only deliverable artifacts and empty state.
- `frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx`: default drawer closed, Codex-like right drawer state.
- `frontend/components/bioinfoflow/agent-runtime/agent-tabbed-panel.tsx`: default to files, compact panels, no terminal content page.
- `frontend/components/bioinfoflow/agent-runtime/browser-tab.tsx`: blank initial browser route.
- `frontend/hooks/use-terminal-session.ts`: send terminal target information and read target metadata.
- `frontend/components/bioinfoflow/terminal/terminal-dock.tsx`: light bottom dock with target label and close-only visible action.
- `backend/app/api/v1/terminal.py`, `backend/app/schemas/terminal.py`, `backend/app/services/terminal_service.py`: support local/remote terminal target metadata.
- `frontend/app/(app)/connections/components/connection-list.tsx`: simplify card layout and selected state.
- `frontend/messages/en.json`, `frontend/messages/zh-CN.json`: update copy for new terminal/browser/artifact states.

## Task 1: Artifact Semantics

**Files:**
- Modify: `frontend/lib/agent-runtime.ts`
- Modify: `frontend/components/bioinfoflow/agent-runtime/artifact-preview-drawer.tsx`
- Modify: backend agent artifact creation files discovered by `rtk rg "command|log_summary|artifact.created" backend/app/services/agent_core backend/tests`
- Test: existing frontend/backend artifact tests or new focused tests near existing suites

- [ ] **Step 1: Write failing tests**

Add tests proving command/log artifacts are not counted as review artifacts and are not created by backend command/log paths. Use existing test style in the nearest artifact/runtime test files.

- [ ] **Step 2: Verify red**

Run the focused tests. Expected: fail because command/log artifacts currently count or are created.

- [ ] **Step 3: Implement deliverable predicate**

Add a single frontend helper equivalent to:

```ts
const DELIVERABLE_ARTIFACT_TYPES = new Set([
  "file",
  "html",
  "pdf",
  "report",
  "markdown",
  "sheet",
  "spreadsheet",
])

export function isDeliverableArtifact(artifact: AgentRuntimeArtifact) {
  if (artifact.type === "command" || artifact.type === "log_summary" || artifact.type === "todo_list") {
    return false
  }
  if (artifact.file_path) return true
  return DELIVERABLE_ARTIFACT_TYPES.has(artifact.type)
}
```

Use it for counts and review lists.

- [ ] **Step 4: Stop backend command/log artifacts**

Remove or redirect backend artifact creation for commands/log summaries so they remain timeline/tool activity data only.

- [ ] **Step 5: Verify green and commit**

Run focused frontend/backend tests, then commit:

```bash
rtk git add frontend backend
rtk git commit -m "fix: keep command logs out of artifacts"
```

## Task 2: Codex-Style Agent Drawer and Blank Browser

**Files:**
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-tabbed-panel.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/browser-tab.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`
- Test: nearest Agent runtime component tests

- [ ] **Step 1: Write failing tests**

Add tests for desktop drawer default closed, first open shows files, review empty state remains available, and browser initial state is blank instead of current app route.

- [ ] **Step 2: Verify red**

Run focused frontend tests. Expected: fail on current default-open drawer and browser URL behavior.

- [ ] **Step 3: Implement drawer state**

Initialize `sidecarOpen` to `false`, reset new conversation without reopening it, default active panel to files, and remove terminal as right-drawer content. Preserve active panel while the component remains mounted.

- [ ] **Step 4: Implement blank browser**

Change browser initialization so it starts with an empty URL and blank empty state. Keep manual URL entry and later navigation intact.

- [ ] **Step 5: Verify green and commit**

Run focused frontend tests and i18n lint for changed copy, then commit:

```bash
rtk git add frontend
rtk git commit -m "feat: align agent drawer with Codex workspace"
```

## Task 3: Remote-Aware Bottom Terminal

**Files:**
- Modify: `backend/app/schemas/terminal.py`
- Modify: `backend/app/api/v1/terminal.py`
- Modify: `backend/app/services/terminal_service.py`
- Modify: `frontend/hooks/use-terminal-session.ts`
- Modify: `frontend/components/bioinfoflow/terminal/terminal-dock.tsx`
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`
- Test: `backend/tests/test_api/test_terminal_api.py`, `backend/tests/test_api/test_terminal_ws.py`, focused frontend tests

- [ ] **Step 1: Write failing tests**

Add backend tests showing a project with `remote_connection_id` returns terminal target metadata of type `remote`, while a local project returns type `local`. Add a frontend test for displaying the target label.

- [ ] **Step 2: Verify red**

Run focused backend/frontend tests. Expected: fail because terminal sessions only expose local project metadata.

- [ ] **Step 3: Implement target metadata**

Add terminal session fields for `target_type`, `target_label`, and optional `remote_connection_id`. For local sessions use the existing project cwd. For remote projects, create the session as a remote target and label it with the connection name. If remote pty execution support is not yet present, implement a clear service boundary and error state rather than silently opening local.

- [ ] **Step 4: Simplify dock UI**

Keep bottom dock. Show compact tab/title with target label and a close button. Remove visible clear/reconnect/new-terminal buttons from the right header.

- [ ] **Step 5: Verify green and commit**

Run focused backend/frontend terminal tests, then commit:

```bash
rtk git add backend frontend
rtk git commit -m "feat: make terminal target project environment"
```

## Task 4: Connection Card Simplification

**Files:**
- Modify: `frontend/app/(app)/connections/components/connection-list.tsx`
- Test: existing connection page tests or component tests

- [ ] **Step 1: Write failing/coverage test**

Add or update a test to assert the card exposes name, `user@host`, and status, and does not render auth method/alias/last checked in the card body.

- [ ] **Step 2: Verify red**

Run focused frontend test. Expected: fail because current cards include extra metadata.

- [ ] **Step 3: Implement simplified card**

Use a wider grid minimum, fewer text rows, a light selected state, and the existing detail/edit surfaces for secondary metadata.

- [ ] **Step 4: Verify green and commit**

Run focused frontend test and lint, then commit:

```bash
rtk git add frontend/app/\(app\)/connections/components/connection-list.tsx frontend/tests
rtk git commit -m "refactor: simplify SSH connection cards"
```

## Task 5: Integration, Visual Review, Review Agents, and PR

**Files:**
- Modify only files required by review findings.

- [ ] **Step 1: Run broad verification**

Run:

```bash
cd backend && rtk uv run pytest && rtk uv run ruff check .
cd ../frontend && rtk bun run lint && rtk bun run lint:i18n && rtk bun run test
```

- [ ] **Step 2: Run visual review**

Set repo `.env` to `AUTH_MODE=dev` if needed, start backend/frontend services, and inspect Agent, terminal, browser, artifact review, and connection center. Use screenshots to verify no overlap/truncation.

- [ ] **Step 3: Spawn review agents**

Run parallel review agents for artifact semantics, terminal/backend safety, and frontend UX regressions. Fix validated findings.

- [ ] **Step 4: Sync and open PR**

Fetch/rebase `origin/main`, rerun relevant checks if rebase changes code, push the branch, and open a draft PR.

