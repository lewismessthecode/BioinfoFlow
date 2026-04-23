# Continued Test Gap Backfill Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Continue filling the highest-value remaining test gaps by covering DAG parsing logic and direct tests for the workspace/browser navigation surfaces that still lack dedicated protection.

**Architecture:** Prefer direct unit/service tests where behavior is compact but branching, and add focused component tests for primary user-facing panels rather than broad page-level integration. Use TDD to lock in any newly discovered behavior bugs, especially around DAG animation semantics.

**Tech Stack:** FastAPI, pytest, Next.js 16, React 19, Vitest, Testing Library

### Task 1: DAG parser coverage

**Files:**
- Create: `backend/tests/test_services/test_dag_parser_service.py`
- Modify: `backend/app/services/dag_parser.py`

**Step 1: Write parser tests**

- Missing DOT file returns an empty DAG
- DOT parsing cleans process labels and schema tasks
- `update_node_status` updates the normalized target node
- `update_edge_animations` only animates edges whose source node is running

**Step 2: Run focused pytest and fix the animation bug**

Run: `cd backend && uv run python -m pytest tests/test_services/test_dag_parser_service.py -v`

### Task 2: Workspace panel coverage

**Files:**
- Create: `frontend/tests/unit/components/workspace-panel.test.tsx`
- Test: `frontend/components/bioinfoflow/workspace-panel.tsx`

**Step 1: Add direct panel tests**

- No active project short-circuits API loading
- Root file listing hides dotfiles
- Folder expansion loads child nodes
- File preview and download actions call the expected APIs/helpers

**Step 2: Run focused Vitest**

Run: `cd frontend && bun run test -- workspace-panel.test.tsx`

### Task 3: Navbar coverage

**Files:**
- Create: `frontend/tests/unit/components/navbar.test.tsx`
- Test: `frontend/components/bioinfoflow/navbar.tsx`

**Step 1: Add direct navbar tests**

- Help action opens docs
- Theme toggle flips between light and dark
- Auth-disabled sign out routes back to `/agent`
- Hamburger button calls `onSidebarToggle`

**Step 2: Run focused Vitest**

Run: `cd frontend && bun run test -- navbar.test.tsx`

### Task 4: Verification

**Files:**
- Modify: `docs/plans/2026-04-23-test-gap-backfill-round-3.md`

**Step 1: Re-run the new suites together**

Run the backend parser tests and the frontend component tests in one pass.

**Step 2: Keep the next queue focused**

Record the next highest-risk uncovered modules after this batch.
