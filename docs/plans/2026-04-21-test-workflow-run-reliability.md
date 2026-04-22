# Test Workflow Run Reliability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the five retained local test workflows runnable again end-to-end, and fix failed-run DAG rendering so the UI stays truthful in both light and dark themes.

**Architecture:** Treat local workflow bundles as a first-class source of default fixtures instead of leaking bundle files through `asset://project/...`. Stage bundle-backed inputs into each run's materialized input area so engines and containers only consume run-local paths. Standardize test WDL workflows on a bash-capable container contract and ensure the WDL path can pull missing images automatically. Fix DAG edge rendering by using theme tokens that exist in both light and dark mode and matching arrowhead color to edge state.

**Tech Stack:** FastAPI, SQLAlchemy, local workflow bundles under `data/state/workflows/local`, miniwdl/WDL adapter, Nextflow adapter, React 19, React Flow, Vitest, pytest.

### Task 1: Reproduce bundle-default failures in tests

**Files:**
- Modify: `backend/tests/test_api/test_workflow_form_spec.py`
- Modify: `backend/tests/test_services/test_run_compiler.py`
- Test: `backend/tests/test_api/test_workflow_form_spec.py`
- Test: `backend/tests/test_services/test_run_compiler.py`

**Step 1: Write the failing tests**

- Add an API test that creates a local bundle workflow with `inputs/happy.params.json` or `inputs/happy.inputs.json`, then asserts `GET /workflows/{id}/form-spec` returns bundle-scoped defaults instead of stale `asset://project/...` values.
- Add a compiler test that submits a run using a bundle-scoped asset default and asserts the resolved engine inputs point into `runs/<id>/input/materialized/...`.

**Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_api/test_workflow_form_spec.py tests/test_services/test_run_compiler.py -q`

Expected: FAIL because local bundle fixture defaults are not reconciled and bundle assets are not staged into run-local materialized inputs.

**Step 3: Write minimal implementation**

- Add a shared helper that reconciles a workflow's `form_spec` with bundle `inputs/happy.*.json` fixtures.
- Support `asset://workflow/<workflow_id>/...` defaults for local bundles.
- Update the compiler to resolve and materialize bundle-backed files into `RunLayout.materialized`.

**Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_api/test_workflow_form_spec.py tests/test_services/test_run_compiler.py -q`

Expected: PASS

### Task 2: Reproduce WDL runtime contract failures in tests

**Files:**
- Modify: `backend/tests/test_engine/test_wdl_adapter.py`
- Modify: `backend/tests/test_services/test_workflow_validator.py` or a new focused test file if clearer
- Modify: `demo/flaky-retry-mini/flaky_retry.wdl`
- Modify: `demo/resource-stress-mini/resource_stress.wdl`
- Modify: `demo/variant-fanout-mini/variant_fanout.wdl`
- Modify: `demo/subworkflow-import-mini/main.wdl`
- Modify: `demo/subworkflow-import-mini/subworkflows/qc_sub.wdl`
- Modify: `demo/subworkflow-import-mini/subworkflows/align_sub.wdl`
- Test: `backend/tests/test_engine/test_wdl_adapter.py`

**Step 1: Write the failing tests**

- Add a WDL adapter test that proves missing required images trigger an auto-pull preflight instead of surfacing `docker image not found`.
- Add or extend tests that cover imported local WDL bundles being extracted from their real bundle path, not a temporary orphan file.

**Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_engine/test_wdl_adapter.py -q`

Expected: FAIL because the adapter does not preflight required images and imported bundle extraction still loses relative imports.

**Step 3: Write minimal implementation**

- Enrich WDL run config with required container images from schema.
- Add WDL adapter pre-submit image preflight/pull.
- Update schema extraction to prefer the real local bundle path when it exists.
- Change retained WDL test workflows to use a consistent bash-capable container contract and portable shell commands.

**Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_engine/test_wdl_adapter.py -q`

Expected: PASS

### Task 3: Reproduce the failed-edge DAG rendering bug in tests

**Files:**
- Modify: `frontend/tests/unit/components/dag-edge.test.tsx`
- Modify: `frontend/components/bioinfoflow/dag/dag-edge.tsx`
- Test: `frontend/tests/unit/components/dag-edge.test.tsx`

**Step 1: Write the failing test**

- Extend the edge unit test so failed edges must use a theme token that exists in light mode and so arrowheads inherit the same terminal color as the edge stroke.

**Step 2: Run test to verify it fails**

Run: `cd frontend && bun run test -- tests/unit/components/dag-edge.test.tsx`

Expected: FAIL because failed edges currently rely on `var(--error)` and arrowheads stay pinned to `var(--foreground)`.

**Step 3: Write minimal implementation**

- Switch failed-edge styling to a shared semantic token available in both themes.
- Make `markerEnd.color` follow the computed edge color.

**Step 4: Run test to verify it passes**

Run: `cd frontend && bun run test -- tests/unit/components/dag-edge.test.tsx`

Expected: PASS

### Task 4: Verify the full regression slice

**Files:**
- No code changes required unless regressions surface

**Step 1: Run focused backend regression commands**

Run:
- `cd backend && uv run pytest tests/test_api/test_workflow_form_spec.py tests/test_services/test_run_compiler.py tests/test_engine/test_wdl_adapter.py -q`
- `cd backend && uv run pytest tests/test_runtime/test_dag_status.py -q`

Expected: PASS

**Step 2: Run focused frontend regression commands**

Run:
- `cd frontend && bun run test -- tests/unit/components/dag-edge.test.tsx tests/integration/components/dag-panel.test.tsx`

Expected: PASS

**Step 3: Spot-check the retained workflow bundles**

Run:
- `rg -n 'docker:' demo/flaky-retry-mini demo/resource-stress-mini demo/variant-fanout-mini demo/subworkflow-import-mini`
- `rg -n 'samplesheet|samples_tsv' demo/rnaseq-quant-mini demo/variant-fanout-mini`

Expected: The retained workflows now declare bundle-self-contained defaults and bash-capable runtime images.
