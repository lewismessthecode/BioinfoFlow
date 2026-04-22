# Run And Workflow UI Refresh Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Repair run detail regressions and upgrade the key workflow surfaces so run details, output files, registration, submission, Hub cards, and source diff all feel stable, readable, and production-ready.

**Architecture:** Keep the existing Next.js App Router structure and current component boundaries, but harden the run artifact data flow and rebalance page-level layouts. Prefer targeted component refactors plus a small backend artifact-path fallback rather than rewriting screens.

**Tech Stack:** Next.js 16, React 19, Tailwind CSS 4, Radix UI, React Flow, FastAPI, Vitest, pytest

### Task 1: Lock output-file behavior before changing code

**Files:**
- Modify: `frontend/tests/integration/components/run-detail-content.test.tsx`
- Modify: `backend/tests/test_api/test_runs_artifacts.py`

**Step 1: Write the failing frontend regression test**

Add a test that opens the run detail files tab, selects an output file, and verifies preview loading uses a stable artifact read path instead of failing with `file not found`.

**Step 2: Run the focused frontend test to verify it fails**

Run: `bun run test frontend/tests/integration/components/run-detail-content.test.tsx`

Expected: FAIL because the current preview path handling does not cover the broken output-file case.

**Step 3: Write the failing backend regression test**

Add a test covering completed runs whose outputs live in a valid configured `outdir` even when the default run results root is empty or missing.

**Step 4: Run the focused backend test to verify it fails**

Run: `cd backend && uv run pytest tests/test_api/test_runs_artifacts.py -v`

Expected: FAIL because the current archive service only checks the canonical run results root.

### Task 2: Fix run artifact resolution and make run detail resilient

