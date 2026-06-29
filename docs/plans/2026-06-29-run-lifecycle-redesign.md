# Run Lifecycle Redesign Plan

## Goal

Make every new runnable run compile from user intent into a fresh run-scoped
execution plan. Retry and supported resume paths must not reuse another run's
resolved paths, engine inputs, launch snapshot, or output directory.

## Root Causes

- `RunCompiler` is the only path that creates the run layout, materializes input
  documents, writes WDL `inputs.json`, builds launch metadata, and binds
  platform-managed output directories.
- `retry_run()` and `resume_run()` currently create rows by hand and copy
  `resolved_runspec` or the old config. Those snapshots contain run-specific
  paths such as `runs/<source>/results` and `runs/<source>/input/...`.
- Archive/output code can fall back to configured `outdir`, which is required
  for legacy runs but dangerous if a newly retried run inherits a stale source
  run path.
- Run lineage, idempotency, and scheduler task uniqueness are not first-class
  persistence invariants. These are real design gaps but can be phased after the
  path isolation fix.

## Design Principles

- User intent is reusable. Execution snapshots are not.
- `RunCompiler` owns runnable run creation.
- `RunLayout` owns run-specific paths.
- Platform-managed fields such as `outdir`, `output_dir`, `publish_dir`, and
  `work_dir` are rebound for every new run.
- Compatibility fallbacks stay explicit and narrow.

## Immediate Phase

### 1. Preserve Submitted Intent

Extend `RunConfigHelper.build_v1()` and `RunCompiler` so new runs persist the
canonical submission envelope under `config["request"]["values"]` and
`config["request"]["options"]`. Existing `params`/`inputs` aliases remain for
the scheduler and adapters.

### 2. Recompile Retry

Change `RunLifecycleService.retry_run()` to:

- require the source run to be failed;
- recover submitted values from `request.values` when available;
- otherwise derive compatibility values from `request.params` and
  `request.inputs` by mapping form-field ids and engine keys back to fields;
- drop platform-managed fields while deriving values;
- merge caller `config_overrides`;
- call `RunCompiler.create_run()` with a fresh `RunCreate` envelope;
- audit `run.retried` with `source_run_id`.

This regenerates run layout, WDL inputs, launch metadata, archive manifest, and
resolved run snapshot for the new run.

### 3. Recompile Supported Resume

Use the same fresh compile path for resume, then add resume metadata to the new
run config. The old best-effort work directory may remain a runtime resume
token, but platform-managed output paths still point at the new run's results.

### 4. Pin Regressions

Add failing tests first for:

- WDL retry rebinding `params.outdir` and qualified WDL outdir inputs to the new
  run results directory.
- WDL retry archive manifest and `engine/wdl/inputs.json` referencing the new run
  and not the source run.
- API retry preserving the canonical path contract through persisted config.

### 5. Verify

Run the focused backend tests for lifecycle/compiler/archive/WDL adapter and
backend lint. If broader blast radius appears, run the full backend suite.

## Deferred Hardening

These should become follow-up work because they need migrations and product/API
decisions:

- Add run lineage fields such as `source_run_id`, `attempt_group_id`, and
  `attempt_number`.
- Add idempotency keys for create/retry to avoid duplicate active children.
- Add a DB-level partial unique invariant for active scheduler tasks per run.
- Increase run ID entropy and make filesystem directory ownership transactional.
- Decide whether project data is container-visible for manifest-referenced large
  inputs or whether those paths must be rejected/materialized into task-visible
  files.
- Introduce a first-class manifest input type with declared path columns and
  allowed roots.

## Commit Phases

1. Commit this plan.
2. Commit failing regression tests after confirming the old code fails them.
3. Commit the compiler/lifecycle refactor after tests and lint pass.
4. Commit any review fixes from parallel final reviewers.
