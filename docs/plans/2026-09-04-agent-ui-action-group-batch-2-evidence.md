# Batch 2 Evidence Audit: Agent UI Action Group

## Status

Complete on `codex/agent-ui-action-group`.

The Batch 2 implementation/evidence commits are
[`c0d8cf5634a9440a87e2dca2cb28a38b61db5175`](https://github.com/lewismessthecode/BioinfoFlow/commit/c0d8cf5634a9440a87e2dca2cb28a38b61db5175),
[`f6f75b264`](https://github.com/lewismessthecode/BioinfoFlow/commit/f6f75b264),
and the release-review P1 fix is
[`4d89880`](https://github.com/lewismessthecode/BioinfoFlow/commit/4d89880).
This worktree was not rebased, and no PR or merge was created.

No Subagents were used.

## Evidence added

The browser fixture now creates a project through the public API, then seeds
three real files through `POST /files/write`:

- `analysis/rnaseq.wdl`
- `results/qc-report.json`
- `README.md`

The browser opens the Files action, expands the seeded directories, selects
`analysis/rnaseq.wdl`, and asserts the real preview before taking screenshots.
The assertions cover the WDL language marker, the existing Scala fallback,
Shiki output, preview content, the JSON file tree entry, and the action group.
The deterministic terminal screenshot fixture remains in place. Its switch is
now a compile-time `NEXT_PUBLIC_BIOINFOFLOW_E2E_TERMINAL_FIXTURE=1` setting
injected only by the existing Playwright web-server command; the browser URL
no longer controls it. A fixture render uses a separate component subtree, so
the live `useTerminalSession` hook and real PTY/WebSocket path are never
created in fixture mode. Production builds do not set this test-only variable,
and default terminal wiring remains unchanged.

Compact viewport coverage now also opens the real terminal bottom Sheet at both
1024x900 and 390x844. It asserts the Sheet's bottom ownership and fixed
72vh composition and captures both baselines. The same browser test persists
the compact panel's open state and active Artifacts tab through reload at both
compact viewports.

Desktop terminal height is resized through the public accessible separator
(`ResizeHandle`, exercised by the test helper `resizeDock`) from 300px to
340px. The test reloads, reopens the terminal, and verifies the 340px height
was restored. The new fixture branch preserves this public resize seam without
changing default live terminal behavior.

## Screenshot evidence

All baselines are Chromium/Darwin-pinned by the existing Playwright
`pathTemplate` and use the repository's `-chromium-darwin.png` convention.

New populated shell screenshots:

- `frontend/tests/e2e/agent-workspace-shell.spec.ts-snapshots/agent-workspace-shell-1440x900-populated-chromium-darwin.png`
- `frontend/tests/e2e/agent-workspace-shell.spec.ts-snapshots/agent-workspace-shell-1024x900-populated-chromium-darwin.png`
- `frontend/tests/e2e/agent-workspace-shell.spec.ts-snapshots/agent-workspace-shell-390x844-populated-chromium-darwin.png`

New mobile terminal Sheet screenshots:

- `frontend/tests/e2e/agent-workspace-shell.spec.ts-snapshots/agent-workspace-shell-1024x900-open-terminal-chromium-darwin.png`
- `frontend/tests/e2e/agent-workspace-shell.spec.ts-snapshots/agent-workspace-shell-390x844-open-terminal-chromium-darwin.png`

The existing 1440x900 terminal screenshot and the 1440x900, 1024x900, and
390x844 open-panel screenshots were refreshed because they now show the
seeded, selected file tree and preview.

## Existing wiring coverage retained

The deterministic terminal double is not treated as the product evidence by
itself. Existing related coverage passed:

- `tests/integration/components/terminal-dock.test.tsx`: 10 tests covering
  TerminalDock session/header/error/theme/fit behavior and fixture isolation
  with a deterministic `MockTerminal`.
- `tests/integration/components/app-layout-terminal.test.tsx`: 8 tests
  covering AppLayout route/project/navbar terminal wiring.
- `tests/integration/pages/agent-page.test.tsx`: 18 tests covering action-group
  state, panel preferences, focus return, and the mobile Sheet.
- `tests/integration/components/live-deck-wiring.test.tsx`: 1 test covering
  real LiveDeck tab/data wiring, including browser and artifact surfaces.
- `tests/unit/components/workspace-code-preview.test.tsx`: WDL-to-Scala
  fallback and Shiki seam.
- `tests/unit/components/agent-browser-panel.test.tsx`: URL normalization and
  sandboxed iframe behavior.
- `tests/unit/lib/terminal/screenshot-fixture.test.ts`: exact test-only
  environment flag semantics.

The current `railRef` remains attached to the desktop LiveDeck rail and the
browser test continues to verify the public panel resize separator. Action
selectors use stable `data-testid`/`data-action-id` state attributes where
possible; visible names remain localized ARIA labels from the active locale.
The existing WDL fallback and browser URL/sandbox fixes were checked and left
unchanged.

## Verification

Passing:

- `rtk bun run test -- tests/unit/components/workspace-code-preview.test.tsx tests/integration/components/live-deck-wiring.test.tsx tests/integration/components/terminal-dock.test.tsx tests/integration/pages/agent-page.test.tsx tests/integration/components/app-layout-terminal.test.tsx`
  — 5 files, 36 tests.
- `rtk bun run test` — 187 files, 1029 tests.
- Chromium browser test without snapshot updates:
  - `PLAYWRIGHT_VIEWPORT_WIDTH=1440 PLAYWRIGHT_VIEWPORT_HEIGHT=900 rtk bunx playwright test tests/e2e/agent-workspace-shell.spec.ts --project=chromium --workers=1`
    — passed.
  - `PLAYWRIGHT_VIEWPORT_WIDTH=1024 PLAYWRIGHT_VIEWPORT_HEIGHT=900 rtk bunx playwright test tests/e2e/agent-workspace-shell.spec.ts --project=chromium --workers=1`
    — passed.
  - `PLAYWRIGHT_VIEWPORT_WIDTH=390 PLAYWRIGHT_VIEWPORT_HEIGHT=844 rtk bunx playwright test tests/e2e/agent-workspace-shell.spec.ts --project=chromium --workers=1`
    — passed.
- `rtk bun run lint`
- `rtk bun run lint:i18n`
- `rtk bun run lint:dead-code`
- `rtk bun run build`
- `rtk git diff --check`

The three viewport baselines were generated with the same Chromium project and
`--update-snapshots` before the non-update verification above.

The final release-review regression also passes: a query-only `/agent?e2eTerminalFixture=1`
run stays in normal mode, while the Playwright test-only environment renders
the deterministic prompt and does not invoke `useTerminalSession`. The three
browser commands above run with the test-only environment through the existing
authenticated E2E startup chain; no public fixture route or authentication
bypass was added.

## Environment limits

The Playwright backend booted successfully and applied Alembic migrations to
head for all three browser runs. No stale-schema error was observed.

The separate full backend command, `rtk uv run pytest`, was not completed:
after reaching 23%, it stalled in Docker credential-helper processes
(`docker-credential-desktop get`). Before the stall,
`tests/test_agent_harness/test_deepseek_sandbox_modes.py` reported four
environment/dependency failures and one skip because sandbox dependencies were
not installed. The run was stopped after no progress; no unrelated backend
code was modified.

The generated Playwright report remains ignored by
`frontend/.gitignore` (`.playwright-report/`), and test results remain ignored
by the root `.gitignore`.
