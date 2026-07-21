# Self-Hosted Console Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the self-hosted Vercel Analytics 404 and determine whether the reported hydration error belongs to Bioinfoflow or an injected browser extension.

**Architecture:** Analytics is rendered only when explicitly enabled or running on Vercel. Hydration diagnosis uses an extension-free browser profile before any application markup changes.

**Tech Stack:** Next.js 16, React 19, Vitest, Playwright/browser smoke testing.

---

### Task 1: Gate Vercel Analytics

**Files:**
- Modify: `frontend/app/layout.tsx`
- Create or modify: `frontend/tests/unit/app/root-layout.test.tsx`
- Modify: `.env.example`

- [ ] **Step 1: Write failing layout tests**

Assert Analytics is absent by default and present when `VERCEL=1` or
`NEXT_PUBLIC_ENABLE_VERCEL_ANALYTICS=true`.

- [ ] **Step 2: Verify RED**

```bash
rtk bun run test -- tests/unit/app/root-layout.test.tsx
```

- [ ] **Step 3: Implement the explicit gate**

```tsx
const analyticsEnabled =
  process.env.VERCEL === "1" ||
  process.env.NEXT_PUBLIC_ENABLE_VERCEL_ANALYTICS === "true"

{analyticsEnabled ? <Analytics /> : null}
```

- [ ] **Step 4: Run tests and commit**

```bash
rtk bun run test -- tests/unit/app/root-layout.test.tsx
rtk git add frontend/app/layout.tsx frontend/tests/unit/app/root-layout.test.tsx .env.example
rtk git commit -m "fix: gate vercel analytics in self-hosted builds"
```

### Task 2: Hydration verification

**Files:**
- Modify only if a clean-profile reproduction identifies application-owned markup.

- [ ] **Step 1: Run a production build**

```bash
rtk bun run build
```

- [ ] **Step 2: Inspect `/settings` with extensions disabled**

Confirm whether React error 418 occurs without injected `contentScript.js`,
`ObjectMultiplex`, and EventEmitter warnings.

- [ ] **Step 3: Apply evidence-based action**

If no clean-profile reproduction exists, record the extension attribution in
the PR and make no hydration code change. If it reproduces, add a minimal
failing component test before changing markup.

- [ ] **Step 4: Run frontend verification**

```bash
rtk bun run lint
rtk bun run test
```
