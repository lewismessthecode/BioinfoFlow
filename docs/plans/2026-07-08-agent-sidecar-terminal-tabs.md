# Agent Sidecar And Terminal Tabs Iteration Plan

## Goal

Refine the Agent workspace sidecar and terminal dock to match the Codex-style UI direction: quieter editor chrome, icon-only sidecar tabs, cleaner split panes, and terminal tabs that read as a top tab strip instead of a raised card.

## Scope

- Agent file preview/editor chrome:
  - Remove the visible background mismatch in text preview line-number gutters.
  - Make the file preview/tree divider a single hairline with an 8px transparent drag hit area.
  - Use a scoped transient scrollbar class on preview/tree scroll containers.
- Agent sidecar tabs:
  - Extract the sidecar tab strip into a reusable `AgentSidecarTabBar`.
  - Render icon-only tabs with tooltips and aria labels.
  - Use a clearer artifact icon (`FileBox`) for artifacts.
  - On desktop, move Agent-owned action controls into the main workbench top-right lane while the sidecar is open; keep mobile tabs inside the modal overlay.
- Terminal dock:
  - Convert the terminal header to a Codex-like compact tab strip.
  - Remove raised-card tab styling and shadows.
  - Preserve the disabled new-terminal affordance without implying multi-session support.

## Phases

1. File preview polish
   - Add failing tests for gutter background, transient scrollbar hooks, and divider classes.
   - Update `UniversalFileRenderer`, `FilesTab`, `AgentWorkspaceTree`, and scoped scrollbar CSS.
   - Run targeted renderer/files tests and commit.

2. Agent sidecar tab relocation
   - Add failing tests for icon-only sidecar tabs and local top-right action placement when the desktop sidecar opens.
   - Extract `AgentSidecarTabBar`, keep mobile overlay behavior, and move desktop controls into the workbench top lane.
   - Run Agent panel/workbench tests and commit.

3. Terminal tab polish
   - Add failing tests for compact Codex-style terminal tab classes.
   - Update `TerminalDock` header/tab styling.
   - Run terminal tests and commit.

4. Review, visual verification, PR
   - Spawn parallel review agents for layout/accessibility and visual polish.
   - Fix review findings.
   - Run `rtk bun run test`, `rtk bun run lint`, `rtk git diff --check`.
   - Run browser smoke checks with `AUTH_MODE=dev`.
   - Push and open or update the PR.
