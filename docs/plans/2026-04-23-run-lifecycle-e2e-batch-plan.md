# Run Lifecycle Test Backfill Batch Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Land the already-written regression batches as separate commits, then continue adding small focused test batches until the project has one real run lifecycle Playwright E2E.

**Architecture:** Keep each batch narrow and independently verifiable. First preserve the existing round-1/2/3/4 test backfill as separate commits with their matching service fixes, then continue with the next highest-value gaps in API, hooks/components, and finally a browser-driven run lifecycle journey.

**Tech Stack:** Git, FastAPI, pytest, Next.js 16, React 19, Vitest, Playwright

### Task 1: Commit the existing round-1 batch

**Files:**
- Create: `backend/tests/test_services/test_run_helpers.py`
- Create: `backend/tests/test_services/test_trace_parser.py`
- Create: `backend/tests/test_services/test_project_workflow_service.py`
- Create: `frontend/tests/unit/components/run-stage-panel.test.tsx`
- Create: `frontend/tests/unit/components/run-error-card.test.tsx`
- Create: `frontend/tests/unit/root-page.test.tsx`
- Create: `docs/plans/2026-04-23-test-gap-backfill.md`

**Step 1: Stage only the round-1 files**

Run: `git add backend/tests/test_services/test_run_helpers.py backend/tests/test_services/test_trace_parser.py backend/tests/test_services/test_project_workflow_service.py frontend/tests/unit/components/run-stage-panel.test.tsx frontend/tests/unit/components/run-error-card.test.tsx frontend/tests/unit/root-page.test.tsx docs/plans/2026-04-23-test-gap-backfill.md`

**Step 2: Verify the round-1 suites**

Run: `cd backend && uv run python -m pytest tests/test_services/test_run_helpers.py tests/test_services/test_trace_parser.py tests/test_services/test_project_workflow_service.py -v`

Run: `cd frontend && bun run test -- run-stage-panel.test.tsx run-error-card.test.tsx root-page.test.tsx`

**Step 3: Commit the batch**

Run: `git commit -m "test: add initial service and run-status regressions"`

### Task 2: Commit the existing round-2 batch

**Files:**
- Modify: `backend/app/services/workflow_service.py`
- Create: `backend/tests/test_services/test_run_archive_service.py`
- Create: `backend/tests/test_services/test_workflow_service.py`
- Create: `backend/tests/test_services/test_run_dag_service.py`
- Create: `frontend/tests/unit/components/monitor-panel.test.tsx`
- Create: `frontend/tests/unit/components/live-deck.test.tsx`
- Create: `docs/plans/2026-04-23-test-gap-backfill-round-2.md`

**Step 1: Stage only the round-2 files**

Run: `git add backend/app/services/workflow_service.py backend/tests/test_services/test_run_archive_service.py backend/tests/test_services/test_workflow_service.py backend/tests/test_services/test_run_dag_service.py frontend/tests/unit/components/monitor-panel.test.tsx frontend/tests/unit/components/live-deck.test.tsx docs/plans/2026-04-23-test-gap-backfill-round-2.md`

**Step 2: Verify the round-2 suites**

Run: `cd backend && uv run python -m pytest tests/test_services/test_run_archive_service.py tests/test_services/test_workflow_service.py tests/test_services/test_run_dag_service.py -v`

Run: `cd frontend && bun run test -- monitor-panel.test.tsx live-deck.test.tsx`

**Step 3: Commit the batch**

Run: `git commit -m "test: cover archive workflow and dag services"`

### Task 3: Commit the existing round-3 batch

**Files:**
- Modify: `backend/app/services/dag_parser.py`
- Create: `backend/tests/test_services/test_dag_parser_service.py`
- Create: `frontend/tests/unit/components/workspace-panel.test.tsx`
- Create: `frontend/tests/unit/components/navbar.test.tsx`
- Create: `docs/plans/2026-04-23-test-gap-backfill-round-3.md`

**Step 1: Stage only the round-3 files**

Run: `git add backend/app/services/dag_parser.py backend/tests/test_services/test_dag_parser_service.py frontend/tests/unit/components/workspace-panel.test.tsx frontend/tests/unit/components/navbar.test.tsx docs/plans/2026-04-23-test-gap-backfill-round-3.md`

**Step 2: Verify the round-3 suites**

Run: `cd backend && uv run python -m pytest tests/test_services/test_dag_parser_service.py -v`

Run: `cd frontend && bun run test -- workspace-panel.test.tsx navbar.test.tsx`

**Step 3: Commit the batch**

Run: `git commit -m "test: lock dag parser and runtime nav panels"`

### Task 4: Commit the existing round-4 batch

**Files:**
- Modify: `backend/app/services/docker_service.py`
- Create: `backend/tests/test_services/test_docker_service.py`
- Create: `backend/tests/test_services/test_run_lifecycle_service.py`
- Create: `frontend/tests/unit/components/connection-status.test.tsx`
- Create: `docs/plans/2026-04-23-test-gap-backfill-round-4.md`

**Step 1: Stage only the round-4 files**

