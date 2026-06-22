# Askuser UI UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign Bioinfoflow's `ask_user` decision cards so agent questions feel like compact inline checkpoints with recommended options and a first-class custom text answer.

**Architecture:** Keep the existing agent-runtime decision flow and `AgentAnswer` payload shape. Extract shared ask-user card behavior into a focused component used by both pending decisions and inline transcript decisions so the two surfaces stay consistent. Do not change backend event schemas.

**Tech Stack:** Next.js 16, React 19, TypeScript, next-intl, Vitest, Testing Library, Tailwind classes, lucide-react icons.

---

## Screenshot Design Notes

The boxed Codex UI has three related states:

- A compact answered marker: a small muted pill that says a question was already asked, keeping the transcript readable after the interaction is resolved.
- A collapsed answered question block: a subtle card with the status label, disclosure arrow, the original question, and the user's answer in lower-contrast text.
- An active ask-user panel: an inline rounded panel inside the transcript with a muted status label, a clear question, numbered options, a highlighted recommended option, small help affordances, a visible custom input row, secondary skip/ignore action, and primary submit action.

The design principles to carry into Bioinfoflow are:

- Keep questions inline with the agent transcript instead of using a modal, so the user sees the reason for the interruption.
- Make options scannable with numbers, labels, descriptions, and a recommended default when the agent marks one.
- Keep the active panel calm and compact; it should feel like a workflow checkpoint rather than a full form.
- Give users a real custom answer option. It should not be hidden behind a tiny "Other" link.
- Use progressive disclosure where resolved questions take less space than active questions.

Bioinfoflow should adapt this with a lab/workflow personality: "agent checkpoint" language, restrained teal/blue accents, numbered option rails, a custom answer row with an edit icon, and dense but readable spacing that fits the existing workbench.

## File Structure

- Modify `frontend/components/bioinfoflow/agent-runtime/ask-user-card.tsx`
  - New shared client component for pending and inline ask-user cards.
  - Owns selection state, custom input state, completeness, answer serialization, and accessible controls.
- Modify `frontend/components/bioinfoflow/agent-runtime/pending-decision-cards.tsx`
  - Replace local `AskUserCard` implementation with the shared component.
- Modify `frontend/components/bioinfoflow/agent-runtime/inline-approval-card.tsx`
  - Replace local `InlineAskUserCard` implementation with the shared component.
- Modify `frontend/lib/agent-runtime/types.ts`
  - Add optional option metadata used by UI only when present: `recommended?: boolean`.
- Modify `frontend/messages/en.json`
  - Add `agentRuntime.ask.customPlaceholder`, `agentRuntime.ask.customLabel`, `agentRuntime.ask.recommended`, `agentRuntime.ask.skip`, and compact helper copy if needed.
- Modify `frontend/messages/zh-CN.json`
  - Add matching translations.
- Modify `frontend/tests/unit/components/agent-runtime-panel.test.tsx`
  - Cover pending card custom answer behavior.
- Modify `frontend/tests/unit/components/agent-transcript.test.tsx`
  - Cover inline card recommended option rendering and custom answer behavior.

## Task 1: Planning Phase

**Files:**
- Create: `docs/plans/2026-06-22-askuser-ui-ux.md`

- [x] **Step 1: Write the design and implementation plan**

  This document records the visual target, file map, TDD tasks, verification commands, and phase commits.

- [ ] **Step 2: Validate plan formatting**

  Run: `rtk git diff --check`

  Expected: exit code 0.

- [ ] **Step 3: Commit the plan**

  Run:

  ```bash
  rtk git add docs/plans/2026-06-22-askuser-ui-ux.md
  rtk git commit -m "docs: plan askuser ui ux"
  ```

## Task 2: Tests First

**Files:**
- Modify: `frontend/tests/unit/components/agent-runtime-panel.test.tsx`
- Modify: `frontend/tests/unit/components/agent-transcript.test.tsx`

- [ ] **Step 1: Add pending-card custom answer test**

  In `frontend/tests/unit/components/agent-runtime-panel.test.tsx`, add a test under `describe("PendingDecisionCards")` that renders an `ask_user` decision with options, types into the custom answer input, submits, and expects:

  ```ts
  expect(onDecision).toHaveBeenCalledWith("a1", "answer", {
    answer: { DB: "DuckDB with parquet staging" },
  })
  ```

- [ ] **Step 2: Verify pending-card test fails**

  Run: `rtk bun run test -- --run frontend/tests/unit/components/agent-runtime-panel.test.tsx`

  Expected: FAIL because no custom answer input exists.

