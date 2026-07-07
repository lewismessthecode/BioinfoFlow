# Fix Sidebar Scroll Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the desktop left sidebar pinned to the viewport while scrollable pages such as `/images` move underneath it.

**Architecture:** The app shell already reserves desktop sidebar width in `frontend/app/(app)/app-layout.tsx` and renders a full-height `Sidebar`. The fix is to make the desktop sidebar column sticky at the top of the viewport so it remains a full-height rail during document-level page scrolling.

**Tech Stack:** Next.js 16, React 19, Tailwind utility classes, Vitest source-style regression tests.

---

### Task 1: Regression Coverage

**Files:**
- Modify: `frontend/tests/unit/styles/sidebar-header-style.test.ts`

- [ ] **Step 1: Write the failing test**

Add a test that reads `app/(app)/app-layout.tsx` and asserts the desktop `<nav>` class contains `sticky top-0 h-[100dvh] self-start` while preserving the `transition-[width,opacity]` behavior.

- [ ] **Step 2: Run test to verify it fails**

Run from `frontend/`:

```bash
rtk bun run test tests/unit/styles/sidebar-header-style.test.ts
```

Expected: FAIL because the current desktop sidebar nav is `relative` and not sticky.

### Task 2: Sticky Sidebar Fix

**Files:**
- Modify: `frontend/app/(app)/app-layout.tsx`

- [ ] **Step 1: Implement the minimal layout change**

Update the desktop sidebar `<nav>` class from:

```tsx
className="relative flex-shrink-0 transition-[width,opacity] duration-200"
```

to:

```tsx
className="sticky top-0 h-[100dvh] flex-shrink-0 self-start transition-[width,opacity] duration-200"
```

- [ ] **Step 2: Run focused validation**

Run from `frontend/`:

```bash
rtk bun run test tests/unit/styles/sidebar-header-style.test.ts
```

Expected: PASS.

- [ ] **Step 3: Run frontend validation**

Run from `frontend/`:

```bash
rtk bun run lint
rtk bun run test
```

Expected: PASS.
