# Phase 1 Engine Abstraction Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Introduce an engine adapter/backend layer so run execution, cancel, and resume logic no longer branch directly on workflow engine implementations.

**Architecture:** Add `app.engine` with a unified `EngineEvent`, adapter registry, and a local subprocess backend. Migrate Nextflow and MiniWDL parsing/command logic into adapters, keep legacy services as thin compatibility wrappers, then switch `runtime/jobs.py` and `services/run_service.py` to the new interfaces while preserving current API and SSE behavior.

**Tech Stack:** FastAPI, async SQLAlchemy, asyncio subprocesses, pytest, pytest-asyncio

### Task 1: Lock the engine contract with tests

**Files:**
- Create: `backend/tests/test_engine/test_engine_event.py`
- Create: `backend/tests/test_engine/test_registry.py`
- Create: `backend/tests/test_engine/test_nextflow_adapter.py`
- Create: `backend/tests/test_engine/test_wdl_adapter.py`
- Create: `backend/tests/test_engine/test_local_backend.py`
- Modify: `backend/tests/test_services/test_phase0_seams.py`

**Step 1: Write the failing tests**

Cover:
- `EngineEvent` typed accessors
- Registry lookup and unknown engine failure
- Nextflow adapter command building, resume token handling, parsing, Docker pre-submit mutation
- WDL adapter command building, parsing, output copy hook
- Local backend subprocess event flow and non-zero exit handling
- Run service cancel/resume/binary checks through adapter lookup

**Step 2: Run the focused tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_engine tests/test_services/test_phase0_seams.py -v`

Expected:
- import failures for `app.engine.*`
- seam test failures because `RunService` still branches on legacy services

### Task 2: Implement the engine package

**Files:**
- Create: `backend/app/engine/__init__.py`
- Create: `backend/app/engine/adapter.py`
- Create: `backend/app/engine/backend.py`
- Create: `backend/app/engine/local.py`
- Create: `backend/app/engine/registry.py`
- Create: `backend/app/engine/adapters/__init__.py`
- Create: `backend/app/engine/adapters/nextflow.py`
- Create: `backend/app/engine/adapters/wdl.py`

**Step 1: Write the minimal implementation**

Implement:
- `EngineEventType` + immutable `EngineEvent`
- `EngineAdapter` and `ExecutionBackend` ABCs
- `LocalBackend.submit()` with pre-submit hook, subprocess execution, stream draining, terminal event handling, and post-complete hook
- `NextflowAdapter` and `WDLAdapter` by moving the command, parsing, resume, cancel, and output-copy logic from the legacy services
- registry helpers with default Nextflow/WDL registration

**Step 2: Run focused engine tests**

Run: `cd backend && uv run pytest tests/test_engine -v`

Expected: PASS

### Task 3: Switch runtime and services to the new abstraction

**Files:**
- Modify: `backend/app/runtime/jobs.py`
- Modify: `backend/app/services/run_service.py`
- Modify: `backend/app/services/nextflow_service.py`
- Modify: `backend/app/services/miniwdl_service.py`
- Modify: `backend/app/models/run_config.py`

**Step 1: Replace engine-specific branches**

Implement:
- `runtime/jobs.py` calling `get_adapter()` + `LocalBackend()`
- `_handle_run_event()` converted to `EngineEvent`
- `RunConfigHelper.to_dict()` to produce a structured config copy for adapters
- `RunService.cancel_run()`, `_require_engine_binary()`, and `resume_run()` through adapters
- legacy services delegating internally to adapters/backend while preserving current call signatures

**Step 2: Run targeted regression tests**

Run:
- `cd backend && uv run pytest tests/test_services/test_run_service.py tests/test_services/test_execution.py tests/test_runtime/test_dag_status.py tests/test_api/test_run_lifecycle.py tests/test_api/test_runs.py -v`

Expected: PASS

### Task 4: Verify, review, and commit

**Files:**
- Review all modified files from Tasks 1-3

**Step 1: Run full backend verification**

Run:
- `cd backend && uv run pytest`
- `cd backend && .venv/bin/ruff check app tests`

Expected: PASS

**Step 2: Review and commit**

Review for:
- engine branches removed from `execute_run()` and `cancel_run()`
- no SSE/status regressions in event handling
- wrapper services still preserve compatibility for existing callers/tests

Commit:
- `git add docs/plans/2026-03-17-phase-1-engine-abstraction.md backend/app/engine backend/app/models/run_config.py backend/app/runtime/jobs.py backend/app/services/miniwdl_service.py backend/app/services/nextflow_service.py backend/app/services/run_service.py backend/tests/test_engine backend/tests/test_services/test_execution.py backend/tests/test_services/test_phase0_seams.py`
- `git commit -m "backend: implement refactor v3 phase 1 engine abstraction"`