- [ ] **Step 3: Add inline-card custom and recommended test**

  In `frontend/tests/unit/components/agent-transcript.test.tsx`, update or add an inline `ask_user` test that includes `{ label: "hg38", description: "Human GRCh38", recommended: true }`, expects the recommended badge to render, types a custom answer, submits, and expects:

  ```ts
  expect(onDecision).toHaveBeenCalledWith("action-ask", "answer", {
    answer: { Genome: "T2T-CHM13" },
  })
  ```

- [ ] **Step 4: Verify inline-card test fails**

  Run: `rtk bun run test -- --run frontend/tests/unit/components/agent-transcript.test.tsx`

  Expected: FAIL because recommended/custom UI is not implemented.

- [ ] **Step 5: Commit failing tests is not allowed**

  Keep tests unstaged until Task 3 makes them pass.

## Task 3: Shared Ask-User Component

**Files:**
- Create: `frontend/components/bioinfoflow/agent-runtime/ask-user-card.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/pending-decision-cards.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/inline-approval-card.tsx`
- Modify: `frontend/lib/agent-runtime/types.ts`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`

- [ ] **Step 1: Add shared component**

  Create `AskUserDecisionCard` with props:

  ```ts
  type AskUserDecisionCardProps = {
    actionId: string
    questions: AgentAskUserQuestion[]
    onDecision?: AgentDecisionHandler
    inline?: boolean
    id?: string
    testId?: string
  }
  ```

  It should render the existing title, each question, numbered option buttons, a recommended badge when `option.recommended` is true, a custom input row for each question, and submit/skip controls.

- [ ] **Step 2: Preserve answer serialization**

  For single-select questions, submit the selected label or the trimmed custom answer. For multi-select questions, submit selected labels plus the trimmed custom answer when present.

- [ ] **Step 3: Wire pending decision card**

  Import `AskUserDecisionCard` in `pending-decision-cards.tsx`, remove the local `AskUserCard`, and pass `testId="ask-user-card"`.

- [ ] **Step 4: Wire inline decision card**

  Import `AskUserDecisionCard` in `inline-approval-card.tsx`, remove the local `InlineAskUserCard`, pass `inline`, `id={`agent-decision-${actionId}`}`, and `testId="inline-ask-user-card"`.

- [ ] **Step 5: Add i18n strings**

  Add matching English and Chinese strings under `agentRuntime.ask` for custom input, recommended badge, and skip action.

- [ ] **Step 6: Verify focused tests pass**

  Run:

  ```bash
  rtk bun run test -- --run frontend/tests/unit/components/agent-runtime-panel.test.tsx
  rtk bun run test -- --run frontend/tests/unit/components/agent-transcript.test.tsx
  ```

  Expected: both pass.

- [ ] **Step 7: Commit implementation**

  Run:

  ```bash
  rtk git add frontend/components/bioinfoflow/agent-runtime/ask-user-card.tsx frontend/components/bioinfoflow/agent-runtime/pending-decision-cards.tsx frontend/components/bioinfoflow/agent-runtime/inline-approval-card.tsx frontend/lib/agent-runtime/types.ts frontend/messages/en.json frontend/messages/zh-CN.json frontend/tests/unit/components/agent-runtime-panel.test.tsx frontend/tests/unit/components/agent-transcript.test.tsx
  rtk git commit -m "feat: refine askuser decision cards"
  ```

## Task 4: Verification and Visual Review

**Files:**
- Modify only if verification finds a defect.

- [ ] **Step 1: Run frontend lint**

  Run: `rtk bun run lint`

  Expected: pass.

- [ ] **Step 2: Run frontend tests**

  Run: `rtk bun run test`

  Expected: pass.

- [ ] **Step 3: Run i18n check**

  Run: `rtk bun run lint:i18n`

  Expected: pass.

- [ ] **Step 4: Visual review**

  If a live frontend check is practical, set repo-root `.env` to `AUTH_MODE=dev`, start the dev stack, open `/agent`, and verify no overlap at desktop and mobile widths. If the dev stack is too slow or blocked, document the blocker and use component/test evidence.

- [ ] **Step 5: Commit visual or verification fixes**

  If any fixes are made, commit them with `fix: polish askuser ui`.

## Task 5: Parallel Review and PR

**Files:**
- Modify only if review agents find actionable issues.

- [ ] **Step 1: Spawn parallel review agents**

  Dispatch at least two agents:

  - UI/UX reviewer: check accessibility, visual density, copy, and screenshot alignment.
  - Code/test reviewer: check React state, payload semantics, tests, and i18n.

- [ ] **Step 2: Fix actionable findings**

  Make the smallest scoped fixes and rerun relevant commands.

- [ ] **Step 3: Final verification**

  Run `rtk git status --short`, focused tests, and any previously failing checks.

- [ ] **Step 4: Push and open PR**

  Push `codex/askuser-ui-ux` and open a PR with a Conventional Commit style title.
