# Demo UI Runtime Parity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reproduce the `codex/demo-runtime` workflow cards, image cards, DAG presentation, and run detail presentation on the main worktree by porting the same runtime/data wiring and page-level code paths.

**Architecture:** The visual deltas are not isolated to leaf card components. The demo branch adds a runtime abstraction, demo scenario data, and app-shell wiring that preselect project context, feed complete seeded data, and hide noisy live-only controls. The implementation should first add parity tests, then port the runtime and page wiring required for those UI surfaces to render identically.

**Tech Stack:** Next.js App Router, React, next-intl, Vitest, Testing Library, TypeScript

### Task 1: Add parity tests for the four demo surfaces

**Files:**
- Create: `frontend/tests/integration/pages/demo-runtime-workflows.test.tsx`
- Create: `frontend/tests/integration/pages/demo-runtime-images.test.tsx`
- Create: `frontend/tests/integration/pages/demo-runtime-run-detail.test.tsx`
- Create: `frontend/tests/unit/lib/runtime/runtime-provider.test.tsx`
- Create: `frontend/tests/unit/lib/runtime/demo-runtime.test.ts`

**Step 1: Write the failing tests**

Port the demo branch tests that assert:
- project-scoped workflow cards render the seeded workflow and launch path
- seeded image cards render local/remote statuses
- run detail page hydrates the seeded run and updates to completed replay state
- runtime provider can resolve demo/live modes and expose the correct runtime

**Step 2: Run tests to verify they fail**

Run:
```bash
cd /Users/lewisliu/Dev/ACTIVE/bioinfoflow/frontend
bun run test --run tests/integration/pages/demo-runtime-workflows.test.tsx tests/integration/pages/demo-runtime-images.test.tsx tests/integration/pages/demo-runtime-run-detail.test.tsx tests/unit/lib/runtime/runtime-provider.test.tsx tests/unit/lib/runtime/demo-runtime.test.ts
```

Expected:
- Fails because runtime modules and/or demo scenario wiring are missing from `main`

**Step 3: Commit**

```bash
git add frontend/tests/integration/pages/demo-runtime-workflows.test.tsx frontend/tests/integration/pages/demo-runtime-images.test.tsx frontend/tests/integration/pages/demo-runtime-run-detail.test.tsx frontend/tests/unit/lib/runtime/runtime-provider.test.tsx frontend/tests/unit/lib/runtime/demo-runtime.test.ts
git commit -m "test: add demo runtime UI parity coverage"
```

### Task 2: Port runtime abstraction and seeded scenario wiring

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/hooks/use-events.ts`
- Modify: `frontend/app/(app)/app-layout.tsx`
- Modify: `frontend/app/(app)/layout.tsx`
- Create: `frontend/lib/runtime/index.ts`
- Create: `frontend/lib/runtime/provider.tsx`
- Create: `frontend/lib/runtime/live-runtime.ts`
- Create: `frontend/lib/runtime/request-core.ts`
- Create: `frontend/lib/runtime/resolve-mode.ts`
- Create: `frontend/lib/runtime/types.ts`
- Create: `frontend/lib/runtime/demo-runtime.ts`
- Create: `frontend/lib/demo/scenario.ts`
- Create or replace: `frontend/lib/demo/scenario-data.ts`
- Create: `frontend/lib/deploy-mode.ts`
- Create: `frontend/lib/demo-auth.ts`

**Step 1: Port the exact demo runtime implementation**

Copy the corresponding files from `codex/demo-runtime` so that:
- `apiRequest` and event subscription go through the active runtime
- the app shell can start with `runtime.contextDefaults.selectedProjectId`
- demo mode can serve seeded workflows/images/runs/DAG data

**Step 2: Run the targeted tests to verify they pass**

Run:
```bash
cd /Users/lewisliu/Dev/ACTIVE/bioinfoflow/frontend
bun run test --run tests/integration/pages/demo-runtime-workflows.test.tsx tests/integration/pages/demo-runtime-images.test.tsx tests/integration/pages/demo-runtime-run-detail.test.tsx tests/unit/lib/runtime/runtime-provider.test.tsx tests/unit/lib/runtime/demo-runtime.test.ts
```

Expected:
- PASS

**Step 3: Commit**

```bash
git add frontend/lib/api.ts frontend/hooks/use-events.ts frontend/app/(app)/app-layout.tsx frontend/app/(app)/layout.tsx frontend/lib/runtime frontend/lib/demo frontend/lib/deploy-mode.ts frontend/lib/demo-auth.ts
git commit -m "feat: port demo runtime wiring for UI parity"
```

### Task 3: Port run-surface gating and demo-mode entrypoints needed for parity

**Files:**
- Modify: `frontend/app/(app)/runs/components/run-detail-content.tsx`
- Modify: `frontend/app/(app)/runs/page.tsx`
- Modify: `frontend/app/auth/page.tsx`
- Modify: `frontend/app/page.tsx`
- Create: `frontend/app/api/demo-auth/route.ts`
- Create: `frontend/components/auth/demo-auth-screen.tsx`
- Create: `frontend/components/landing/demo-landing-page.tsx`
- Modify: `frontend/proxy.ts`
- Modify: `frontend/lib/auth-config.ts`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`

**Step 1: Port the exact page-level code paths from `codex/demo-runtime`**

This includes:
- run actions respecting runtime capabilities
- demo auth/entry flow needed to reach the seeded surfaces in demo mode
- locale strings required by the new entry/auth UI

**Step 2: Run focused frontend verification**

Run:
```bash
cd /Users/lewisliu/Dev/ACTIVE/bioinfoflow/frontend
bun run test --run tests/integration/pages/demo-runtime-workflows.test.tsx tests/integration/pages/demo-runtime-images.test.tsx tests/integration/pages/demo-runtime-run-detail.test.tsx tests/unit/auth-page.test.tsx tests/unit/root-page.test.tsx tests/unit/middleware-demo.test.ts
```

Expected:
- PASS

**Step 3: Commit**

```bash
git add frontend/app/(app)/runs/components/run-detail-content.tsx frontend/app/(app)/runs/page.tsx frontend/app/auth/page.tsx frontend/app/page.tsx frontend/app/api/demo-auth/route.ts frontend/components/auth/demo-auth-screen.tsx frontend/components/landing/demo-landing-page.tsx frontend/proxy.ts frontend/lib/auth-config.ts frontend/messages/en.json frontend/messages/zh-CN.json
git commit -m "feat: align demo-mode run surfaces and entry flow"
```

### Task 4: Final parity verification

**Files:**
- Verify only

**Step 1: Run the relevant verification commands**

Run:
```bash
cd /Users/lewisliu/Dev/ACTIVE/bioinfoflow/frontend
bun run test --run tests/integration/pages/demo-runtime-workflows.test.tsx tests/integration/pages/demo-runtime-images.test.tsx tests/integration/pages/demo-runtime-run-detail.test.tsx tests/unit/lib/runtime/runtime-provider.test.tsx tests/unit/lib/runtime/demo-runtime.test.ts tests/unit/auth-page.test.tsx tests/unit/root-page.test.tsx tests/unit/middleware-demo.test.ts
```

Run:
```bash
cd /Users/lewisliu/Dev/ACTIVE/bioinfoflow/frontend
bun run lint
```

Run:
```bash
cd /Users/lewisliu/Dev/ACTIVE/bioinfoflow/frontend
bun run lint:i18n
```

**Step 2: Commit**

```bash
git add -A
git commit -m "test: verify demo UI parity"
```
