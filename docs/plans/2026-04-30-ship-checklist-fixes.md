# Ship Checklist Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the release blockers found while checking `docs/SHIP_CHECKLIST.md` and commit them in focused batches.

**Architecture:** Keep fixes close to the failing contracts: backend run validation/log behavior, frontend storage-source mapping, and local Docker readiness. Do not refactor unrelated services.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, Next.js, Vitest, Docker Compose.

## Task 1: Backend Run Validation And Logs

**Files:**
- Modify: `backend/app/services/run_compiler.py`
- Modify: `backend/app/services/run_lifecycle_service.py`
- Modify tests only if an existing expectation is stale.

**Steps:**
1. Reproduce the focused backend failures:
   `cd backend && uv run pytest tests/test_api/test_runs.py::test_runs_create_rejects_paths_outside_field_allow_roots tests/test_api/test_runs_artifacts.py::test_runs_artifact_endpoints_return_not_found_when_missing -q`
2. Trace why a `source_hint: reference` field without explicit `allow_roots` accepts a project path.
3. Preserve explicit `allow_roots`, but infer roots from `source_hint` when a schema field omitted them.
4. Make completed-run missing logs return a not-found error while pending/running runs can still return an empty log list before the log file exists.
5. Verify the focused backend tests.
6. Commit as `fix: enforce run storage contracts`.

## Task 2: Backend Auth Default Isolation

**Files:**
- Modify: `backend/app/config.py` or test fixture code only if root cause shows environment state leaks into `Settings(_env_file=None)`.
- Test: `backend/tests/test_auth/test_config_defaults.py`

**Steps:**
1. Reproduce the full-suite-only auth default failure or prove it is fixed after Task 1.
2. If still failing, isolate environment reads so `Settings(_env_file=None)` has deterministic defaults.
3. Verify `cd backend && uv run pytest tests/test_auth/test_config_defaults.py -q`.
4. Include in the backend commit if code changed.

## Task 3: Frontend Storage Source Mapping

**Files:**
- Modify: `frontend/tests/unit/lib/storage-source-policy.test.ts` if the product contract now includes `database`.
- Or modify: `frontend/lib/storage-source-policy.ts` if `database` should not be offered for `any_allowed_root`.

**Steps:**
1. Reproduce: `cd frontend && bun run test tests/unit/lib/storage-source-policy.test.ts`.
2. Compare frontend mapping with backend `any_allowed_root`, which includes project, deliveries, reference, and database.
3. Update the stale side so both layers agree.
4. Verify focused frontend test.
5. Commit as `fix: align storage source policy`.

## Task 4: Local Docker Readiness

**Files:**
- Modify: `.env.example`, `README.md`, `RUNBOOK.md`, or Docker Compose defaults only as needed.

**Steps:**
1. Confirm why `docker compose up -d --build` failed on macOS with `/srv/bioinfoflow`.
2. Make the default local path usable from this repo or document the required local override clearly enough for the checklist.
3. Verify Docker Compose startup, health endpoint, and scheduler endpoint.
4. Stop the stack with `docker compose down`.
5. Commit as `fix: make local docker startup ready`.

## Final Verification

Run:

```bash
cd backend && uv run ruff check . && uv run pytest && uv run miniwdl check ../demo/parabricks-wgs-v470/wdl/wgs_fq_to_vcf.wdl
cd frontend && bun run lint && bun run test && bun run build
docker compose up -d --build
docker compose ps
curl -fsS http://localhost:8000/api/v1/system/health
curl -fsS http://localhost:8000/api/v1/scheduler/status
docker compose down
git status --short --untracked-files=all
```
