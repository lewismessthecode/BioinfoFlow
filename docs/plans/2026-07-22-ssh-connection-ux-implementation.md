# SSH Connection UX Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically verify saved SSH hosts and make connection-check progress and results immediately visible.

**Architecture:** Keep persisted connection statuses and backend APIs unchanged. Orchestrate save-then-test in the connections page, pass the existing transient test identifier into connection cards, and add a small probe summary state to the edit drawer.

**Tech Stack:** Next.js 16, React 19, TypeScript, next-intl, Vitest, Testing Library, Tailwind CSS.

---

### Task 1: Automatic host verification

**Files:**
- Modify: `frontend/tests/integration/pages/connections-page.test.tsx`
- Modify: `frontend/app/(app)/connections/page.tsx`
- Modify: `frontend/app/(app)/connections/components/connection-list.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`

- [ ] Add a deferred test response to the create-host integration test and assert that `POST /connections/{id}/test` follows `POST /connections`.
- [ ] Assert that the newly created card renders `Connecting...` while the test promise is unresolved.
- [ ] Run `rtk bun run test -- frontend/tests/integration/pages/connections-page.test.tsx` from `frontend/` and confirm the new assertion fails because only the create request is made.
- [ ] Extract a `verifyConnection` helper from the current manual test handler, call it after both create and update succeed, and keep the drawer close independent of test completion.
- [ ] Pass `testingConnectionId` to `ConnectionList` and render a localized transient status instead of the persisted status for that card.
- [ ] Add localized `connecting` and `retestConnection` strings in both locale files.
- [ ] Re-run the targeted integration test and confirm it passes.

### Task 2: Automatic verification failure behavior

**Files:**
- Modify: `frontend/tests/integration/pages/connections-page.test.tsx`
- Modify: `frontend/app/(app)/connections/page.tsx`

- [ ] Add a test where create succeeds and automatic verification rejects.
- [ ] Assert that the saved host remains rendered, the transient state clears, and an error toast is shown.
- [ ] Run the targeted test and confirm it fails for the expected missing auto-verification behavior.
- [ ] Ensure `verifyConnection` catches transport failures without undoing the saved connection and clears the transient identifier in `finally`.
- [ ] Re-run the targeted test and confirm it passes.

### Task 3: Persistent run-check feedback

**Files:**
- Modify: `frontend/tests/integration/pages/connections-page.test.tsx`
- Modify: `frontend/app/(app)/connections/page.tsx`
- Modify: `frontend/app/(app)/connections/components/connection-dialog.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`

- [ ] Extend the WebSocket integration test with deferred frames and assert that `Running connection check...` is visible immediately after the dropdown closes.
- [ ] Assert that an exit frame with code `0` changes the summary to `Connection check completed.` and preserves streamed output.
- [ ] Add a stream-error test that expects an alert containing the failure message.
- [ ] Run the targeted tests and confirm they fail because no persistent summary exists.
- [ ] Add a minimal `ProbeFeedback` state (`idle`, `running`, `success`, `error`) in the page and update it from `handleRunProbe`.
- [ ] Pass the summary state into `ConnectionDialog` and render a compact live region below its header.
- [ ] Treat non-zero exit codes and timeouts as failed checks even when the stream closes normally.
- [ ] Add matching localized running, success, timeout, and non-zero-exit messages.
- [ ] Re-run the targeted integration tests and confirm they pass.

### Task 4: Full verification and delivery

**Files:**
- Inspect all modified files.

- [ ] Run `rtk bun run lint` from `frontend/`.
- [ ] Run `rtk bun run lint:i18n` from `frontend/`.
- [ ] Run `rtk bun run lint:dead-code` from `frontend/`.
- [ ] Run `rtk bun run test` from `frontend/`.
- [ ] Run `rtk bun run build` from `frontend/`.
- [ ] Run `rtk git diff --check` and inspect `rtk git diff --stat` from the repository root.
- [ ] Commit with a Conventional Commit message, push `codex/refine-ssh-connection-ux`, and open a PR with the same canonical title.
