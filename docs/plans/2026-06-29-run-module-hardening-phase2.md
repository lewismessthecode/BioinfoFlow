# Run Module Hardening Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the remaining Run-module deferred hazards by making lifecycle lineage, idempotency, scheduler uniqueness, filesystem ownership, output isolation, and WDL mount visibility explicit invariants.

**Architecture:** Keep `RunCompiler` as the only creation path for runnable runs, but make the invariants durable at database and filesystem boundaries. Runtime execution still flows through the existing scheduler, adapters, and archive services; the change is to constrain their inputs and transitions instead of letting stale JSON config decide ownership.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Alembic, SQLite/PostgreSQL-compatible constraints where possible, pytest, ruff.

---

## First-Principles Invariants

- A run has one immutable public identity and one exclusive filesystem home.
- A replayed run records queryable lineage: source run, replay kind, attempt number, and replay idempotency key.
- Duplicate retry/resume requests for the same failed source and same replay intent must resolve to the same child run, even if the child has already reached a terminal state.
- A scheduler may have at most one active task (`queued` or `dispatched`) per run at the database level.
- A scheduler retry starts a fresh attempt clock and clears stale per-attempt counters.
- New-schema runs resolve outputs from `runs/<run_id>/results`; legacy configured outdir fallback is allowed only for legacy configs.
- Output downloads are scoped to the resolved output root, not the whole project tree.
- WDL task containers can see every platform path Bioinfoflow puts into WDL inputs or manifest rows, or compile rejects the run.
- Public API fields must either work or be rejected; silently ignored fields are invalid.

## Phase 1: Plan And Schema Invariants

**Files:**
- Modify: `backend/app/models/run.py`
- Modify: `backend/app/scheduler/models.py`
- Create: `backend/alembic/versions/0041_run_module_invariants.py`
- Test: `backend/tests/test_models/test_run_invariants.py`

- [ ] Add failing tests:
  - invalid `runs.status` insert fails;
  - duplicate active `scheduled_tasks` rows for one `run_id` fail;
  - duplicate replay rows with the same `(source_run_id, replay_kind, idempotency_key)` fail, regardless of terminal state;
  - partial replay lineage rows and self-sourced replay rows fail.
- [ ] Run:
  - `rtk uv run pytest tests/test_models/test_run_invariants.py -q`
  - Expected before implementation: failures from missing columns/constraints.
- [ ] Add model fields:
  - `Run.source_run_id -> runs.run_id`, nullable;
  - `Run.replay_kind`, nullable string constrained to `retry` or `resume`;
  - `Run.replay_idempotency_key`, nullable string;
  - `Run.attempt_number`, non-null integer default `1`.
- [ ] Add DB constraints and indexes:
  - allowed `runs.status`;
  - allowed nullable `runs.replay_kind`;
  - partial unique replay index on `(source_run_id, replay_kind, replay_idempotency_key)` for non-null replay intent rows;
  - all-or-none lineage constraints tying `source_run_id`, `replay_kind`, `replay_idempotency_key`, and `attempt_number` together;
  - partial unique active scheduler index on `scheduled_tasks(run_id)` for states `queued`, `dispatched`.
- [ ] Run:
  - `rtk uv run pytest tests/test_models/test_run_invariants.py -q`
  - `rtk uv run alembic upgrade head`
  - Expected after implementation: pass.
- [ ] Commit:
  - `rtk git add -f docs/plans/2026-06-29-run-module-hardening-phase2.md`
  - `rtk git add backend/app/models/run.py backend/app/scheduler/models.py backend/alembic/versions/0041_run_module_invariants.py backend/tests/test_models/test_run_invariants.py`
  - `rtk git commit -m "refactor: add run lifecycle invariants"`

## Phase 2: Replay Idempotency And API Honesty

**Files:**
- Modify: `backend/app/schemas/run.py`
- Modify: `backend/app/services/run_compiler.py`
- Modify: `backend/app/services/run_lifecycle_service.py`
- Modify: `backend/app/api/v1/runs.py`
- Test: `backend/tests/test_services/test_run_service.py`
- Test: `backend/tests/test_api/test_runs.py`

