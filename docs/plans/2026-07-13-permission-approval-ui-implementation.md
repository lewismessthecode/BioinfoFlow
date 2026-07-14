# Permission and Approval UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development and superpowers:verification-before-completion task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make permission changes and approval decisions explicit, transactional, accessible, target-aware, and safe against duplicate or stale client responses.

**Architecture:** `useAgentRuntime` owns the permission transaction and exposes a small status object plus a Promise-returning mutation. A focused `PermissionControl` renders the selector and delegates pending-strategy confirmation to the workbench, where pending tool approvals are derived from persisted events. Approval cards share a per-card async submission primitive, while decision views pair waiting events with their persisted risk-assessment target.

**Tech Stack:** Next.js 16, React 19, TypeScript, next-intl, Radix UI, Vitest, Testing Library.

---

### Task 1: Transactional permission hook

**Files:**
- Modify: `frontend/hooks/use-agent-runtime.ts`
- Test: `frontend/tests/unit/hooks/use-agent-runtime.test.tsx`

- [x] Write failing tests proving optimistic session/draft/storage updates, exact rollback, duplicate suppression, ordered overlap, stale-session protection, policy-version protection, retry, and authoritative reconciliation status.
- [x] Run `rtk bun run test tests/unit/hooks/use-agent-runtime.test.tsx` and confirm the new assertions fail for missing transaction state/behavior.
- [x] Add `AgentPermissionUpdateState`, a Promise-returning `setPermissionMode(mode, pendingStrategy?)`, and `retryPermissionModeUpdate`.
- [x] Serialize different overlapping writes, reuse the same Promise for duplicates, and guard commits/rollbacks by transaction sequence, active session id, and policy version.
- [x] Version the draft storage key and preserve the exact previous raw storage value on rollback.
- [x] Re-run the focused hook tests to green.

### Task 2: Accessible permission control and pending strategy

**Files:**
- Create: `frontend/components/bioinfoflow/agent-runtime/permission-control.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-composer.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx`
- Test: `frontend/tests/unit/components/agent-composer.test.tsx`
- Test: `frontend/tests/unit/components/agent-workbench.test.tsx`

- [x] Write failing component tests for `menuitemradio`, checked state, busy/disabled state, live success/error status, retry, and local/remote boundary copy.
- [x] Write failing workbench tests proving only pending tool approvals are eligible, interactions are excluded, widening defaults to `future_only`, the alternate option sends `approve_pending_tools`, tightening is direct, and returned backend counts replace preview counts.
- [x] Run both focused suites and confirm expected failures.
- [x] Extract `PermissionControl`, add a focused confirmation dialog, derive pending counts directly from event state, and pass transaction state without duplicating derived React state.
- [x] Re-run both focused suites to green.

### Task 3: Per-card async decisions and persisted targets

**Files:**
- Modify: `frontend/components/bioinfoflow/agent-runtime/types.ts`
- Modify: `frontend/components/bioinfoflow/agent-runtime/pending-actions.ts`
- Modify: `frontend/components/bioinfoflow/agent-runtime/inline-approval-card.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/pending-decision-cards.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/ask-user-card.tsx`
- Test: `frontend/tests/unit/components/agent-transcript.test.tsx`
- Test: `frontend/tests/unit/components/agent-runtime-cards.test.tsx`

- [x] Write failing tests that require `AgentDecisionHandler` to return a Promise, disable both actions during submission, suppress double-submit, keep failures on the originating card, support retry, and isolate concurrent cards.
- [x] Write a failing test pairing `action.waiting_decision` with the matching persisted `action.risk_assessed.target`, independent of current composer target.
- [x] Run focused card/transcript suites and confirm expected failures.
- [x] Add the smallest shared per-card async decision state and target parsing needed to satisfy the tests.
- [x] Re-run focused suites to green.

### Task 4: Copy, integration, and verification

**Files:**
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`
- Modify tests above as needed for locale parity.

- [x] Add English and Simplified Chinese copy for future-only semantics, current pending approval choices/counts/exclusions, critical safety floor, local sandbox boundary, remote SSH authority, busy/success/error/retry, card target, and decision failure.
- [x] Run focused hook/client/composer/workbench/card/i18n tests.
- [x] Run `rtk bun run lint`, `rtk bun run lint:i18n`, `rtk bun run lint:dead-code`, `rtk bun run test`, and `rtk bun run build` from `frontend/`.
- [ ] With `AUTH_MODE=dev`, visually verify desktop and narrow layouts for local/remote targets with zero, one, and multiple pending approvals when services can be started. Blocked in this environment because the in-app browser runtime reported no available browsers and Docker was unavailable; equivalent component/integration states passed automated tests.
- [x] Run `rtk git diff --check`, review the staged diff, and commit the permission-control UI phases.
