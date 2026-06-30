# Agent workspace UX refactor

## Goal

Make the Agent workspace behave like Codex: the conversation is primary, the
right drawer is a contextual workspace, the terminal lives in a bottom dock, and
artifacts mean real deliverables.

## Requirements

### Right drawer

- The Agent right drawer is closed by default.
- Opening the drawer shows concrete workspace content, not a large tool menu.
- The first open shows the project file tree.
- Reopening the drawer preserves the last active panel.
- Available right-drawer panels are files, review/artifacts, and browser.
- The drawer header uses compact icon tabs and a close control.

### Artifacts

- Artifacts are user-facing deliverables only: files, HTML, Markdown, PDF,
  reports, sheets, spreadsheets, and similar previewable outputs.
- Command runs, terminal output, tool-call logs, and log summaries are not
  artifacts.
- The review entry remains visible. When no deliverable artifacts exist, it
  shows a minimal empty state: `暂无产物`.
- Counts in the tool entry and drawer must count deliverable artifacts only.
- Backend creation and frontend filtering should share the same semantic
  boundary so legacy command artifacts do not keep leaking into review.

### Browser

- The Agent browser starts blank.
- It must not initialize to the current Bioinfoflow app route.
- The empty state invites the user or Agent to enter a URL.
- Once a URL is opened, the browser can preserve that state while the drawer is
  reopened.

### Terminal

- The terminal is always a bottom dock, not a right-drawer panel.
- The terminal UI should be visually light and Codex-like.
- The visible header should keep only essential context and a close button.
- The default terminal target follows the project:
  - remote project: remote terminal on the bound connection;
  - local project: local project terminal.
- The terminal must clearly label the execution target as local or remote.

### Connection center

- SSH node cards should be longer, simpler, and easier to scan.
- Cards show only the minimum needed for selection: node name, `user@host`, and
  status.
- Authentication method, alias, and last checked time stay in detail/edit
  surfaces rather than the card.
- Selected cards use a light, thin selected state instead of a heavy border.

## Implementation phases

1. Documentation and branch setup.
2. Artifact semantics and tests.
3. Agent drawer and browser behavior.
4. Remote-aware terminal service and dock UI.
5. Connection center card simplification.
6. Integration verification, visual review, review agents, fixes, and PR.

