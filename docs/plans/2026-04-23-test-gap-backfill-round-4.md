# Continued Test Gap Backfill Round 4 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend necessary regression coverage into the next highest-value untested modules, focusing on Docker image parsing/lifecycle helpers, direct run lifecycle service behaviors, and the remaining lightweight connection status UI surface.

**Architecture:** Prefer direct unit/service tests around deterministic branching logic rather than broad integration setup. Follow TDD for any bugfixes uncovered by the new tests, especially for Docker image name parsing where registry ports can be confused with tags.

**Tech Stack:** FastAPI, pytest, Next.js 16, React 19, Vitest, Testing Library

### Task 1: Docker service coverage and parsing hardening

**Files:**
- Create: `backend/tests/test_services/test_docker_service.py`
- Modify: `backend/app/services/docker_service.py`

**Step 1: Write failing Docker service tests**

- `_split_tag` keeps `localhost:5000/repo` as an untagged image and defaults to `latest`
- `list_images` normalizes registry/name/tag metadata from Docker SDK objects
- `inspect_image` returns `None` for missing images
- `delete_image` returns `False` on Docker API errors

**Step 2: Run focused pytest to confirm the current failure**

Run: `cd backend && uv run python -m pytest tests/test_services/test_docker_service.py -v`

**Step 3: Apply the minimal production fix**

- Harden `_split_tag` so registry ports are not mistaken for image tags
- Keep the rest of the behavior unchanged

**Step 4: Re-run focused pytest**

Run: `cd backend && uv run python -m pytest tests/test_services/test_docker_service.py -v`

### Task 2: Direct run lifecycle service coverage

**Files:**
- Create: `backend/tests/test_services/test_run_lifecycle_service.py`
- Test: `backend/app/services/run_lifecycle_service.py`

**Step 1: Add targeted service tests**

- `cleanup_run` forwards workspace/runtime details to `WorkDirCleaner` and audits the result
- `get_logs` falls back to the resolved workspace when the default audit log path is absent
- `append_run_log` persists a relative `log_path` and appends newline-delimited entries

**Step 2: Run focused pytest**

Run: `cd backend && uv run python -m pytest tests/test_services/test_run_lifecycle_service.py -v`

### Task 3: Connection status component coverage

**Files:**
- Create: `frontend/tests/unit/components/connection-status.test.tsx`
- Test: `frontend/components/bioinfoflow/connection-status.tsx`

**Step 1: Add direct component tests**

- Connected state exposes an accessible label even when the inline text is hidden
- Connecting/reconnecting states show visible status text and animated indicator styling
- Disconnected state keeps the correct tooltip/status copy

**Step 2: Run focused Vitest**

Run: `cd frontend && bun run test -- connection-status.test.tsx`

### Task 4: Verification

**Files:**
- Modify: `docs/plans/2026-04-23-test-gap-backfill-round-4.md`

**Step 1: Re-run the new round-4 suites together**

Run the new backend service tests and the new frontend component test in one pass.

**Step 2: Re-run the full expanded backfill suite**

Verify the earlier round-1/2/3 tests together with the new round-4 coverage.

**Step 3: Record the next uncovered queue**

Keep the next gap list focused on remaining high-risk modules such as `run_dispatch`, `run_submission_service`, and missing frontend hook coverage.

## Verification Notes

- Focused backend: `cd backend && uv run python -m pytest tests/test_services/test_docker_service.py -v`
- Focused backend: `cd backend && uv run python -m pytest tests/test_services/test_run_lifecycle_service.py -v`
- Focused frontend: `cd frontend && bun run test -- connection-status.test.tsx`
- Round-4 backend bundle: `cd backend && uv run python -m pytest tests/test_services/test_docker_service.py tests/test_services/test_run_lifecycle_service.py -v`
- Round-4 frontend bundle: `cd frontend && bun run test -- connection-status.test.tsx`
- Expanded backend backfill suite: `cd backend && uv run python -m pytest tests/test_services/test_run_helpers.py tests/test_services/test_trace_parser.py tests/test_services/test_project_workflow_service.py tests/test_services/test_run_archive_service.py tests/test_services/test_workflow_service.py tests/test_services/test_run_dag_service.py tests/test_services/test_dag_parser_service.py tests/test_services/test_docker_service.py tests/test_services/test_run_lifecycle_service.py -v`
- Expanded frontend backfill suite: `cd frontend && bun run test -- run-stage-panel.test.tsx run-error-card.test.tsx root-page.test.tsx monitor-panel.test.tsx live-deck.test.tsx workspace-panel.test.tsx navbar.test.tsx connection-status.test.tsx`

## Outcome

- Found and fixed a real `docker_service` defect where registry ports like `localhost:5000/...` were misread as tags, and non-default registries were dropped from `full_name`.
- Added direct service coverage for `RunLifecycleService` cleanup/logging behaviors that API tests were not locking down.
- Added direct component coverage for `ConnectionStatus` to protect the accessibility fix from future regressions.

## Next Queue

- Backend: `run_dispatch.py`, `run_submission_service.py`, `batch_service.py`
- Frontend hooks: `use-chat-actions`, `use-chat-messages`, `use-dag-positions`, `use-llm-settings`
- Frontend components: `command-palette`, `chat-stream`, higher-traffic sidebar surfaces
