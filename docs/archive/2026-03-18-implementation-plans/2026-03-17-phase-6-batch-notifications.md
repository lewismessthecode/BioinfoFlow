# Phase 6 Batch Submission And Notifications Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add batch run submission, batch state aggregation, and best-effort webhook notifications for run and batch completion without breaking the existing run lifecycle APIs.

**Architecture:** Introduce `Batch`, `BatchRun`, and `NotificationConfig` persistence models plus service-layer orchestration for batch creation, cancellation, and status recomputation. Extend scheduler completion hooks to update batch state and trigger webhook delivery, then expose the new capability through `/runs/batch` and `/notifications` endpoints.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, SQLite, httpx, pytest, asyncio

### Task 1: Batch and notification persistence

**Files:**
- Create: `backend/app/models/batch.py`
- Create: `backend/app/models/notification.py`
- Create: `backend/app/repositories/batch_repo.py`
- Create: `backend/app/repositories/notification_repo.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/alembic/versions/0007_batches_and_notifications.py`
- Test: `backend/tests/test_services/test_batch.py`
- Test: `backend/tests/test_services/test_notifications.py`

**Step 1: Write the failing tests**

Add tests that assert batch state aggregation from linked runs and notification config filtering by project, trigger, and enabled flag.

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_services/test_batch.py tests/test_services/test_notifications.py -v`
Expected: FAIL because the new models, repositories, and services do not exist yet.

**Step 3: Write minimal implementation**

Add the new ORM models, repository helpers, and migration so the database can persist batches, batch-to-run links, and webhook notification configs.

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_services/test_batch.py tests/test_services/test_notifications.py -v`
Expected: PASS

### Task 2: Batch and notification services

**Files:**
- Create: `backend/app/services/batch_service.py`
- Create: `backend/app/services/notification_service.py`
- Modify: `backend/app/services/run_service.py`
- Test: `backend/tests/test_services/test_batch.py`
- Test: `backend/tests/test_services/test_notifications.py`

**Step 1: Write the failing tests**

Add service tests for mixed-validity batch creation, batch cancellation, batch status recomputation, webhook delivery payloads, and best-effort failure logging.

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_services/test_batch.py tests/test_services/test_notifications.py -v`
Expected: FAIL because the orchestration logic is missing.

**Step 3: Write minimal implementation**

Implement `BatchService` and `NotificationService`, reusing `RunService.create_run` for single-run validation/creation and `RunService.cancel_run` for batch cancellation.

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_services/test_batch.py tests/test_services/test_notifications.py -v`
Expected: PASS

### Task 3: Hook integration for run completion

**Files:**
- Modify: `backend/app/scheduler/hooks.py`
- Test: `backend/tests/test_scheduler/test_hooks.py`
- Test: `backend/tests/test_scheduler/test_hooks_phase6.py`

**Step 1: Write the failing tests**

Add hook tests asserting run completion triggers audit logging, best-effort run notifications, batch state updates, and one batch-complete notification when a batch reaches a terminal aggregate state.

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_scheduler/test_hooks.py tests/test_scheduler/test_hooks_phase6.py -v`
Expected: FAIL because the hooks only perform cleanup and audit logging today.

**Step 3: Write minimal implementation**

Extend `RunCompletionHooks` to coordinate cleanup, audit logging, notification delivery, and batch aggregation while keeping notification failures non-fatal.

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_scheduler/test_hooks.py tests/test_scheduler/test_hooks_phase6.py -v`
Expected: PASS

### Task 4: API surface for batch and notifications

**Files:**
- Create: `backend/app/api/v1/batch.py`
- Create: `backend/app/api/v1/notifications.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/app/schemas/run.py`
- Create: `backend/app/schemas/notification.py`
- Test: `backend/tests/test_api/test_batch_api.py`

**Step 1: Write the failing tests**

Add API tests covering batch creation, batch lookup, batch cancellation, notification config create/list/delete, and validation for batch size and payload shape.

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_api/test_batch_api.py -v`
Expected: FAIL because the routes and schemas do not exist yet.

**Step 3: Write minimal implementation**

Add the new request/response schemas, routes, and router wiring for `/runs/batch` and `/notifications`.

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_api/test_batch_api.py -v`
Expected: PASS

### Task 5: Regression verification, review, and commit

**Files:**
- Test: `backend/tests/test_api/test_run_lifecycle.py`
- Test: `backend/tests/test_scheduler/test_scheduler.py`
- Test: `backend/tests/test_services/test_batch.py`
- Test: `backend/tests/test_services/test_notifications.py`
- Test: `backend/tests/test_scheduler/test_hooks.py`
- Test: `backend/tests/test_scheduler/test_hooks_phase6.py`
- Test: `backend/tests/test_api/test_batch_api.py`

**Step 1: Run focused regression tests**

Run: `cd backend && uv run pytest tests/test_services/test_batch.py tests/test_services/test_notifications.py tests/test_scheduler/test_hooks.py tests/test_scheduler/test_hooks_phase6.py tests/test_api/test_batch_api.py tests/test_api/test_run_lifecycle.py tests/test_scheduler/test_scheduler.py -v`
Expected: PASS

**Step 2: Run full backend verification**

Run: `cd backend && uv run pytest`
Expected: PASS

Run: `cd backend && uv run ruff check .`
Expected: PASS

**Step 3: Review and commit**

Review the diff for transaction boundaries, duplicate batch-complete notifications, cancellation edge cases, and API compatibility, then commit with a phase-6-specific message.
