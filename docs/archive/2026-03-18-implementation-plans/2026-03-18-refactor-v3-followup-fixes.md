# Refactor V3 Follow-Up Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix four confirmed behavior bugs in the refactor-v3 scheduler/batch/notification paths, prove each with regression tests, and commit the patch set.

**Architecture:** Keep the current API -> scheduler -> backend -> adapter layering intact. Apply the smallest possible code changes at the behavior boundaries that are already responsible for run terminal handling, WDL output materialization, batch state aggregation, and webhook delivery semantics.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy async, pytest, httpx, asyncio

### Task 1: Scheduler Terminal DAG Finalization

**Files:**
- Modify: `backend/tests/test_scheduler/test_scheduler.py`
- Modify: `backend/app/scheduler/scheduler.py`

**Step 1: Write the failing test**

Add a regression test that drives a run through the scheduler with a backend emitting a task update and then an error. Assert the run becomes failed and the DAG no longer contains `running` nodes after terminal handling. Add a second assertion path for cancellation if needed, but keep the first test focused on failure finalization.

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_scheduler/test_scheduler.py::test_scheduler_finalizes_dag_on_failure -q`

Expected: FAIL because failed runs do not currently finalize DAG state.

**Step 3: Write minimal implementation**

Update scheduler terminal failure/cancel paths to call `_finalize_dag_statuses()` when a DAG exists, commit the final config, and publish the DAG update just like the success path already does.

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_scheduler/test_scheduler.py::test_scheduler_finalizes_dag_on_failure -q`

Expected: PASS

### Task 2: WDL Resume Output Copy

**Files:**
- Modify: `backend/tests/test_engine/test_wdl_adapter.py`
- Modify: `backend/app/engine/adapters/wdl.py`

**Step 1: Write the failing test**

Add a regression test that sets `resume_work_dir` to a shared directory, writes an output file under that resumed work dir, calls `post_complete()`, and asserts the file is copied into the configured outdir.

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_engine/test_wdl_adapter.py::test_wdl_adapter_post_complete_uses_resume_work_dir_when_present -q`

Expected: FAIL because `post_complete()` currently reads from `.bioinfoflow/miniwdl/{run_id}` instead of the resumed work dir.

**Step 3: Write minimal implementation**

Resolve the effective WDL work directory from `resume_work_dir` when present, otherwise fall back to the run-id-based default path, and reuse that helper for output copying.

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_engine/test_wdl_adapter.py::test_wdl_adapter_post_complete_uses_resume_work_dir_when_present -q`

Expected: PASS

### Task 3: Batch Running Status Aggregation

**Files:**
- Modify: `backend/tests/test_services/test_batch.py`
- Modify: `backend/app/services/batch_service.py`

**Step 1: Write the failing test**

Add a regression test proving a batch with linked runs still in active states reports `running` rather than `pending`.

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_services/test_batch.py::test_update_batch_status_marks_active_batches_running -q`

Expected: FAIL because the current aggregator returns `pending` when all observed runs are active.

**Step 3: Write minimal implementation**

Adjust `_derive_status()` so any batch with `active > 0` reports `running`, except the true zero-progress case where there are no linked runs yet and the batch remains `pending`.

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_services/test_batch.py::test_update_batch_status_marks_active_batches_running -q`

Expected: PASS

### Task 4: Webhook HTTP Failure Handling

**Files:**
- Modify: `backend/tests/test_services/test_notifications.py`
- Modify: `backend/app/services/notification_service.py`

**Step 1: Write the failing test**

Add a regression test that simulates an HTTP 500 response from the webhook client and asserts the service logs the delivery failure instead of treating the request as success.

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_services/test_notifications.py::test_notify_logs_http_status_failures -q`

Expected: FAIL because `_send_webhook()` does not currently call `raise_for_status()`.

**Step 3: Write minimal implementation**

Capture the response from `client.post(...)` and call `response.raise_for_status()` so 4xx/5xx paths are handled by the existing exception logging branch.

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_services/test_notifications.py::test_notify_logs_http_status_failures -q`

Expected: PASS

### Task 5: Regression Verification And Commit

**Files:**
- Review: `backend/app/scheduler/scheduler.py`
- Review: `backend/app/engine/adapters/wdl.py`
- Review: `backend/app/services/batch_service.py`
- Review: `backend/app/services/notification_service.py`
- Review: `backend/tests/test_scheduler/test_scheduler.py`
- Review: `backend/tests/test_engine/test_wdl_adapter.py`
- Review: `backend/tests/test_services/test_batch.py`
- Review: `backend/tests/test_services/test_notifications.py`

**Step 1: Run focused test set**

Run: `cd backend && uv run pytest tests/test_scheduler/test_scheduler.py tests/test_engine/test_wdl_adapter.py tests/test_services/test_batch.py tests/test_services/test_notifications.py -q`

Expected: PASS

**Step 2: Run broader touched-area regressions**

Run: `cd backend && uv run pytest tests/test_scheduler/test_retry.py tests/test_scheduler/test_timeout.py tests/test_scheduler/test_hooks_phase6.py tests/test_api/test_run_lifecycle.py -q`

Expected: PASS

**Step 3: Review diff**

Run: `git diff --stat && git diff -- backend/app/scheduler/scheduler.py backend/app/engine/adapters/wdl.py backend/app/services/batch_service.py backend/app/services/notification_service.py backend/tests/test_scheduler/test_scheduler.py backend/tests/test_engine/test_wdl_adapter.py backend/tests/test_services/test_batch.py backend/tests/test_services/test_notifications.py docs/plans/2026-03-18-refactor-v3-followup-fixes.md`

Expected: Only the planned files change, and each change maps directly to one regression.

**Step 4: Commit**

Run:

```bash
git add docs/plans/2026-03-18-refactor-v3-followup-fixes.md \
  backend/app/scheduler/scheduler.py \
  backend/app/engine/adapters/wdl.py \
  backend/app/services/batch_service.py \
  backend/app/services/notification_service.py \
  backend/tests/test_scheduler/test_scheduler.py \
  backend/tests/test_engine/test_wdl_adapter.py \
  backend/tests/test_services/test_batch.py \
  backend/tests/test_services/test_notifications.py
git commit -m "fix: patch refactor v3 scheduler follow-ups"
```
