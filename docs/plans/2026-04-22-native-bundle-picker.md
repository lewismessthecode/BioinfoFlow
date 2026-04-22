# Native Bundle Picker Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace local bundle registration's manual path entry with native directory selection and clickable entrypoint selection, while preserving single-file quick import.

**Architecture:** The frontend should treat a local workflow bundle as a selected directory payload, not a typed filesystem path. Bundle mode will use a native directory picker (`webkitdirectory`) to collect the full bundle file list, then let the user choose the entrypoint from those files. The backend will expose a dedicated multipart bundle-upload registration endpoint that materializes the selected bundle into the workflow store before running existing validation and schema extraction.

**Tech Stack:** Next.js 16, React 19, FastAPI, SQLAlchemy, Vitest, pytest, multipart form uploads.

### Task 1: Cover native bundle picking in tests

**Files:**
- Modify: `frontend/tests/integration/components/workflow-register-dialog.test.tsx`
- Modify: `backend/tests/test_api/test_workflows.py`

**Step 1: Write the failing frontend test**

Add a test that:

- switches to local bundle mode
- uploads a bundle directory selection through a file input carrying `webkitRelativePath`
- chooses an entrypoint from the discovered candidates
- submits the form
- asserts the frontend uses multipart upload for bundle registration instead of JSON `bundle_path`

**Step 2: Run the frontend test to verify it fails**

Run:

```bash
bun run test tests/integration/components/workflow-register-dialog.test.tsx
```

Expected: FAIL because bundle mode still expects `bundle_path` and typed `entrypoint_relpath`.

**Step 3: Write the failing backend API test**

Add a test that submits multipart form data to a new local-bundle registration endpoint with:

- metadata fields
- repeated uploaded files
- relative path manifest
- chosen entrypoint path

Assert the backend materializes the bundle and persists the workflow.

**Step 4: Run the backend test to verify it fails**

Run:

```bash
uv run pytest backend/tests/test_api/test_workflows.py -q
```

Expected: FAIL because the multipart bundle endpoint does not exist yet.

### Task 2: Implement backend bundle-upload registration

**Files:**
- Modify: `backend/app/api/v1/workflows.py`
- Modify: `backend/app/schemas/workflow.py`
- Modify: `backend/app/services/workflow_service.py`
- Modify: `backend/tests/test_api/test_workflows.py`

**Step 1: Add a dedicated multipart endpoint**

Create a new endpoint such as:

```text
POST /api/v1/workflows/local-bundle
```

It should accept:

- optional metadata fields (`name`, `version`, `engine`, `description`)
- `entrypoint_relpath`
- a JSON manifest of relative paths
- repeated uploaded files

**Step 2: Materialize uploaded bundle files**

Build the workflow bundle directory from the uploaded files using the provided relative paths. Reject path traversal and mismatched manifest lengths.

**Step 3: Reuse the existing local workflow validation path**

Feed the materialized bundle into the existing local workflow creation flow so schema extraction, uniqueness checks, and metadata writing stay consistent.

### Task 3: Implement frontend native bundle selection

**Files:**
- Modify: `frontend/app/(app)/workflows/components/register-form-hook.ts`
- Modify: `frontend/app/(app)/workflows/components/register-form-fields.tsx`
- Modify: `frontend/app/(app)/workflows/components/workflow-register-dialog.tsx`
- Modify: `frontend/app/(app)/workflows/components/register-preview-panel.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`

**Step 1: Replace typed bundle path with selected bundle files**

Track:

- selected bundle files
- bundle display label
- discovered entrypoint candidates
- selected entrypoint

**Step 2: Use a native directory picker**

Add a hidden file input using directory selection attributes and trigger it from the visible “Choose bundle” button.

**Step 3: Add clickable entrypoint selection**

Replace the free-text entrypoint field with a chooser based on the selected bundle's discovered `.nf` / `.wdl` files.

**Step 4: Submit multipart form data**

When in bundle mode, send a `FormData` payload to the new backend endpoint instead of JSON `bundle_path`.

### Task 4: Verify the change

**Files:**
- Test: `frontend/tests/integration/components/workflow-register-dialog.test.tsx`
- Test: `backend/tests/test_api/test_workflows.py`

**Step 1: Run focused frontend tests**

```bash
bun run test tests/integration/components/workflow-register-dialog.test.tsx
```

Expected: PASS

**Step 2: Run focused backend tests**

```bash
cd backend && uv run pytest tests/test_api/test_workflows.py -q
```

Expected: PASS

**Step 3: Run integration confidence checks**

```bash
bun run lint
cd backend && uv run pytest tests/test_api/test_workflows.py tests/test_api/test_workflow_form_spec.py -q
```

Expected: PASS
