# Semantic Highlight Colors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace inconsistent success and failure/destructive highlights with the approved balanced tonal system across the frontend in light and dark modes.

**Architecture:** Define the complete semantic palette once in `app/globals.css`, expose every role through Tailwind v4 theme mappings, and migrate semantic component styles to those utilities. A source-level Vitest regression test protects the selected values and prevents the audited components from returning to hard-coded green/red utilities.

**Tech Stack:** Next.js 16, React 19, Tailwind CSS 4, Vitest 4, TypeScript

---

### Task 1: Add semantic color regression coverage

**Files:**
- Create: `frontend/tests/unit/styles/semantic-highlight-colors.test.ts`
- Modify: `frontend/tests/unit/styles/workflow-source-diff-style.test.ts`

- [ ] **Step 1: Write the failing palette test**

Create a Vitest source test that reads `app/globals.css` and asserts the eight approved light and dark foreground/base values, four muted surfaces, four borders, and Tailwind mappings for `success-foreground`, `success-muted`, `success-border`, `error`, `error-foreground`, `error-muted`, and `error-border`.

- [ ] **Step 2: Write the failing component migration test**

In the same file, read the audited semantic component sources and assert that they do not contain `emerald-*`, `green-*`, `red-*`, `rose-*`, or the retired semantic hexadecimal values. Assert that Composer uses `bg-success-muted`, DAG nodes contain no `shadow-[0_0_12px_var(--success-border)]` or failure equivalent, and Sonner consumes the explicit error surface tokens.

- [ ] **Step 3: Update the workflow diff expectation**

Replace expectations for `bg-rose-50/90` and `bg-emerald-50/90` with `bg-error-muted` and `bg-success-muted` so the existing test describes the unified design.

- [ ] **Step 4: Run the focused tests and verify RED**

Run:

```bash
rtk bun run test -- tests/unit/styles/semantic-highlight-colors.test.ts tests/unit/styles/workflow-source-diff-style.test.ts tests/unit/styles/dag-theme-style.test.ts
```

Expected: failures for missing approved tokens, remaining hard-coded semantic colors, Composer hard-coding, DAG colored shadows, and old workflow diff classes.

### Task 2: Define the light and dark semantic token system

**Files:**
- Modify: `frontend/app/globals.css`
- Modify: `frontend/components/ui/status-badge.tsx`
- Modify: `frontend/components/ui/button.tsx`
- Modify: `frontend/components/ui/sonner.tsx`

- [ ] **Step 1: Add approved light tokens**

Set success base/foreground/muted/border to `#3F8A5D`, `#2F744A`, `#E9F3EC`, and `#C6DEC9`. Set error base/foreground/muted/border to `#C0575C`, `#984248`, `#F9EAEC`, and `#E9C5C8`. Map `--destructive` to the error base and use white destructive foreground in light mode.

- [ ] **Step 2: Add independently calibrated dark tokens**

Set success base/foreground/muted/border to `#5DBB7C`, `#78C991`, `#17271D`, and `#31563D`. Set error base/foreground/muted/border to `#D96C72`, `#E58A8E`, `#2D1B1D`, and `#60383C`. Use the dark neutral foreground for solid destructive controls.

- [ ] **Step 3: Expose all semantic roles to Tailwind**

Add `--color-success-muted`, `--color-success-border`, `--color-error`, `--color-error-foreground`, `--color-error-muted`, and `--color-error-border` mappings under `@theme inline`.

- [ ] **Step 4: Route shared UI primitives through the roles**

Use semantic foreground roles in `StatusBadge`, use `text-destructive-foreground` in the destructive button variant, and replace Sonner color mixing with `var(--error-muted)`, `var(--error-foreground)`, and `var(--error-border)`.

- [ ] **Step 5: Run focused tests**

Run the Task 1 command. Expected: palette and shared primitive assertions pass; component migration assertions still identify remaining files.

### Task 3: Migrate application status components

