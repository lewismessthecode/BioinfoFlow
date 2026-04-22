# Phase 2 Persistent Run Scheduler Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move run execution from the in-memory task runner to a DB-backed scheduler while keeping legacy mode and non-run background tasks intact.

**Architecture:** Add a `scheduled_tasks` persistence layer plus a `RunScheduler` that owns queueing, recovery, and worker execution. Wire `RunService` through dispatcher/scheduler globals so create/resume/retry/cancel can switch between legacy and persistent modes without changing the API surface.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, SQLite, pytest, asyncio

### Task 1: Scheduler persistence model and queue

**Files:**
- Create: `backend/app/scheduler/__init__.py`
- Create: `backend/app/scheduler/config.py`
- Create: `backend/app/scheduler/models.py`
- Create: `backend/app/scheduler/queue.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/alembic/versions/0005_scheduled_tasks.py`
- Test: `backend/tests/test_scheduler/test_queue.py`

**Step 1: Write the failing tests**

Add queue tests that assert enqueue/dequeue ordering, queue depth enforcement, and queued-task cancellation persistence.

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_scheduler/test_queue.py -v`
Expected: FAIL because the scheduler package and `scheduled_tasks` model do not exist yet.

**Step 3: Write minimal implementation**

Add `ScheduledTask`, priority/state enums, a DB-backed `TaskQueue`, and the migration/model exports needed for table creation.

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_scheduler/test_queue.py -v`
Expected: PASS

### Task 2: RunScheduler core behavior

**Files:**
- Create: `backend/app/scheduler/scheduler.py`
- Modify: `backend/app/runtime/jobs.py`
- Modify: `backend/app/services/run_dispatch.py`
- Modify: `backend/app/services/run_service.py`
- Test: `backend/tests/test_scheduler/test_scheduler.py`
- Test: `backend/tests/test_scheduler/test_recovery.py`

**Step 1: Write the failing tests**

Add scheduler tests for persistent enqueue/dispatch execution, stale dispatched recovery, max queue depth, and queued/dispatched cancellation.

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_scheduler/test_scheduler.py tests/test_scheduler/test_recovery.py -v`
Expected: FAIL because `RunScheduler` and persistent dispatcher integration do not exist yet.

**Step 3: Write minimal implementation**

Implement `RunScheduler`, scheduler dispatcher/global accessors, and move run execution/recovery orchestration behind the scheduler while keeping legacy wrappers for `jobs.py`.

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_scheduler/test_scheduler.py tests/test_scheduler/test_recovery.py -v`
Expected: PASS

### Task 3: App wiring and scheduler status endpoint

**Files:**
- Create: `backend/app/api/v1/scheduler.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_api/test_scheduler.py`

**Step 1: Write the failing tests**

Add API tests covering the new `/api/v1/scheduler/status` response and feature-flagged legacy/persistent wiring.

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_api/test_scheduler.py -v`
Expected: FAIL because the route and startup wiring do not exist yet.

**Step 3: Write minimal implementation**

Add scheduler config fields, initialize/stop the persistent scheduler in app lifespan, keep legacy mode available, and expose scheduler status via a new API route.

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_api/test_scheduler.py -v`
Expected: PASS

### Task 4: Regression verification and commit

**Files:**
- Test: `backend/tests/test_api/test_runs.py`
- Test: `backend/tests/test_api/test_run_lifecycle.py`
- Test: `backend/tests/test_runtime/test_run_recovery.py`

**Step 1: Run focused regression tests**

Run: `cd backend && uv run pytest tests/test_api/test_runs.py tests/test_api/test_run_lifecycle.py tests/test_runtime/test_run_recovery.py -v`
Expected: PASS

**Step 2: Run full backend verification**

Run: `cd backend && uv run pytest`
Expected: PASS

Run: `cd backend && .venv/bin/ruff check app tests`
Expected: PASS

**Step 3: Review and commit**

Review the diff for scheduler state drift, recovery edge cases, and legacy-mode regressions, then commit with a phase-2-specific message.
