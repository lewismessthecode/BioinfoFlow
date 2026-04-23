# Expanded Test Gap Backfill Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add broader regression coverage for high-risk backend services and missing frontend runtime panels that previous review passes still flagged as under-tested.

**Architecture:** Prioritize core workflow/run services over low-risk presentation components. Use direct service tests for branching logic and safety boundaries, then add lightweight frontend unit tests for missing live-status surfaces so regressions are caught without expensive page setup.

**Tech Stack:** FastAPI, SQLAlchemy async session, pytest, Next.js 16, React 19, Vitest, Testing Library

### Task 1: Run archive service coverage

**Files:**
- Create: `backend/tests/test_services/test_run_archive_service.py`
- Test: `backend/app/services/run_archive.py`

**Step 1: Write failing/coverage tests**

- Redaction and archive document override behavior
- Output listing ignores symlinks and builds asset URIs
- Archive generation refuses unsafe symlink targets
- Output deletion removes persisted results

**Step 2: Run focused pytest**

Run: `cd backend && uv run python -m pytest tests/test_services/test_run_archive_service.py -v`

### Task 2: Workflow service coverage and path hardening

**Files:**
- Create: `backend/tests/test_services/test_workflow_service.py`
- Modify: `backend/app/services/workflow_service.py`

**Step 1: Write failing workflow path-safety test**

- Prove local workflow creation rejects absolute entrypoint paths instead of writing outside the bundle root

**Step 2: Add coverage for lifecycle behavior**

- Updating schema rebuilds form spec
- Deleting local workflows removes local bundle files
- Resolving source path enforces local-only bundle access

**Step 3: Run focused pytest and implement the minimal fix**

Run: `cd backend && uv run python -m pytest tests/test_services/test_workflow_service.py -v`

### Task 3: Run DAG service coverage

**Files:**
- Create: `backend/tests/test_services/test_run_dag_service.py`
- Test: `backend/app/services/run_dag_service.py`

**Step 1: Add direct service tests**

- `get_dag` falls back to workflow schema when run config lacks a stored DAG
- `repair_run_dag(..., dry_run=True)` reports repairs without persisting them
- Mock DAG variant creation deduplicates variants and validates unsupported inputs

**Step 2: Run focused pytest**

Run: `cd backend && uv run python -m pytest tests/test_services/test_run_dag_service.py -v`

### Task 4: Frontend live panel coverage

**Files:**
- Create: `frontend/tests/unit/components/monitor-panel.test.tsx`
- Create: `frontend/tests/unit/components/live-deck.test.tsx`
- Test: `frontend/components/bioinfoflow/monitor-panel.tsx`
- Test: `frontend/components/bioinfoflow/live-deck.tsx`

**Step 1: Add focused unit tests**

- Monitor panel reacts to incoming run status events and computes progress
- Live deck renders the selected panel and forwards collapse/tab actions

**Step 2: Run focused Vitest**

Run: `cd frontend && bun run test -- monitor-panel.test.tsx live-deck.test.tsx`

### Task 5: Verification and follow-up gaps

**Files:**
- Modify: `docs/plans/2026-04-23-test-gap-backfill-round-2.md`

**Step 1: Re-run all newly added tests together**

Run backend and frontend focused commands after fixes.

**Step 2: Summarize remaining high-risk modules**

Keep the next wave focused on the largest uncovered services and missing API/websocket auth edges.