- [ ] Add failing tests:
  - two identical `retry_run()` calls against a failed run return the same child, including after that child is terminal;
  - retry child stores `source_run_id`, `replay_kind="retry"`, `attempt_number=source.attempt_number+1`;
  - resume child stores `source_run_id`, `replay_kind="resume"`;
  - `POST /runs` with `options.resume_from_run_id` returns 422 until first-class create-time resume is implemented.
- [ ] Run:
  - `rtk uv run pytest tests/test_services/test_run_service.py::test_retry_run_is_idempotent_for_active_child tests/test_api/test_runs.py::test_runs_create_rejects_resume_from_run_id_option -q`
  - Expected before implementation: failures.
- [ ] Implement deterministic replay idempotency:
  - compute a stable SHA-256 key from source run id, replay kind, replay values, replay options, config overrides, and resume payload;
  - before compiling, return an existing child with the same key;
  - pass lineage fields into `RunCompiler.create_run`;
  - after compile, catch replay unique-index conflicts and return the existing child;
  - if persistence fails before dispatch, remove the half-created child so idempotency cannot wedge on a non-runnable row.
- [ ] Reject `RunOptions.resume_from_run_id` in create-run validation with a structured `CompileError`.
- [ ] Run:
  - focused tests above;
  - `rtk uv run pytest tests/test_services/test_run_service.py tests/test_api/test_runs.py -q`.
- [ ] Commit:
  - `rtk git add backend/app/schemas/run.py backend/app/services/run_compiler.py backend/app/services/run_lifecycle_service.py backend/app/api/v1/runs.py backend/tests/test_services/test_run_service.py backend/tests/test_api/test_runs.py`
  - `rtk git commit -m "fix: make replay runs idempotent"`

## Phase 3: Scheduler Attempt Safety

**Files:**
- Modify: `backend/app/scheduler/queue.py`
- Modify: `backend/app/scheduler/scheduler.py`
- Modify: `backend/app/repositories/run_repo.py`
- Modify: `backend/app/services/run_lifecycle_service.py`
- Test: `backend/tests/test_scheduler/test_queue.py`
- Test: `backend/tests/test_scheduler/test_retry.py`
- Test: `backend/tests/test_services/test_run_lifecycle_service.py`

- [ ] Add failing tests:
  - concurrent enqueue creates one active task;
  - queue state helpers refuse illegal terminal-to-dispatched or terminal-to-queued transitions;
  - scheduler retry clears `started_at`, `last_heartbeat_at`, `current_task`, `tasks_total`, and `tasks_completed`;
  - scheduler retry clears stale process identifiers and does not orphan a run if task requeue loses a race;
  - terminal transitions cannot overwrite a newer terminal state;
  - task claim is guarded by a database state predicate, not only a process-local lock;
  - repository/lifecycle terminal helpers compute `duration_seconds`.
- [ ] Run focused tests and confirm red.
- [ ] Implement enqueue conflict handling and transition guards.
- [ ] Reset per-attempt run fields in `_schedule_retry()`.
- [ ] Make terminal state updates and task claims conditional database updates.
- [ ] Compute duration in repository/lifecycle terminal helpers.
- [ ] Run:
  - `rtk uv run pytest tests/test_scheduler/test_queue.py tests/test_scheduler/test_retry.py tests/test_services/test_run_lifecycle_service.py -q`.
- [ ] Commit:
  - `rtk git add backend/app/scheduler/queue.py backend/app/scheduler/scheduler.py backend/app/repositories/run_repo.py backend/app/services/run_lifecycle_service.py backend/tests/test_scheduler/test_queue.py backend/tests/test_scheduler/test_retry.py backend/tests/test_services/test_run_lifecycle_service.py`
  - `rtk git commit -m "fix: enforce scheduler run invariants"`

## Phase 4: Filesystem And Archive Boundaries

