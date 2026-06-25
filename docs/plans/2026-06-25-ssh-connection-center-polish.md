# SSH Connection Center Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn PR #70's SSH connection center from a saved-config view into a real remote operation entry point with test, edit, compact SSH-profile UX, skill presets/import, and a visible streamed command probe.

**Architecture:** Keep SSH execution backend-side: the browser talks to Bioinfoflow, and Bioinfoflow uses the existing SSH executor and remote Agent tools. The connection page gets CRUD/test helpers, a compact add/edit dialog, and a single-command streamed probe over the existing `/connections/{id}/exec/ws` endpoint. Full interactive terminal UX remains a follow-up using xterm.js plus backend PTY/session semantics.

**Tech Stack:** Next.js 16, React 19, Radix UI/shadcn components, existing FastAPI SSH endpoints, Vitest, Testing Library.

---

### Task 1: Frontend Connection Client

**Files:**
- Modify: `frontend/lib/demo-connections.ts`
- Test: `frontend/tests/unit/lib/demo-connections.test.ts`

- [ ] Add failing tests for `updateRemoteConnection`, `testRemoteConnection`, and streamed command WebSocket URL/message behavior.
- [ ] Implement typed helpers for PATCH, POST test, and command stream callbacks.
- [ ] Run `rtk bun run test frontend/tests/unit/lib/demo-connections.test.ts`.
- [ ] Commit with `feat: add remote connection client actions`.

### Task 2: Connection Page Behavior

**Files:**
- Modify: `frontend/app/(app)/connections/page.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`
- Test: `frontend/tests/integration/pages/connections-page.test.tsx`

- [ ] Add failing integration tests for visible test action, edit action, key-file validation, and streamed command probe output.
- [ ] Refactor the dialog into add/edit modes using the same validation and payload builder.
- [ ] Add detail actions: test connection, edit connection, and run remote probe.
- [ ] Update list/detail state after test and edit without losing selection.
- [ ] Run `rtk bun run test frontend/tests/integration/pages/connections-page.test.tsx`.
- [ ] Commit with `feat: make ssh connections testable and editable`.

### Task 3: Compact SSH Profile UX

**Files:**
- Modify: `frontend/app/(app)/connections/page.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`
- Test: `frontend/tests/integration/pages/connections-page.test.tsx`

- [ ] Compress the add/edit dialog into one fixed footer card that does not push actions out of view on desktop.
- [ ] Replace auth selection with profile-style options that explain SSH config alias, key file, and ssh-agent.
- [ ] Add Agent Skill preset dropdown and drag/drop text-file import.
- [ ] Keep user-facing text concise and operational.
- [ ] Run `rtk bun run lint:i18n` and the focused connection page tests.
- [ ] Commit with `feat: polish ssh profile dialog skill UX`.

### Task 4: Validation, Review, And PR Update

**Files:**
- All changed frontend files.

- [ ] Run focused frontend tests, lint, and i18n checks.
- [ ] Run relevant backend SSH/Agent tests to confirm real remote execution path remains intact.
- [ ] Perform browser visual review with `AUTH_MODE=dev` if local services are needed.
- [ ] Spawn review agents for spec and code quality; fix Critical/Important findings.
- [ ] Rebase on `origin/main`, push `codex/remote-connections-ssh-agent`, and update PR #70.
