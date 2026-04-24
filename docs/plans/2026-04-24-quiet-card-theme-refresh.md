# Quiet Card Theme Refresh Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refresh the workflow and image cards with a quieter, more editor-like icon treatment while making metadata pills and DAG chrome align better with the appearance preset system.

**Architecture:** Keep business-semantic status colors stable, but move decorative metadata chrome onto appearance-aware tokens. Reuse shared card-shell helpers where possible so workflow and image cards feel related without looking identical. Add regression tests around the card chrome and token-driven pill styles before changing production components.

**Tech Stack:** Next.js App Router, React 19, Tailwind CSS 4, Radix UI, Vitest, Testing Library

### Task 1: Add regression tests for card chrome and token-aware pills

**Files:**
- Modify: `frontend/tests/unit/workflows/workflow-pills.test.tsx`
- Create: `frontend/tests/unit/images/image-card-grid.test.tsx`

**Step 1: Write the failing test**

Add tests that assert:
- workflow metadata pills use semantic appearance utility classes instead of hardcoded blue/emerald/amber palettes
- image cards render the status badge separately from the tag and keep the local badge visible
- image and workflow cards expose the refreshed icon container structure

**Step 2: Run test to verify it fails**

Run: `cd frontend && bun run test -- workflow-pills image-card-grid`

Expected: FAIL because the current components still use the older card/icon chrome and hardcoded pill classes.

**Step 3: Write minimal implementation**

Update the card components and pill styles just enough to satisfy the new tests.

**Step 4: Run test to verify it passes**

Run: `cd frontend && bun run test -- workflow-pills image-card-grid`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/tests/unit/workflows/workflow-pills.test.tsx frontend/tests/unit/images/image-card-grid.test.tsx
git commit -m "test: cover quiet card chrome and themed pills"
```

### Task 2: Refresh workflow and image card icon design

**Files:**
- Modify: `frontend/app/(app)/workflows/components/workflow-card-base.tsx`
- Modify: `frontend/app/(app)/images/components/image-views.tsx`
- Modify: `frontend/app/(app)/workflows/components/project-group-card.tsx`
- Modify: `frontend/app/(app)/workflows/components/hub-workflow-card.tsx`

**Step 1: Write the failing test**

Assert that workflow cards use a graph-like icon and image cards use a package/container icon with a quieter single-layer tile treatment.

**Step 2: Run test to verify it fails**

Run: `cd frontend && bun run test -- workflow-pills image-card-grid`

Expected: FAIL on icon container assertions.

**Step 3: Write minimal implementation**

Implement the quiet icon tiles, update the glyphs, and keep the overall layout intact.

**Step 4: Run test to verify it passes**

Run: `cd frontend && bun run test -- workflow-pills image-card-grid`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/app/(app)/workflows/components/workflow-card-base.tsx frontend/app/(app)/images/components/image-views.tsx frontend/app/(app)/workflows/components/project-group-card.tsx frontend/app/(app)/workflows/components/hub-workflow-card.tsx
git commit -m "feat: refresh workflow and image card chrome"
```

### Task 3: Make metadata pills and DAG chrome appearance-aware

**Files:**
- Modify: `frontend/app/(app)/workflows/components/workflow-pills.tsx`
- Modify: `frontend/components/bioinfoflow/dag/dag-header.tsx`
- Modify: `frontend/app/globals.css`

**Step 1: Write the failing test**

Assert that workflow metadata pills no longer depend on hardcoded brand palettes and that the run-status dots pull from semantic/custom properties instead of raw emerald shades.

**Step 2: Run test to verify it fails**

Run: `cd frontend && bun run test -- workflow-pills`

Expected: FAIL because the existing implementation still hardcodes palette classes.

**Step 3: Write minimal implementation**

Introduce appearance-aware utility classes/CSS variables for metadata pills and soften DAG ambient tokens while preserving semantic status colors.

**Step 4: Run test to verify it passes**

Run: `cd frontend && bun run test -- workflow-pills`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/app/(app)/workflows/components/workflow-pills.tsx frontend/components/bioinfoflow/dag/dag-header.tsx frontend/app/globals.css
git commit -m "feat: align metadata pills and dag chrome with themes"
```

### Task 4: Verify and review

**Files:**
- Modify: none expected

**Step 1: Run focused verification**

Run: `cd frontend && bun run test -- workflow-pills image-card-grid`

**Step 2: Run broader verification**

Run: `cd frontend && bun run lint`

**Step 3: Review the diff**

Run: `git diff --stat` and `git diff --check`

**Step 4: Final commit check**

Confirm the worktree is clean except for the pre-existing untracked plan doc outside this feature scope if it remains.
