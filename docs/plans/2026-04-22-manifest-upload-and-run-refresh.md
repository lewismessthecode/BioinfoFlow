# Manifest Upload And Run Refresh Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan.

**Goal:** Let manifest-style workflow inputs be uploaded at run submission time and snapshotted into the run, while fixing runs-page output refresh after completion.

**Architecture:** Add an explicit `materialize_to_run` form-field flag so the platform knows which top-level file inputs are runtime documents, not large source data. Introduce a hidden run-upload asset source plus a small upload API, snapshot marked documents into `runs/<run_id>/input/materialized/attachments`, and refresh outputs when an expanded run transitions to a terminal state.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Next.js, React, Vitest, Pytest

### Task 1: Form Spec Contract

**Files:**
- Modify: `backend/app/schemas/form_spec.py`
- Modify: `backend/app/services/workflow_form_spec.py`
- Modify: `frontend/lib/form-spec.ts`
- Test: `backend/tests/test_api/test_workflow_form_spec.py`

**Step 1: Write failing tests**

- Add a backend test proving a local workflow override can expose `materialize_to_run: true`.
- Add a backend test proving manifest-style file fields no longer inherit bundle fixture defaults.

**Step 2: Run tests to verify they fail**

Run:

```bash
cd /Users/lewisliu/Dev/playground/bpiper/backend && uv run pytest backend/tests/test_api/test_workflow_form_spec.py -q
```

**Step 3: Implement minimal contract changes**

- Add `materialize_to_run: bool = False` to server/frontend form field types.
- Let overrides set that flag.
- Skip default bundle prefill for `materialize_to_run` file/directory fields.

**Step 4: Re-run tests**

### Task 2: Run Upload + Snapshot

**Files:**
- Modify: `backend/app/path_layout.py`
- Modify: `backend/app/schemas/run.py`
- Modify: `backend/app/api/v1/runs.py`
- Modify: `backend/app/services/run_compiler.py`
- Test: `backend/tests/test_api/test_runs.py`

**Step 1: Write failing tests**

- Add a run API test proving a manifest uploaded through a run-upload URI gets copied into `runs/<run_id>/input/materialized/attachments/...` and the engine config points at the copied file.

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/lewisliu/Dev/playground/bpiper/backend && uv run pytest backend/tests/test_api/test_runs.py -q
```

**Step 3: Implement minimal backend**

- Add hidden per-project run-upload staging paths under state.
- Add `POST /api/v1/runs/uploads`.
- Resolve `asset://run_upload/...` in the compiler.
- Snapshot `materialize_to_run` documents into the run attachments directory.

**Step 4: Re-run tests**

### Task 3: Frontend Upload UX

**Files:**
- Modify: `frontend/app/(app)/workflows/components/run-form/fields/file-field.tsx`
- Modify: `frontend/tests/integration/components/run-form.test.tsx`

**Step 1: Write failing test**

- Add a frontend test proving `materialize_to_run` file fields show an upload affordance and submit the returned run-upload URI through `onChange`.

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/lewisliu/Dev/playground/bpiper/frontend && bun run test frontend/tests/integration/components/run-form.test.tsx
```

**Step 3: Implement minimal frontend**

- Add a hidden file input and upload button for `materialize_to_run` file fields.
- POST to `/runs/uploads` with `FormData`.
- Preserve existing browse flow for storage-backed selection.

**Step 4: Re-run tests**

### Task 4: Runs Detail Output Refresh

**Files:**
- Modify: `frontend/app/(app)/runs/use-runs-page.ts`
- Modify: `frontend/app/(app)/runs/[runId]/page.tsx`
- Test: `frontend/tests/integration/pages/runs-page-core.test.tsx`

**Step 1: Write failing test**

- Prove that when an expanded run receives a terminal `onRunStatus` event, outputs are re-fetched and the detail panel updates.

**Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/lewisliu/Dev/playground/bpiper/frontend && bun run test frontend/tests/integration/pages/runs-page-core.test.tsx
```

**Step 3: Implement minimal refresh**

- Extract a details reload helper.
- Re-fetch outputs for the expanded/full-page run on terminal transitions (`completed`, `failed`, `cancelled`).

**Step 4: Re-run tests**

### Task 5: Demo Fixtures And Verification

**Files:**
- Modify: `demo/rnaseq-quant-mini/inputs/form-spec.overrides.json`
- Modify: `demo/variant-fanout-mini/inputs/form-spec.overrides.json`
- Modify: `demo/rnaseq-quant-mini/data/samplesheet*.csv`
- Modify: `demo/variant-fanout-mini/data/*.tsv`
- Modify: `backend/tests/test_api/test_runs.py`

**Step 1: Update demo manifests**

- Mark manifest fields as `materialize_to_run`.
- Refresh example manifest contents/documentation to match the upload-and-snapshot flow.

**Step 2: Run focused verification**

Run:

```bash
cd /Users/lewisliu/Dev/playground/bpiper/backend && uv run pytest backend/tests/test_api/test_runs.py backend/tests/test_api/test_workflow_form_spec.py -q
cd /Users/lewisliu/Dev/playground/bpiper/frontend && bun run test frontend/tests/integration/components/run-form.test.tsx frontend/tests/integration/pages/runs-page-core.test.tsx
```

**Step 3: Commit in logical batches**

- Backend contract + compiler
- Frontend upload + runs refresh
- Demo fixtures + tests
