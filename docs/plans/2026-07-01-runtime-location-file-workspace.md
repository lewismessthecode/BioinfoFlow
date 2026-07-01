# Runtime location and file workspace UX

## Context

The agent composer currently labels the execution target selector as a Host
Skill selector even though it is backed by remote connections. The file drawer
also treats file preview as a narrow side panel next to the file tree, which
clips long code lines and makes opened files feel secondary.

## Goals

- Rename the composer target selector around the user concept of a runtime
  location instead of a host skill.
- Let users choose either the local Bioinfoflow workspace or a configured remote
  server from the same menu.
- Make the files tab behave like a file workspace: file content is the primary
  pane and the file tree is navigation.
- Support a draggable split between preview and tree panes.
- Preserve existing file actions: search, collapse, copy path, attach to
  context, open/download preview actions, and selected file state.

## Design

### Runtime location selector

The existing `ConnectedNodeSelector` remains the control used by the composer,
but its text and menu model changes:

- Empty/default selection becomes `Local workspace`.
- The menu is titled `Runtime location`.
- A local option is always present and clears the remote connection id.
- Remote connection options remain grouped below the local option and continue
  to display connection name, status, and SSH target details.
- The management item becomes `Manage connections`.

This keeps the API boundary stable: parents still store an optional remote
connection id. An empty id means local execution.

### File workspace

The files tab becomes a two-pane split:

- Preview pane on the left with the selected file content, path header, and file
  actions.
- Tree pane on the right with search, collapse, folders, files, copy path, and
  attach actions.
- A draggable separator adjusts the tree width within min/max bounds.
- On narrow containers, the layout stacks so neither pane is squeezed into an
  unusable column.
- Preview content keeps its own scroll area, with code using syntax-oriented
  rendering, line numbers where already supported, and horizontal overflow
  instead of clipping.

The existing `AgentFilePreview` markdown/code rendering stays in place. The
layout changes should make that renderer useful by giving it enough space.

## Validation

- Update English and Chinese locale strings for the runtime location selector.
- Add or update focused component tests for local/remote selector behavior and
  the file workspace split handle.
- Run frontend lint and test commands after implementation.
- Run a browser visual check with `AUTH_MODE=dev` if local services are needed
  to reach protected agent routes.
