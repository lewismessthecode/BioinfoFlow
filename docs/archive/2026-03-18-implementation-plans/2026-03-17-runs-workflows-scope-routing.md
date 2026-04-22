# Runs And Workflows Scope Routing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `runs` behave like `workflows` by supporting both global and project-scoped views, and make dashboard cards open the global runs/workflows views by default.

**Architecture:** Add explicit URL-driven scope handling to the two list pages instead of inferring the view only from `activeProjectId`. `runs` will gain a scope toggle plus conditional project filtering; `workflows` will keep its existing hub/project structure but will initialize and stay in sync with a `scope` query param so external links can force the global view.

**Tech Stack:** Next.js App Router, React 19 client components, next/navigation search params, next-intl, Vitest + Testing Library.

### Task 1: Document current behavior in tests

**Files:**
- Modify: `frontend/tests/integration/pages/runs-page.test.tsx`
- Modify: `frontend/tests/integration/pages/workflows-page.test.tsx`
- Create: `frontend/tests/integration/pages/dashboard-page.test.tsx`

**Step 1: Write the failing tests**

Add tests that prove:
- `RunsPage` can load all runs when `scope=all`, even if a project is active.
- `RunsPage` can switch between project and all scopes from the page UI.
- `WorkflowsPage` honors `scope=hub` from the URL, even if a project is active.
- `DashboardPage` links the runs and workflows stat cards to `/runs?scope=all` and `/workflows?scope=hub`.

**Step 2: Run tests to verify they fail**

Run:
```bash
cd frontend && bun run test frontend/tests/integration/pages/runs-page.test.tsx frontend/tests/integration/pages/workflows-page.test.tsx frontend/tests/integration/pages/dashboard-page.test.tsx
```

Expected:
- FAIL because `RunsPage` has no scope toggle or `scope=all` handling.
- FAIL because `WorkflowsPage` does not read scope from URL.
- FAIL because `DashboardPage` still links to `/runs` and `/workflows`.

### Task 2: Implement URL-driven scope behavior for runs

**Files:**
- Modify: `frontend/app/(app)/runs/page.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`

**Step 1: Write minimal implementation**

Update the page to:
- Read `scope` from `useSearchParams`.
- Derive `scope` as `"project"` only when explicitly requested and a project exists; otherwise allow `"all"`.
- Keep `project_id` URL support for deep links and highlighted runs.
- Fetch `/runs` with `project_id` only in project scope.
- Subscribe to `useEvents` only when project scope is active.
- Render a `Tabs` scope switch similar to `workflows`.
- Add translation keys for the runs scope labels if needed.

**Step 2: Run focused tests**

Run:
```bash
cd frontend && bun run test frontend/tests/integration/pages/runs-page.test.tsx
```

Expected:
- PASS with explicit confirmation that the correct `project_id` param is sent only for project scope.

### Task 3: Implement URL-driven default scope for workflows and dashboard links

**Files:**
- Modify: `frontend/app/(app)/workflows/page.tsx`
- Modify: `frontend/app/(app)/dashboard/page.tsx`

**Step 1: Write minimal implementation**

Update the workflows page to:
- Read `scope` from the URL.
- Initialize and synchronize view state from that param.
- Prefer hub/global view when `scope=hub`, even if `activeProjectId` exists.

Update dashboard cards to:
- Link runs card to `/runs?scope=all`
- Link workflows card to `/workflows?scope=hub`

**Step 2: Run focused tests**

Run:
```bash
cd frontend && bun run test frontend/tests/integration/pages/workflows-page.test.tsx frontend/tests/integration/pages/dashboard-page.test.tsx
```

Expected:
- PASS with dashboard links and workflows URL scope behavior verified.

### Task 4: Verify the combined behavior

**Files:**
- Modify: `frontend/app/(app)/runs/page.tsx`
- Modify: `frontend/app/(app)/workflows/page.tsx`
- Modify: `frontend/app/(app)/dashboard/page.tsx`
- Modify: `frontend/tests/integration/pages/runs-page.test.tsx`
- Modify: `frontend/tests/integration/pages/workflows-page.test.tsx`
- Create: `frontend/tests/integration/pages/dashboard-page.test.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`

**Step 1: Run the targeted regression suite**

Run:
```bash
cd frontend && bun run test frontend/tests/integration/pages/runs-page.test.tsx frontend/tests/integration/pages/workflows-page.test.tsx frontend/tests/integration/pages/dashboard-page.test.tsx
```

Expected:
- PASS for all targeted tests.

**Step 2: Run lint if the tests pass**

Run:
```bash
cd frontend && bun run lint
```

Expected:
- PASS with no new lint errors.

**Step 3: Commit**

```bash
git add docs/plans/2026-03-17-runs-workflows-scope-routing.md frontend/app/'(app)'/runs/page.tsx frontend/app/'(app)'/workflows/page.tsx frontend/app/'(app)'/dashboard/page.tsx frontend/tests/integration/pages/runs-page.test.tsx frontend/tests/integration/pages/workflows-page.test.tsx frontend/tests/integration/pages/dashboard-page.test.tsx frontend/messages/en.json frontend/messages/zh-CN.json
git commit -m "feat: add global scope routing for runs and workflows"
```
