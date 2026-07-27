# Compact Appearance Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the detailed light and dark appearance skeletons with compact theme thumbnails that preserve palette recognition.

**Architecture:** Keep `ThemePreviewCard` inside the existing settings page client and simplify only its internal presentational markup. Continue driving all colors from `AppearanceTokens`, without changing appearance state, translations, or settings behavior.

**Tech Stack:** Next.js 16, React 19, TypeScript, Tailwind CSS, Vitest, Testing Library

---

### Task 1: Specify the compact skeleton

**Files:**
- Modify: `frontend/tests/unit/styles/settings-appearance-preview-style.test.ts`

- [ ] **Step 1: Replace the existing detailed-skeleton assertions**

```ts
it("uses a compact preview skeleton without terminal decoration", () => {
  const source = readFileSync(
    resolve(process.cwd(), "components/bioinfoflow/settings/settings-page-client.tsx"),
    "utf8"
  )

  expect(source).toContain('className="relative flex min-h-[236px] flex-col')
  expect(source).toContain('data-testid="appearance-preview-main"')
  expect(source).not.toContain('min-h-[420px]')
  expect(source).not.toContain('tokens["terminal-background"]')
})
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `rtk bun run test tests/unit/styles/settings-appearance-preview-style.test.ts` from `frontend/`.

Expected: FAIL because the component still has `min-h-[420px]` and terminal styling.

### Task 2: Simplify the preview component

**Files:**
- Modify: `frontend/components/bioinfoflow/settings/settings-page-client.tsx`

- [ ] **Step 1: Reduce the outer card height**

Use `min-h-[236px]` on the preview shell while keeping its token-backed background, border, and foreground styles.

- [ ] **Step 2: Replace the detailed application mockup**

Inside the existing card header, render one compact body with:

```tsx
<div className="relative grid flex-1 grid-cols-[72px_minmax(0,1fr)] gap-3 p-4">
  <aside>{/* logo tile and three short navigation bars */}</aside>
  <div data-testid="appearance-preview-main">
    {/* one toolbar row, one primary content block, and two small summary blocks */}
  </div>
</div>
```

All fills and borders must continue to use existing `tokens` fields. Remove the terminal panel, traffic-light dots, button pills, and nested window composition.

- [ ] **Step 3: Run the focused test and verify GREEN**

Run: `rtk bun run test tests/unit/styles/settings-appearance-preview-style.test.ts` from `frontend/`.

Expected: PASS.

### Task 3: Verify behavior and presentation

**Files:**
- Verify: `frontend/components/bioinfoflow/settings/settings-page-client.tsx`
- Verify: `frontend/tests/unit/styles/settings-appearance-preview-style.test.ts`

- [ ] **Step 1: Run focused settings tests**

Run: `rtk bun run test tests/unit/components/settings-page.test.tsx tests/integration/pages/settings-page-flow.test.tsx` from `frontend/`.

Expected: PASS with two appearance preview shells still rendered.

- [ ] **Step 2: Run frontend quality checks**

Run: `rtk bun run lint` and `rtk bun run test` from `frontend/`.

Expected: both commands exit 0.

- [ ] **Step 3: Visually verify the settings page**

Start the local app with `AUTH_MODE=dev`, open `/settings?section=appearance`, and capture desktop and narrow viewport screenshots. Confirm the two cards are compact, readable, token-distinct, and do not overflow.

### Task 4: Publish and merge

**Files:**
- Commit only the design, plan, component, and focused test files.

- [ ] **Step 1: Inspect and commit**

Run `rtk git diff --check`, inspect `rtk git diff`, explicitly stage the intended files, and commit with `fix: simplify appearance preview skeletons`.

- [ ] **Step 2: Sync and push**

Run `rtk git fetch origin --prune && rtk git rebase origin/main`, then push the branch.

- [ ] **Step 3: Create and merge the PR**

Create a ready PR titled `fix: simplify appearance preview skeletons`, wait for required checks, and merge only after GitHub reports it mergeable.
