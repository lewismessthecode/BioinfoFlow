# Frontend Performance Optimization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce frontend initial-load cost by deferring heavy app-shell features and scoping heavyweight global styles to the routes that actually need them.

**Architecture:** Keep the existing UI and data flow intact while changing loading boundaries. The app shell will lazy-load non-essential client features, the runs list will lazy-load expensive detail content, and third-party global CSS will move from the root bundle to route-specific entry points.

**Tech Stack:** Next.js 16 App Router, React 19, next/dynamic, Vitest, Testing Library, Tailwind CSS 4

### Task 1: Lock the target behavior in tests

**Files:**
- Modify: `frontend/tests/integration/pages/runs-page-core.test.tsx`

**Step 1: Write the failing test**

Add a test that expands a run row and expects an inline loading placeholder to appear before the heavy detail content resolves.

**Step 2: Run test to verify it fails**

Run: `cd frontend && bun run test frontend/tests/integration/pages/runs-page-core.test.tsx`

Expected: FAIL because the current implementation renders inline detail immediately and never shows a lazy-load placeholder.

### Task 2: Defer heavy app-shell features

**Files:**
- Modify: `frontend/app/(app)/app-layout.tsx`
- Create: `frontend/app/(app)/app-shell.css`

**Step 1: Write the failing test**

Reuse app-layout terminal integration coverage after adding lazy-loading boundaries so the terminal toggle and open behavior remain correct.

**Step 2: Run test to verify it protects behavior**

Run: `cd frontend && bun run test frontend/tests/integration/components/app-layout-terminal.test.tsx`

Expected: PASS before refactor, then PASS after refactor.

**Step 3: Write minimal implementation**

- Move the `@xterm/xterm` CSS import out of `frontend/app/globals.css` into a new app-shell-specific CSS entry.
- Lazy-load `TerminalDock` and `CommandPalette` with `next/dynamic`.
- Only render those lazy boundaries when the feature is actually reachable.

### Task 3: Split runs-page heavy detail code from the list bundle

**Files:**
- Modify: `frontend/app/(app)/runs/page.tsx`
- Modify: `frontend/app/(app)/runs/components/run-inline-detail.tsx`

**Step 1: Write the failing test**

Use the new runs-page loading-placeholder test from Task 1.

**Step 2: Run test to verify it fails**

Run: `cd frontend && bun run test frontend/tests/integration/pages/runs-page-core.test.tsx`

Expected: FAIL until the page uses a lazy-loaded inline detail with a loading fallback.

**Step 3: Write minimal implementation**

- Convert the runs page to lazy-load `RunInlineDetail`.
- Keep the existing UX, but show a compact placeholder row while the chunk loads.
- Preserve the current rerun/detail interactions once the chunk resolves.

### Task 4: Scope scheduler-only chart styles

**Files:**
- Modify: `frontend/app/globals.css`
- Create: `frontend/app/(app)/scheduler/scheduler.css`
- Modify: `frontend/app/(app)/scheduler/page.tsx`

**Step 1: Write the failing test**

No dedicated unit test needed because this is route-level CSS loading rather than app behavior. Verify via existing scheduler page test coverage and targeted lint/test runs after the change.

**Step 2: Write minimal implementation**

- Move the `uplot` CSS import out of `frontend/app/globals.css`.
- Load it from the scheduler route entry so non-scheduler pages stop paying that global style cost.

### Task 5: Verify the optimized behavior

**Files:**
- Verify: `frontend/app/(app)/app-layout.tsx`
- Verify: `frontend/app/(app)/runs/page.tsx`
- Verify: `frontend/app/(app)/runs/components/run-inline-detail.tsx`
- Verify: `frontend/app/globals.css`
- Verify: `frontend/app/(app)/app-shell.css`
- Verify: `frontend/app/(app)/scheduler/page.tsx`
- Verify: `frontend/app/(app)/scheduler/scheduler.css`
- Verify: `frontend/tests/integration/components/app-layout-terminal.test.tsx`
- Verify: `frontend/tests/integration/pages/runs-page-core.test.tsx`

**Step 1: Run targeted tests**

Run: `cd frontend && bun run test frontend/tests/integration/components/app-layout-terminal.test.tsx frontend/tests/integration/pages/runs-page-core.test.tsx`

Expected: PASS

**Step 2: Run lint**

Run: `cd frontend && bun run lint`

Expected: PASS

**Step 3: Optional production build smoke check**

Run: `cd frontend && bun run build`

Expected: May fail in this environment if Google font fetching is unavailable; record the exact failure instead of masking it.
