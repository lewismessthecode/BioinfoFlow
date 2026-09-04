# Batch 2 Evidence: Agent UI Action Group

## Current state

The rebased worktree is `codex/agent-ui-action-group`. The latest code commit
is `0c859b9` (`fix: resolve archived agent deep links`); this document is
committed separately. The current verification pass added no business-code
changes.

The implementation retains the four-action group (Browser, Files, Artifacts,
and DAG), project/session/draft isolation, route-authoritative session panels,
SSR-safe media queries, persistence, focus return, bounded resize behavior,
WDL-to-Scala fallback labeling, and deterministic terminal fixture wiring.
Subagents are not exposed.

## Evidence covered

- Direct `/agent/{sessionId}` routes remain unscoped until the sidebar session
  collection resolves that ID. A resolved project-bound session supplies its
  own project; an unscoped inbox session supplies `null`. Until then,
  AgentWorkbench, LiveDeck, workspace requests, events, and project-scoped
  terminal wiring are not mounted against stale context. Loading and
  missing states are visible rather than leaving an empty resolution shell
  indefinitely. Direct resolution queries include archived sessions, which
  render through the existing read-only AgentWorkbench path without adding
  archived sessions to the sidebar.
- The global terminal action is disabled while a direct route is unresolved or
  unavailable. Once resolved, its identity follows the route session's project;
  unscoped inbox sessions remain disabled and stale project terminal state is
  cleared on scope changes.
- WorkspacePanel root, child-directory, and preview requests carry abort
  signals and request-generation guards. A project change or unmount cancels
  old work. Child failures stay local to the directory, preserve the root and
  sibling tree, and expose a retry action. Replacement requests own spinner
  cleanup; an older request cannot clear their `loadingPaths` state.
- `.playwright-e2e/**` is ignored by the frontend ESLint flat config. Generated
  Playwright reports and results remain ignored and are not committed.

## Browser and screenshot contract

Screenshots use Chromium on Darwin/macOS with the repository's platform-suffixed
snapshot names (`-chromium-darwin.png`). This is the reproducible screenshot
contract; these checks do not claim Linux baseline compatibility.

The existing browser fixture creates a project and seeded workspace files
through the public API. Populated screenshots include the real Files tree and
preview, action group, and deterministic terminal fixture where applicable.
The fixture branch is test-only; production terminal wiring remains unchanged.
No screenshot was updated at runtime during validation, and no
`playwright-report` content was added.

## Verification

Passing in this worktree:

- Focused route/sidebar/terminal suite: 39 tests.
- Full frontend Vitest parallel run: 183 of 187 files passed; these 8 tests
  timed out at five seconds: `workspace-shell-sidebar` project deletion,
  four `connections-page` save/verification tests,
  `create-project-dialog` remote project creation, and two `members-panel`
  member creation/error tests. This is not full-green evidence.
- Each affected file passed independently with one worker and no file
  parallelism: workspace-shell-sidebar (5), connections-page (38),
  create-project-dialog (9), and members-panel (3). Reproduction command:
  `bun run test -- <file> --no-file-parallelism --maxWorkers=1`.
- Complete stable serial Vitest passed: 187 files, 1049 tests, using
  `bun run test -- --no-file-parallelism --maxWorkers=1`. The release
  recommendation is to use this serial command in this constrained local
  environment; the default parallel command remains susceptible to the
  documented five-second resource contention timeouts.
- `rtk bun run lint`
- `rtk bun run lint:i18n`
- `rtk bun run lint:dead-code`
- `rtk bun run build`
- `rtk git diff --check`
- Chromium non-update shell acceptance at 1440x900, 1024x900, and 390x844.

The browser runs used the existing E2E startup chain and completed Alembic
migrations. No snapshot update flag was used for these validation runs.

## Unverified scope and environment limits

The full backend suite (`rtk uv run pytest`) and a full live-agent journey
against external model providers were not run in this audit. They remain
environment-dependent and are not represented as passing evidence here.
Earlier repository evidence recorded backend execution stalling in Docker
credential-helper processes and sandbox dependency failures; no backend or
Terminal code was changed for those limitations.
