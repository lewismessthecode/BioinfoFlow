# Run Submission Contract And Deaf_20 Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Repair the run-submission contract so demo workflows submit predictably in the UI, refresh visibly in runs, and materialize `Deaf_20` manifests correctly under qualified WDL input keys.

**Architecture:** Keep the submission hint as the UI-facing source of truth, but make both frontend guided inputs and backend WDL submission handling honor the same canonical key mapping. Treat demo workflow confusion as a UX problem: surface clearer defaults/descriptions while preserving the underlying mock workflow design. Fix `Deaf_20` by normalizing qualified WDL keys before manifest materialization so asset-backed `sequence.list` files are rewritten into runtime-visible absolute paths.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Next.js App Router, React 19, Vitest, pytest

### Task 1: Lock The Backend WDL Key Normalization Bug

**Files:**
- Modify: `backend/tests/test_api/test_unified_run_create.py`
- Modify: `backend/app/services/run_submission_service.py`

**Step 1: Write the failing test**

Add a regression test that submits a WDL run with qualified JSON keys like `"Deaf_20.sequence_list"` and asserts:
- the run is accepted
- the stored engine inputs use a materialized `sequence.list`
- the materialized manifest rewrites cell-level `asset://deliveries/...fq.gz` entries to absolute paths

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_api/test_unified_run_create.py -k qualified_sequence_list -v`

Expected: FAIL because the current backend only materializes unqualified `sequence_list`.

**Step 3: Write minimal implementation**

Normalize WDL submission JSON keys from qualified form to schema names before:
- manifest detection/materialization
- managed-input injection
- final engine input assembly

Reject ambiguous payloads if both qualified and unqualified forms are supplied for the same logical input.

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_api/test_unified_run_create.py -k qualified_sequence_list -v`

Expected: PASS

### Task 2: Lock The Frontend Guided-Input Contract Bug

**Files:**
- Modify: `frontend/tests/integration/components/run-submission-wizard.test.tsx`
- Modify: `frontend/app/(app)/workflows/components/run-submission-workbench.tsx`
- Modify: `frontend/app/(app)/workflows/components/json-input-editor.tsx`

**Step 1: Write the failing tests**

Add regressions that prove:
- WDL guided file picking updates the qualified JSON key while keeping the user-facing field readable
- samplesheet-driven Nextflow workflows do not show reserved `samplesheet`/`input` fields inside JSON guided inputs

**Step 2: Run tests to verify they fail**

Run: `cd frontend && bun run test frontend/tests/integration/components/run-submission-wizard.test.tsx`

Expected: FAIL because guided inputs currently write raw schema names and ignore reserved JSON keys.

**Step 3: Write minimal implementation**

Drive guided JSON fields from the submission hint contract:
- separate display label from JSON key
- qualify WDL JSON keys consistently
- exclude reserved JSON keys from guided fields

**Step 4: Run test to verify it passes**

Run: `cd frontend && bun run test frontend/tests/integration/components/run-submission-wizard.test.tsx`

Expected: PASS

### Task 3: Make New Runs Visible Immediately

**Files:**
- Modify: `frontend/app/(app)/workflows/components/run-submission-wizard.tsx`
- Modify: `frontend/app/(app)/runs/page.tsx`
- Modify: `frontend/app/(app)/runs/use-runs-page.ts`
- Modify: `frontend/app/(app)/workflows/page.tsx`

**Step 1: Write the failing test**

Add a regression around the submission flow so a successful create-run response triggers a visible post-submit action instead of silently closing with stale run state.

**Step 2: Run test to verify it fails**

Run: `cd frontend && bun run test frontend/tests/integration/components/run-submission-wizard.test.tsx`

Expected: FAIL because submit success does not currently refresh or route to the new run.

**Step 3: Write minimal implementation**

Thread the created `run_id` through the wizard callback so:
- runs page can refresh/highlight the new run
- workflows page can navigate the user to the runs view with the new run highlighted

**Step 4: Run test to verify it passes**

Run: `cd frontend && bun run test frontend/tests/integration/components/run-submission-wizard.test.tsx`

Expected: PASS

### Task 4: Clarify The Demo Workflow UX

**Files:**
- Modify: `backend/app/services/demo_catalog.py`

**Step 1: Write the failing test**

Prefer an existing API or frontend test if present; otherwise add a narrow assertion that demo workflow descriptions clarify mock/self-contained inputs where needed.

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_api/test_submission_hint.py -k demo -v`

Expected: FAIL or no coverage yet.

**Step 3: Write minimal implementation**

Tighten demo descriptions so:
- `subworkflow_import_mini` explicitly says it is self-contained and only needs `sample_id`
- `rnaseq_quant_mini` makes the samplesheet/default-param split easier to understand in the UI copy

**Step 4: Run tests to verify nothing regresses**

Run: `cd backend && uv run pytest tests/test_api/test_submission_hint.py -v`

Expected: PASS

### Task 5: Verify The Whole Fix Set

**Files:**
- Modify: `docs/workflow-submission-guide.md` if behavior or examples changed materially

**Step 1: Run targeted backend tests**

Run: `cd backend && uv run pytest tests/test_api/test_unified_run_create.py -k 'sequence_list or submission_hint' -v`

Expected: PASS

**Step 2: Run targeted frontend tests**

Run: `cd frontend && bun run test frontend/tests/integration/components/run-submission-wizard.test.tsx`

Expected: PASS

**Step 3: Run one broader smoke slice per side**

Run: `cd backend && uv run pytest tests/test_api/test_submission_hint.py tests/test_engine/test_schema_extractor.py -v`

Run: `cd frontend && bun run test frontend/tests/unit/lib/schema-resolver.test.ts frontend/tests/integration/components/run-submission-wizard.test.tsx`

Expected: PASS