**Files:**
- Modify: `backend/app/services/run_helpers.py`
- Modify: `backend/app/path_layout.py`
- Modify: `backend/app/services/run_compiler.py`
- Modify: `backend/app/services/run_archive.py`
- Test: `backend/tests/test_services/test_run_compiler.py`
- Test: `backend/tests/test_api/test_runs_artifacts.py`
- Test: `backend/tests/test_scheduler/test_directory_isolation.py`

- [ ] Add failing tests:
  - run id has at least 128 bits of entropy;
  - an existing run home is never adopted by a new run;
  - new-schema runs do not fall back to configured legacy outdir when canonical results are missing;
  - legacy configs without schema version may still resolve legacy outdir;
  - output download rejects files outside the resolved output root.
- [ ] Run focused tests and confirm red.
- [ ] Increase run id entropy and make run-home reservation exclusive.
- [ ] Limit output fallback to legacy config.
- [ ] Scope archive `file_path` to output root.
- [ ] Run focused tests.
- [ ] Commit:
  - `rtk git add backend/app/services/run_helpers.py backend/app/path_layout.py backend/app/services/run_compiler.py backend/app/services/run_archive.py backend/tests/test_services/test_run_compiler.py backend/tests/test_api/test_runs_artifacts.py backend/tests/test_scheduler/test_directory_isolation.py`
  - `rtk git commit -m "fix: isolate run filesystem outputs"`

## Phase 5: WDL Mount Contract And Docs

**Files:**
- Modify: `backend/app/engine/miniwdl_mounts.py`
- Modify: `backend/app/engine/adapters/wdl.py`
- Modify: `backend/app/engine/miniwdl_container_backend.py`
- Modify: `docs/concepts/storage.md`
- Modify: `docs/reference/architecture.md`
- Test: `backend/tests/test_engine/test_miniwdl_mounts.py`
- Test: `backend/tests/test_engine/test_wdl_adapter.py`

- [ ] Add failing tests:
  - managed project WDL host dir mounts project `data` read-only, run `input` read-only, run `results` read-write;
  - external project WDL host dir derives the same mounts from the canonical `.../runs/<run_id>/engine/wdl/work` shape;
  - WDL best-effort resume keeps current run work dir as the miniwdl `--dir` so mount inference follows the new run.
  - WDL best-effort resume fails clearly if the source work dir has been cleaned up.
  - WDL table/manifest path cells under unmounted roots are materialized into the current run `input/` tree.
- [ ] Run focused tests and confirm red.
- [ ] Derive run mounts from the nearest `runs/<run_id>/engine/<engine>/work` ancestor instead of only `projects_root()`.
- [ ] Add project data as a sibling read-only mount.
- [ ] Preserve source resume work dir as explicit resume metadata without letting miniwdl task host dir become the source run.
- [ ] Validate source resume work dir and materialize unmounted WDL path cells.
- [ ] Update docs to match the corrected identity-mount contract.
- [ ] Run:
  - `rtk uv run pytest tests/test_engine/test_miniwdl_mounts.py tests/test_engine/test_wdl_adapter.py -q`
  - `rtk git diff --check`.
- [ ] Commit:
  - `rtk git add backend/app/engine/miniwdl_mounts.py backend/app/engine/adapters/wdl.py backend/app/engine/miniwdl_container_backend.py backend/tests/test_engine/test_miniwdl_mounts.py backend/tests/test_engine/test_wdl_adapter.py docs/concepts/storage.md docs/reference/architecture.md`
  - `rtk git commit -m "fix: enforce wdl mount contract"`

## Final Verification

- [ ] Run:
  - `rtk uv run pytest`
  - `rtk uv run ruff check .`
- [ ] Spawn final parallel review agents for:
  - schema/lifecycle/idempotency;
  - scheduler/retry;
  - filesystem/archive/WDL mount contract.
- [ ] Fix review findings with tests.
- [ ] Re-run affected tests and full backend verification.
- [ ] Sync, rebase, push, and update PR #78.