Run: `git add backend/app/services/docker_service.py backend/tests/test_services/test_docker_service.py backend/tests/test_services/test_run_lifecycle_service.py frontend/tests/unit/components/connection-status.test.tsx docs/plans/2026-04-23-test-gap-backfill-round-4.md`

**Step 2: Verify the round-4 suites**

Run: `cd backend && uv run python -m pytest tests/test_services/test_docker_service.py tests/test_services/test_run_lifecycle_service.py -v`

Run: `cd frontend && bun run test -- connection-status.test.tsx`

**Step 3: Commit the batch**

Run: `git commit -m "test: add docker and run lifecycle regression coverage"`

### Task 5: Cover the remaining backend API gaps

**Files:**
- Create: `backend/tests/test_api/test_events.py`
- Create: `backend/tests/test_api/test_providers.py`
- Create: `backend/tests/test_api/test_user_settings_api.py`
- Test: `backend/app/api/v1/events.py`
- Test: `backend/app/api/v1/providers.py`
- Test: `backend/app/api/v1/user_settings.py`

**Step 1: Write the failing API tests**

- Event stream auth/filtering and unsubscribe behavior
- Provider metadata envelope and credential-field shape
- User settings get/update/test-provider/models routes

**Step 2: Run focused pytest**

Run: `cd backend && uv run python -m pytest tests/test_api/test_events.py tests/test_api/test_providers.py tests/test_api/test_user_settings_api.py -v`

**Step 3: Fix only real failures if tests expose defects**

**Step 4: Re-run focused pytest**

Run: `cd backend && uv run python -m pytest tests/test_api/test_events.py tests/test_api/test_providers.py tests/test_api/test_user_settings_api.py -v`

**Step 5: Commit**

Run: `git add backend/tests/test_api/test_events.py backend/tests/test_api/test_providers.py backend/tests/test_api/test_user_settings_api.py`

Run: `git commit -m "test: cover remaining settings and event api routes"`

### Task 6: Cover the next hook/context gaps

**Files:**
- Create: `frontend/tests/unit/hooks/use-form-spec.test.ts`
- Create: `frontend/tests/unit/hooks/use-terminal-session.test.tsx`
- Create: `frontend/tests/unit/components/project-context.test.tsx`
- Create: `frontend/tests/unit/components/workspace-shell-context.test.tsx`

**Step 1: Write the failing tests**

- Form-spec hook request lifecycle and refetch guards
- Terminal-session hook/session bootstrap behavior
- Project/workspace context provider state transitions

**Step 2: Run focused Vitest**

Run: `cd frontend && bun run test -- use-form-spec.test.ts use-terminal-session.test.tsx project-context.test.tsx workspace-shell-context.test.tsx`

**Step 3: Fix only real failures if needed**

**Step 4: Re-run focused Vitest**

Run: `cd frontend && bun run test -- use-form-spec.test.ts use-terminal-session.test.tsx project-context.test.tsx workspace-shell-context.test.tsx`

**Step 5: Commit**

Run: `git add frontend/tests/unit/hooks/use-form-spec.test.ts frontend/tests/unit/hooks/use-terminal-session.test.tsx frontend/tests/unit/components/project-context.test.tsx frontend/tests/unit/components/workspace-shell-context.test.tsx`

Run: `git commit -m "test: cover form and workspace context hooks"`

### Task 7: Add a real run lifecycle Playwright E2E

**Files:**
- Create: `frontend/tests/e2e/run-lifecycle.spec.ts`
- Modify as needed: `frontend/tests/e2e/pages/runs-page.ts`
- Modify as needed: `frontend/tests/e2e/pages/workflows-page.ts`
- Modify as needed: `frontend/tests/e2e/pages/agent-page.ts`
- Modify as needed: local dev/test launch instructions if Playwright needs a stable command

**Step 1: Design the smallest true lifecycle journey**

- Seed or create a project/workflow through the real app/backend
- Launch a run through the UI
- Observe state transition on the runs or run-detail surface
- Verify at least one lifecycle action/result in the browser without API mocking

**Step 2: Write the failing Playwright test**

Run: `cd frontend && bunx playwright test tests/e2e/run-lifecycle.spec.ts --project=chromium`

**Step 3: Fix only real product or selector issues**

**Step 4: Re-run the focused Playwright E2E**

Run: `cd frontend && bunx playwright test tests/e2e/run-lifecycle.spec.ts --project=chromium`

**Step 5: Re-run the expanded verification set**

Run: `cd backend && uv run python -m pytest tests/test_api/test_events.py tests/test_api/test_providers.py tests/test_api/test_user_settings_api.py -v`

Run: `cd frontend && bun run test -- use-form-spec.test.ts use-terminal-session.test.tsx project-context.test.tsx workspace-shell-context.test.tsx`

Run: `cd frontend && bunx playwright test tests/e2e/core-navigation.spec.ts tests/e2e/run-lifecycle.spec.ts --project=chromium`

**Step 6: Commit**

Run: `git add frontend/tests/e2e/run-lifecycle.spec.ts frontend/tests/e2e/pages/runs-page.ts frontend/tests/e2e/pages/workflows-page.ts frontend/tests/e2e/pages/agent-page.ts`

Run: `git commit -m "test: add run lifecycle browser coverage"`
