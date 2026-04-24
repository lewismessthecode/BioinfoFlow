# App Page Performance Batch 2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Unblock reliable production auditing for authenticated app routes, then ship the highest-value application-page performance fixes from that audit.

**Architecture:** First fix the frontend standalone auth runtime so production-like app routes can actually boot. The fix stays narrowly focused on the `better-sqlite3` ABI guard path. Once the auth/runtime path is healthy, rerun production Lighthouse against app routes and only implement optimizations supported by those results.

**Tech Stack:** Next.js 16 standalone output, Node.js, better-auth, better-sqlite3, Vitest

### Task 1: Guard against lazy native-module ABI failures

**Files:**
- Modify: `frontend/scripts/ensure-better-sqlite3-node-abi.mjs`
- Create: `frontend/scripts/better-sqlite3-node-abi.mjs`
- Test: `frontend/tests/unit/scripts/better-sqlite3-node-abi.test.ts`

**Step 1: Write the failing test**

Add a unit test that simulates a `better-sqlite3` package whose top-level import succeeds but whose first `new Database(...)` throws an ABI mismatch error. The test should expect the verifier to treat that as an ABI mismatch and request a rebuild.

**Step 2: Run test to verify it fails**

Run: `cd frontend && bun run test tests/unit/scripts/better-sqlite3-node-abi.test.ts`

Expected: FAIL because the current script only checks `require("better-sqlite3")`.

**Step 3: Write minimal implementation**

- Extract reusable verifier/rebuild logic into `frontend/scripts/better-sqlite3-node-abi.mjs`.
- Verify the package by opening and closing an in-memory database so the native binary is actually loaded.
- Keep the CLI wrapper script thin.

**Step 4: Run test to verify it passes**

Run: `cd frontend && bun run test tests/unit/scripts/better-sqlite3-node-abi.test.ts`

Expected: PASS

### Task 2: Verify standalone auth runtime

**Files:**
- Verify: `frontend/lib/auth.ts`
- Verify: `frontend/app/auth/page.tsx`

**Step 1: Rebuild frontend**

Run: `cd frontend && bun run build`

Expected: PASS

**Step 2: Verify standalone route boot**

Run: `cd frontend && PORT=3002 node .next/standalone/server.js`

Then verify:
- `curl -I http://127.0.0.1:3002/auth`
- `curl -I http://127.0.0.1:3002/agent`

Expected: No `better-sqlite3` ABI crash.

### Task 3: Rerun production app-page audits

**Files:**
- Verify only

**Step 1: Audit representative app routes**

Run Lighthouse against production-like routes reachable after Task 2, prioritizing:
- `/agent`
- `/dashboard` or `/runs`

Expected: Stable production numbers without dev-only chunk noise.

**Step 2: Pick one optimization batch**

Only optimize the largest real bottleneck shown by the new audit. Do not batch unrelated tweaks.

### Task 4: Ship the chosen app-page optimization batch

**Files:**
- Modify only the routes/components supported by Task 3 findings
- Add or update tests for any behavior changes

**Step 1: Write failing tests for any user-visible behavior change**

Use route/component-specific tests based on the chosen optimization.

**Step 2: Implement the minimal fix**

Keep the batch tightly scoped to the measured bottleneck.

**Step 3: Verify**

Run the targeted tests, then:
- `cd frontend && bun run lint`
- `cd frontend && bun run lint:i18n` (if messages changed)
- `cd frontend && bun run build`

### Task 5: Commit the batch

**Files:**
- Stage only files belonging to this batch

**Step 1: Inspect staged diff**

Run: `git diff --cached --stat`

**Step 2: Commit**

Run a single commit after verification passes.
