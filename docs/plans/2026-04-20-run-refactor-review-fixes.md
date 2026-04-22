# Run Refactor Review Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the review regressions in the run refactor by enforcing server-side form validation and restoring correct empty-table validation in the frontend while simplifying duplicated form helpers.

**Architecture:** Keep the new `form_spec`-driven submission flow, but add one backend validation gate in `RunCompiler` so malformed envelopes fail before files are written or runs are queued. On the frontend, centralize field-emptiness logic so required-table validation, summary counts, and future field types all share one source of truth.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Next.js, React 19, Vitest, pytest

### Task 1: Backend validation guard

**Files:**
- Modify: `backend/app/services/run_compiler.py`
- Test: `backend/tests/test_services/test_run_compiler.py`
- Test: `backend/tests/test_api/test_runs.py`

**Step 1: Write the failing tests**

Add pytest coverage for:
- rejecting a missing required form field before queueing a run
- rejecting unknown field ids in `values`

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_services/test_run_compiler.py tests/test_api/test_runs.py -q`
Expected: FAIL because the compiler currently accepts incomplete / unknown values.

**Step 3: Write minimal implementation**

Add a small `RunCompiler` validation helper that:
- checks `values` against `Workflow.form_spec`
- rejects unknown non-platform-managed field ids
- rejects missing required values
- rejects type-shape mismatches for files, file lists, tables, bools, ints, floats, and selects

Raise `CompileError` with a stable validation code and short hint text.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_services/test_run_compiler.py tests/test_api/test_runs.py -q`
Expected: PASS

### Task 2: Frontend empty-table handling and simplification

**Files:**
- Modify: `frontend/lib/form-spec.ts`
- Modify: `frontend/app/(app)/workflows/components/run-submission-workbench.tsx`
- Test: `frontend/tests/integration/components/run-form.test.tsx`
- Test: `frontend/tests/integration/components/run-submission-wizard.test.tsx`

**Step 1: Write the failing tests**

Add Vitest coverage for:
- required table fields staying invalid when they have zero meaningful rows
- run summary not counting an empty table field as filled

**Step 2: Run tests to verify they fail**

Run: `bun run test -- tests/integration/components/run-form.test.tsx tests/integration/components/run-submission-wizard.test.tsx`
Expected: FAIL because empty table objects are treated as filled values.

**Step 3: Write minimal implementation**

Extract a shared field-value helper in `frontend/lib/form-spec.ts` that:
- determines whether a field has a meaningful value
- treats table values with no non-empty rows as empty

Use it from both `validateValues` and the run summary.

**Step 4: Run tests to verify they pass**

Run: `bun run test -- tests/integration/components/run-form.test.tsx tests/integration/components/run-submission-wizard.test.tsx`
Expected: PASS

### Task 3: Cleanup and verification

**Files:**
- Modify: lint-reported files with trivial unused imports only if still touched by this work

**Step 1: Keep the refactor tidy**

Remove any unused imports introduced by the branch where it is safe and low-risk.

**Step 2: Run targeted verification**

Run:
- `uv run pytest tests/test_api/test_workflow_form_spec.py tests/test_services/test_run_compiler.py tests/test_api/test_runs.py tests/test_api/test_demo_smoke.py tests/test_agent/test_run_tools.py -q`
- `bun run test -- tests/integration/components/run-form.test.tsx tests/integration/components/run-submission-wizard.test.tsx`
- `uv run ruff check .`
- `bun run lint`

Expected: PASS

**Step 3: Finish branch**

Commit the fixes, push the branch, and open a PR against `main` with a short summary of the review findings and the validation commands.