**Files:**
- Modify: `frontend/app/(demo)/demo/page.tsx`
- Modify: `frontend/app/(app)/connections/components/connection-list.tsx`
- Modify: `frontend/app/(app)/connections/components/connection-ui.tsx`
- Modify: `frontend/components/bioinfoflow/agent-core/agent-core-turn-block.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/connected-node-selector.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/todo-checklist.tsx`
- Modify: `frontend/components/bioinfoflow/card/card-base.tsx`
- Modify: `frontend/components/bioinfoflow/remote-connection-status.tsx`
- Modify: `frontend/components/bioinfoflow/run-stage-panel.tsx`
- Modify: `frontend/app/(app)/workflows/components/register-sub-components.tsx`

- [ ] **Step 1: Replace online/completed hard-coding**

Use `success`, `success-foreground`, `success-muted`, and `success-border` utilities for completed turns, active demo states, online connections, checklist completion, successful cards, run stages, and registration progress.

- [ ] **Step 2: Replace offline/error hard-coding**

Use `error`, `error-foreground`, `error-muted`, and `error-border` utilities for offline/error connection states and error cards.

- [ ] **Step 3: Remove status glows**

Replace remote connection colored shadow rings with a neutral/semantic muted ring or a flat semantic dot so state remains legible without neon-style outer glow.

- [ ] **Step 4: Run focused tests**

Run the Task 1 command. Expected: these component sources no longer trigger hard-coded semantic color assertions.

### Task 4: Migrate Composer, DAG, dialogs, diffs, and environment summaries

**Files:**
- Modify: `frontend/components/bioinfoflow/composer-selector-chip.ts`
- Modify: `frontend/components/bioinfoflow/dag/dag-node.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-composer.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/artifact-viewers.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/connect-model-dialog.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-environment-card.tsx`
- Modify: `frontend/components/bioinfoflow/settings/llm-catalog-panel.tsx`
- Modify: `frontend/app/(app)/workflows/[id]/components/workflow-source-tab.tsx`

- [ ] **Step 1: Unify Composer execution styling**

Replace every execution green hexadecimal class with semantic token utilities for marker, border, surface, text, and hover states. Replace Composer error treatments with error token utilities.

- [ ] **Step 2: Flatten DAG terminal states**

Keep semantic node borders/icons and edges, but remove success and failure colored outer shadows.

- [ ] **Step 3: Migrate error panels and environment summaries**

Use semantic error roles for model/catalog error panels and stderr/deletions. Use success roles for command/addition/completion treatments.

- [ ] **Step 4: Migrate workflow source diffs**

Use muted semantic surfaces and semantic foregrounds/borders for additions and removals in both themes instead of Tailwind emerald/rose palettes.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run the Task 1 command. Expected: all focused tests pass.

### Task 5: Audit, review, and verify the complete frontend

**Files:**
- Modify only additional frontend files proven by the semantic audit to contain success/failure hard-coding.

- [ ] **Step 1: Run the semantic source audit**

Search for `emerald-*`, `green-*`, `red-*`, `rose-*`, and retired semantic hex values. Classify remaining matches; preserve only brand/decorative colors such as Google logo fills and non-semantic landing/auth accents.

- [ ] **Step 2: Review the diff against the design**

Check that every semantic component uses shared roles, dark values are independently calibrated, color is not the sole state signal, and no unrelated layout or behavior changed.

- [ ] **Step 3: Run full verification**

From `frontend/` run:

```bash
rtk bun run lint
rtk bun run lint:i18n
rtk bun run lint:dead-code
rtk bun run test
rtk bun run build
```

From the repository root run:

```bash
rtk git diff --check
rtk git status --short
```

Expected: every command exits zero, with only intended files plus the local ignored/untracked visual companion directory outside the staged change.

- [ ] **Step 4: Commit implementation**

Stage the implementation plan, tests, styles, and component migrations. Commit with:

```bash
rtk git commit -m "fix: unify semantic highlight colors"
```

- [ ] **Step 5: Sync, push, and open the PR**

Fetch and rebase onto `origin/main`, rerun focused verification if the rebase changes files, push `codex/unify-semantic-colors`, and create a PR titled `fix: unify semantic highlight colors` with the design summary and verification evidence.