**Files:**
- Modify: `backend/app/services/run_archive.py`
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/app/(app)/runs/[runId]/page.tsx`
- Modify: `frontend/app/(app)/runs/components/run-detail-content.tsx`
- Modify: `frontend/app/(app)/runs/components/run-detail-utils.ts`

**Step 1: Implement backend output-path fallback**

Teach `RunArchiveService.resolve_output_path()` to prefer the canonical run results directory, but fall back to configured `outdir` values that still resolve inside the project workspace.

**Step 2: Include stable preview metadata in run outputs**

Extend run output items with optional artifact URIs so the frontend can preview files via storage APIs when available.

**Step 3: Harden run-detail data fetching**

Replace the all-or-nothing `Promise.all` branch in `runs/[runId]/page.tsx` with independent loading so a single missing artifact does not collapse the rest of the page.

**Step 4: Update files-tab preview logic**

Use the new output metadata to preview through the most stable read path, keep download behavior intact, and render an explicit tab-level load error instead of silently showing an empty state.

**Step 5: Re-run the focused tests**

Run:
- `bun run test frontend/tests/integration/components/run-detail-content.test.tsx`
- `cd backend && uv run pytest tests/test_api/test_runs_artifacts.py -v`

Expected: PASS

### Task 3: Rebuild run detail layout and DAG UX

**Files:**
- Modify: `frontend/app/(app)/runs/[runId]/page.tsx`
- Modify: `frontend/app/(app)/runs/components/run-detail-content.tsx`
- Modify: `frontend/app/(app)/runs/components/run-audit-tab.tsx`
- Modify: `frontend/app/(app)/runs/components/dag-fullscreen-dialog.tsx`
- Modify: `frontend/components/bioinfoflow/dag/dag-panel.tsx`
- Modify: `frontend/tests/integration/components/run-detail-content.test.tsx`

**Step 1: Write a failing layout test**

Add a test that asserts the full-page run layout keeps a larger DAG viewport and exposes the revised content frame classes used to fill the page.

**Step 2: Run the focused test to verify it fails**

Run: `bun run test frontend/tests/integration/components/run-detail-content.test.tsx`

Expected: FAIL because the current page still clamps the DAG area and leaves excessive empty space.

**Step 3: Refactor the run detail page shell**

Use a wider container, stronger desktop grid, taller content frame, and a better failure message block that scrolls instead of exploding the layout.

**Step 4: Improve DAG usability**

Make tall linear DAGs auto-present better in landscape, reduce over-aggressive fit padding, enlarge the embedded viewport, and expose helpful summary affordances without changing the theme.

**Step 5: Clarify the audit tab**

Keep audit, but explain its purpose, compress the empty space, and switch the timeline into a denser, clearer activity feed.

**Step 6: Re-run the focused test**

Run: `bun run test frontend/tests/integration/components/run-detail-content.test.tsx`

Expected: PASS

### Task 4: Tighten the run submission wizard and file browser

**Files:**
- Modify: `frontend/app/(app)/workflows/components/run-submission-wizard.tsx`
- Modify: `frontend/app/(app)/workflows/components/run-submission-workbench.tsx`
- Modify: `frontend/app/(app)/workflows/components/json-input-editor.tsx`
- Modify: `frontend/app/(app)/workflows/components/samplesheet-editor.tsx`
- Modify: `frontend/components/bioinfoflow/file-browser-dialog.tsx`
- Modify: `frontend/tests/integration/components/run-submission-wizard.test.tsx`

**Step 1: Add a failing wizard/UI regression test**

Capture the intended workbench structure and key copy so the right side no longer reads as dead empty space.

**Step 2: Run the focused wizard test to verify it fails**

Run: `bun run test frontend/tests/integration/components/run-submission-wizard.test.tsx`

Expected: FAIL after asserting the new structure or labels.

**Step 3: Rebalance the wizard**

Turn the workbench into a denser split layout, surface summary/help where the blank area used to be, and keep the bottom action zone visually anchored.

**Step 4: Upgrade the file browser**

Reorder storage sources by likely submission scenarios, improve tab treatment, spacing, toolbar clarity, and selection affordances without changing backend behavior.

**Step 5: Re-run the focused wizard test**

Run: `bun run test frontend/tests/integration/components/run-submission-wizard.test.tsx`

Expected: PASS

### Task 5: Simplify workflow registration and polish Hub/detail views

**Files:**
- Modify: `frontend/app/(app)/workflows/components/workflow-register-dialog.tsx`
- Modify: `frontend/app/(app)/workflows/components/register-form-fields.tsx`
- Modify: `frontend/app/(app)/workflows/components/register-preview-panel.tsx`
- Modify: `frontend/app/(app)/workflows/components/hub-workflow-card.tsx`
- Modify: `frontend/app/(app)/workflows/components/workflow-card-base.tsx`
- Modify: `frontend/app/(app)/workflows/[id]/components/workflow-source-tab.tsx`
- Modify: `frontend/tests/integration/components/workflow-register-dialog.test.tsx`
- Modify: `frontend/tests/integration/pages/workflow-detail-page.test.tsx`

**Step 1: Add failing registration and source-diff assertions**

Cover the lighter registration copy, stable source-type panel sizing, and the revised GitHub-style diff presentation.

**Step 2: Run the focused tests to verify they fail**

Run:
- `bun run test frontend/tests/integration/components/workflow-register-dialog.test.tsx`
- `bun run test frontend/tests/integration/pages/workflow-detail-page.test.tsx`

Expected: FAIL

**Step 3: Streamline the registration dialog**

Remove low-value explanatory copy, stabilize source-type card heights so the frame does not jump, and keep the preview useful but lighter.

**Step 4: Improve Hub cards**

Turn the version/count treatment into a clearer pill-plus-dropdown style while preserving existing actions.

**Step 5: Rebuild source diff**

Switch the split diff layout to a denser GitHub-like presentation with tighter line height, fixed gutters, sticky headers, and one natural scroll container instead of per-line horizontal scroll.

**Step 6: Re-run the focused tests**

Run:
- `bun run test frontend/tests/integration/components/workflow-register-dialog.test.tsx`
- `bun run test frontend/tests/integration/pages/workflow-detail-page.test.tsx`

Expected: PASS

### Task 6: Final verification

**Files:**
- No additional code files required

**Step 1: Run focused frontend verification**

Run:
- `bun run test frontend/tests/integration/components/run-detail-content.test.tsx`
- `bun run test frontend/tests/integration/components/run-submission-wizard.test.tsx`
- `bun run test frontend/tests/integration/components/workflow-register-dialog.test.tsx`
- `bun run test frontend/tests/integration/pages/workflow-detail-page.test.tsx`

**Step 2: Run focused backend verification**

Run:
- `cd backend && uv run pytest tests/test_api/test_runs_artifacts.py -v`

**Step 3: Run broader guardrail checks if time permits**

Run:
- `cd frontend && bun run lint`

**Step 4: Summarize residual risk**

Call out any unverified browser-only behavior, especially React Flow auto-layout perception and long-run artifact edge cases.
