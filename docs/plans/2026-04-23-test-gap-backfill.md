# Test Gap Backfill Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add focused regression coverage for currently under-tested backend helper/parser logic and frontend run-status UI surfaces.

**Architecture:** Use existing pytest and Vitest patterns to add narrow, behavior-oriented tests around pure functions, small services, and route/component regressions. Prioritize modules with real branching logic but no direct test files, and prefer deterministic unit coverage over broad end-to-end setup.

**Tech Stack:** FastAPI, pytest, SQLAlchemy async session, Next.js App Router, Vitest, Testing Library

### Task 1: Backend pure helpers

**Files:**
- Create: `backend/tests/test_services/test_run_helpers.py`
- Test: `backend/app/services/run_helpers.py`

**Step 1: Write focused helper tests**

Cover path resolution, resume token precedence, mock DAG state derivation, and samplesheet validation.

**Step 2: Run targeted pytest**

Run: `cd backend && uv run pytest tests/test_services/test_run_helpers.py -v`

**Step 3: Adjust only if behavior mismatches intended contract**

Keep production changes minimal and only if a failing test reveals a real regression.

### Task 2: Backend parser and workflow binding service

**Files:**
- Create: `backend/tests/test_services/test_trace_parser.py`
- Create: `backend/tests/test_services/test_project_workflow_service.py`
- Test: `backend/app/services/trace_parser.py`
- Test: `backend/app/services/project_workflow_service.py`

**Step 1: Add parser coverage**

Cover missing files, row parsing, process-name normalization, and process status prioritization.

**Step 2: Add project workflow service coverage**

Cover pin selection/grouping and dangling binding cleanup when a workflow row has already been deleted.

**Step 3: Run targeted pytest**

Run: `cd backend && uv run pytest tests/test_services/test_trace_parser.py tests/test_services/test_project_workflow_service.py -v`

### Task 3: Frontend run feedback surfaces

**Files:**
- Create: `frontend/tests/unit/components/run-stage-panel.test.tsx`
- Create: `frontend/tests/unit/components/run-error-card.test.tsx`
- Create: `frontend/tests/unit/root-page.test.tsx`
- Test: `frontend/components/bioinfoflow/run-stage-panel.tsx`
- Test: `frontend/components/bioinfoflow/run-error-card.tsx`
- Test: `frontend/app/page.tsx`

**Step 1: Add component tests**

Cover active/terminal rendering, current-task messaging, translated stage badges, and null-state rendering.

**Step 2: Add root redirect regression test**

Assert the root page redirects to `/auth`.

**Step 3: Run targeted Vitest**

Run: `cd frontend && bun run test -- run-stage-panel.test.tsx run-error-card.test.tsx root-page.test.tsx`

### Task 4: Verification and summary

**Files:**
- Modify: `docs/plans/2026-04-23-test-gap-backfill.md`

**Step 1: Re-run all newly added tests together**

Run backend and frontend targeted commands again after any fixes.

**Step 2: Summarize remaining notable gaps**

Call out high-risk modules still lacking direct coverage so follow-up work stays focused.
