# Composer Command Workflow Mentions Implementation Plan

**Goal:** Add a unified composer command layer that supports `/` skills and concrete `@workflow` workflow/version mentions.

**Architecture:** Keep command detection and menu rendering inside the composer, with the workbench supplying data and owning submitted context parts. The composer emits selected workflow refs as structured attachments, while active skills keep the existing active-skill chip behavior.

**Tech Stack:** Next.js, React, TypeScript, Vitest, Testing Library, existing Bioinfoflow API client and workflow types.

---

## Phase 1: Planning Baseline

**Files:**
- Create: `docs/plans/2026-07-16-composer-command-workflow-mentions.md`

**Validation:**
- Run `rtk git diff --check`.

**Commit:**
- `docs: plan composer workflow mentions`

## Phase 2: RED Tests

**Files:**
- Modify: `frontend/tests/unit/components/agent-composer.test.tsx`
- Modify: `frontend/tests/unit/components/agent-workbench.test.tsx`

**Tests to add before implementation:**
- Composer opens one unified command menu for `/` skills and `@workflow`.
- Composer selects a concrete workflow mention and renders a removable workflow chip.
- Workbench loads project workflow groups when `projectId` is present and sends the selected workflow id in `inputParts`.
- Workbench falls back to global workflow groups when no project is present.

**Validation:**
- Run the new focused tests and verify they fail for the expected missing behavior.

**Commit:**
- `test: cover composer workflow mentions`

## Phase 3: Unified Composer Command Layer

**Files:**
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-composer.tsx`
- Modify: `frontend/lib/agent-runtime/types.ts`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`

**Implementation:**
- Replace the skill-only slash token state with a command token state that recognizes `/` and `@`.
- Keep `/` options mapped to skills and preserve active skill chips.
- Add workflow mention options for `@` queries with keyboard, click, hover, Escape, Tab, and Enter behavior matching the existing skill menu.
- Render selected workflow mentions as removable chips above the textarea.
- Update placeholder copy to mention `/` and `@`.

**Validation:**
- Run focused composer tests and `rtk bun run lint:i18n`.

**Commit:**
- `feat: add composer command menu`

## Phase 4: Workflow Data Integration

**Files:**
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx`
- Modify: `frontend/lib/agent-runtime/client.ts`
- Modify: `frontend/lib/agent-runtime/index.ts`
- Modify: `frontend/lib/agent-runtime/types.ts`
- Modify: `frontend/lib/runtime/demo-runtime.ts` if needed for test/demo behavior.

**Implementation:**
- Add client helpers for project workflow groups and global workflow groups.
- Build concrete mention options from pinned/latest workflow plus all versions.
- Submit selected workflow mention chips as `workflow_ref` parts with `workflow_id`, `project_id`, and scope.
- Preserve existing plain-text `@workflow` behavior as a fallback.

**Validation:**
- Run focused workbench tests.

**Commit:**
- `feat: mention concrete workflows`

## Phase 5: Review, Full Verification, PR

**Validation:**
- Run `rtk bun run lint` from `frontend/`.
- Run `rtk bun run test` from `frontend/`.
- Run `rtk bun run lint:i18n` from `frontend/`.
- Run visual review if feasible with `AUTH_MODE=dev`.

**Review:**
- Dispatch parallel review agents for frontend behavior, data-contract correctness, and UI/accessibility.
- Fix Critical and Important findings.

**Publish:**
- Push branch `codex/composer-command-workflow-mentions`.
- Open a draft PR against `main`.
