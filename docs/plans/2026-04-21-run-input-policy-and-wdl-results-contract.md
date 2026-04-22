# Run Input Policy And WDL Results Contract Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove the remaining contract mismatches across local workflow registration, run submission, WDL execution, and runs-page UX so retained test workflows behave predictably from input selection through output browsing.

**Architecture:** Move local workflow input-source policy into each workflow bundle so the bundle, backend compiler, and frontend picker all consume the same declared contract instead of inferring intent from field names. Standardize WDL platform-managed directory inputs on one absolute run results directory so every task, retry, and output copier shares the same filesystem truth. Consume one-time run highlighting in the runs UI and add explicit workflow-detail navigation where users naturally expect it.

**Tech Stack:** FastAPI, SQLAlchemy, local workflow bundles under `demo/`, form-spec reconciliation, miniwdl adapter, Nextflow/WDL run compiler, Next.js 16, React 19, Vitest, pytest.

### Task 1: Add a bundle-level input policy contract for local workflows

**Files:**
- Create: `demo/rnaseq-quant-mini/inputs/form-spec.overrides.json`
- Create: `demo/variant-fanout-mini/inputs/form-spec.overrides.json`
- Modify: `backend/app/services/workflow_form_spec.py`
- Modify: `backend/tests/test_api/test_workflow_form_spec.py`
- Modify: `backend/tests/test_services/test_form_spec.py`
- Test: `backend/tests/test_api/test_workflow_form_spec.py`
- Test: `backend/tests/test_services/test_form_spec.py`

**Step 1: Write the failing tests**

- Add a form-spec service test proving a local bundle can override `allow_roots` explicitly instead of inheriting the name-based default.
- Add an API test proving `GET /workflows/{id}/form-spec` returns the declared mixed roots for `rnaseq-quant-mini.samplesheet` and `variant-fanout-mini.samples_tsv`.

**Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_services/test_form_spec.py tests/test_api/test_workflow_form_spec.py -q`

Expected: FAIL because bundle metadata cannot currently override `allow_roots`.

**Step 3: Write minimal implementation**

- Teach `workflow_form_spec.py` to load an optional bundle file such as `inputs/form-spec.overrides.json`.
- Support per-field overrides keyed by either `engine_key` or `id`, initially for `allow_roots` and other existing `FormField` properties the schema already supports.
- Add explicit overrides so:
  - `demo/rnaseq-quant-mini/inputs/form-spec.overrides.json` allows `samplesheet` from `project_data` and `shared_data`
  - `demo/variant-fanout-mini/inputs/form-spec.overrides.json` allows `samples_tsv` from `project_data` and `shared_data`

**Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_services/test_form_spec.py tests/test_api/test_workflow_form_spec.py -q`

Expected: PASS

### Task 2: Make the frontend file picker obey the same allowed-source contract

**Files:**
- Modify: `frontend/components/bioinfoflow/file-browser-dialog.tsx`
- Modify: `frontend/app/(app)/workflows/components/run-form/fields/file-field.tsx`
- Modify: `frontend/app/(app)/workflows/components/run-form/fields/file-list-field.tsx`
- Modify: `frontend/app/(app)/workflows/components/run-form/fields/table-field.tsx`
- Modify: `frontend/tests/integration/components/run-form.test.tsx`
- Add or modify: a focused frontend test covering source filtering in the file browser or field wrappers
- Test: `frontend/tests/integration/components/run-form.test.tsx`

**Step 1: Write the failing tests**

- Add a focused test proving a file field with `allow_roots=["project_data","shared_data"]` exposes project + deliveries, but hides reference/results/database.
- Add a focused test proving a table path picker uses the same allowed-source filtering.

**Step 2: Run tests to verify they fail**

Run: `cd frontend && bun run test -- tests/integration/components/run-form.test.tsx`

Expected: FAIL because the current browser only picks a preferred tab and still renders every storage source.

**Step 3: Write minimal implementation**

- Pass allowed source kinds into `FileBrowserDialog`, not just one preferred tab.
- Filter the `/storage/sources` result to the allowed set before rendering tabs.
- Reuse one helper that maps `allow_roots` to frontend source kinds so file, file-list, and table path pickers stay aligned.

**Step 4: Run tests to verify they pass**

Run: `cd frontend && bun run test -- tests/integration/components/run-form.test.tsx`

Expected: PASS

### Task 3: Make WDL directory inputs use one absolute shared results root

