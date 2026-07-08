# Agent Single Top Chrome And Terminal Chrome Implementation Plan

**Goal:** Remove the Agent sidecar's extra toolbar by moving desktop sidecar tabs/actions into the app navbar, then tighten the terminal dock header to match Codex's compact terminal chrome.

**Architecture:** `AgentWorkbench` remains the owner of sidecar state and navbar actions. `AgentTabbedPanel` keeps mobile/local chrome by default but supports a chromeless desktop mode for content-only rendering. `TerminalDock` keeps its current session behavior while reducing header height, tab dimensions, button chrome, and body top padding.

**Tech Stack:** Next.js 16, React 19, Tailwind utility classes, Vitest, Testing Library, lucide-react.

## Task 1: Agent Sidecar Single Top Chrome

**Files:**
- `frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx`
- `frontend/components/bioinfoflow/agent-runtime/agent-tabbed-panel.tsx`
- `frontend/tests/unit/components/agent-workbench.test.tsx`
- `frontend/tests/unit/components/agent-runtime-panel.test.tsx`

Steps:
1. Write tests proving desktop sidecar tabs live in navbar actions, `agent-workbench-top-actions` is absent, and `AgentTabbedPanel` can render content without local chrome.
2. Run targeted tests and confirm they fail for the missing behavior.
3. Add a `hideHeader` prop to `AgentTabbedPanel`.
4. Build sidecar tab buttons into `AgentWorkbench` navbar actions when the desktop sidecar is open.
5. Keep navbar actions populated while desktop sidecar is open.
6. Remove the local `agent-workbench-top-actions` row.
7. Pass `hideHeader` to the desktop `AgentTabbedPanel`; keep mobile dialog header unchanged.
8. Run targeted tests and commit with `fix: merge agent sidecar tabs into top chrome`.

## Task 2: Codex-Style Terminal Top Bar

**Files:**
- `frontend/components/bioinfoflow/terminal/terminal-dock.tsx`
- `frontend/tests/integration/components/terminal-dock.test.tsx`

Steps:
1. Update terminal dock tests for a compact header: thinner header, smaller tab capsule, smaller plus/close buttons, and tighter body top padding.
2. Run targeted terminal tests and confirm they fail.
3. Change the header to a thinner Codex-like strip.
4. Shrink the terminal tab and icon buttons while keeping the close button on the far right.
5. Reduce terminal body top padding so the terminal sits directly below the bar.
6. Run targeted terminal tests and commit with `fix: tighten terminal dock chrome`.

## Task 3: Final Verification And PR Update

Steps:
1. Run `rtk bun run lint`, `rtk bun run test`, and `rtk git diff --check`.
2. Use `AUTH_MODE=dev` visual smoke if needed: confirm one top chrome row, sidecar content starts directly below app chrome, tabs live in navbar/action area, resize still works, and terminal header matches the compact Codex reference.
3. Spawn parallel review agents for sidecar/top chrome, terminal chrome, and tests/accessibility.
4. Fix critical or important findings.
5. Rebase on `origin/main`, push `codex/agent-ui-ux-refine`, and update/open the PR.