**Files:**
- Modify: `backend/app/services/run_compiler.py`
- Modify: `backend/app/engine/adapters/wdl.py`
- Modify: `backend/tests/test_services/test_run_compiler.py`
- Modify: `backend/tests/test_engine/test_wdl_adapter.py`
- Modify: `backend/tests/test_api/test_runs_artifacts.py`
- Test: `backend/tests/test_services/test_run_compiler.py`
- Test: `backend/tests/test_engine/test_wdl_adapter.py`
- Test: `backend/tests/test_api/test_runs_artifacts.py`

**Step 1: Write the failing tests**

- Add a compiler test proving WDL platform-managed `outdir` inputs are compiled to the absolute path of `run_results_root(project, run_id)`.
- Add a WDL adapter test proving qualified keys such as `resource_stress_mini.outdir` are preserved as absolute paths in `inputs.json`.
- Add an artifacts test proving files written under the canonical run results root are discoverable without depending on legacy relative `outdir` fallback.

**Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_services/test_run_compiler.py tests/test_engine/test_wdl_adapter.py tests/test_api/test_runs_artifacts.py -q`

Expected: FAIL because WDL currently gets relative `runs/<run_id>/results` paths and `_prepare_inputs()` only rewrites bare keys.

**Step 3: Write minimal implementation**

- In `RunCompiler`, compute WDL-managed output directory inputs from `layout.results.resolve()` rather than from a workspace-relative string.
- In the WDL adapter, absolutize platform-managed directory values by semantic key suffix (`outdir`, `output_dir`, `publish_dir`, `work_dir`), not only by exact dict key.
- Keep `_copy_outputs()` and run-archive lookup aligned with the public run results root.

**Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_services/test_run_compiler.py tests/test_engine/test_wdl_adapter.py tests/test_api/test_runs_artifacts.py -q`

Expected: PASS

### Task 4: Fix runs-page highlight state and workflow-detail navigation

**Files:**
- Modify: `frontend/app/(app)/runs/use-runs-page.ts`
- Modify: `frontend/app/(app)/runs/page.tsx`
- Modify: `frontend/app/(app)/runs/components/run-inline-detail.tsx`
- Modify: `frontend/app/(app)/runs/[runId]/page.tsx`
- Modify: `frontend/tests/integration/pages/runs-page-core.test.tsx`
- Modify: `frontend/tests/integration/pages/runs-page-actions.test.tsx`
- Test: `frontend/tests/integration/pages/runs-page-core.test.tsx`
- Test: `frontend/tests/integration/pages/runs-page-actions.test.tsx`

**Step 1: Write the failing tests**

- Add a runs-page test proving closing a highlighted run stays closed across subsequent refreshes/SSE-driven rerenders.
- Add a runs-page test proving workflow names navigate to `/workflows/{workflow_id}` without accidentally toggling row expansion.

**Step 2: Run tests to verify they fail**

Run: `cd frontend && bun run test -- tests/integration/pages/runs-page-core.test.tsx tests/integration/pages/runs-page-actions.test.tsx`

Expected: FAIL because `highlight` is reapplied on every refresh and workflow names are plain text today.

**Step 3: Write minimal implementation**

- Consume and clear the `highlight` query parameter after the first successful auto-expand.
- Separate row-expanded state from one-time highlight intent.
- Render workflow names as links in:
  - the runs table
  - the inline run detail header
  - the run detail page sidebar card

**Step 4: Run tests to verify they pass**

Run: `cd frontend && bun run test -- tests/integration/pages/runs-page-core.test.tsx tests/integration/pages/runs-page-actions.test.tsx`

Expected: PASS

### Task 5: Update docs and run the focused regression slice

**Files:**
- Modify: `docs/workflow-submission-guide.md`

**Step 1: Update docs**

- Document that local workflow bundles may declare `inputs/form-spec.overrides.json`.
- Clarify that WDL platform-managed directory inputs resolve to the absolute run results root.
- Clarify that the frontend file browser only shows storage sources allowed by `form-spec`.

**Step 2: Run backend regression commands**

Run:
- `cd backend && uv run pytest tests/test_services/test_form_spec.py tests/test_api/test_workflow_form_spec.py tests/test_services/test_run_compiler.py tests/test_engine/test_wdl_adapter.py tests/test_api/test_runs_artifacts.py -q`

Expected: PASS

**Step 3: Run frontend regression commands**

Run:
- `cd frontend && bun run test -- tests/integration/components/run-form.test.tsx tests/integration/pages/runs-page-core.test.tsx tests/integration/pages/runs-page-actions.test.tsx`

Expected: PASS

**Step 4: Commit in logical batches**

Suggested commits:
- `git commit -m "Add explicit local workflow input source policies"`
- `git commit -m "Fix WDL results directory contract"`
- `git commit -m "Fix runs page highlight and workflow navigation UX"`
