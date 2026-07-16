# Agent Artifact Deliverables UX Plan

## Goal

Refine the agent workspace so conversation-generated files appear as first-class
deliverables in chat cards and in the right-side preview center, while excluding
run outputs, commands, logs, todos, and generic tool records.

## Scope

- Show only conversation artifacts that are actual generated files.
- Add compact file cards below the relevant assistant turn.
- Upgrade the artifact sidecar into a deliverables center with list and preview
  states.
- Improve inline code and fenced code contrast in assistant Markdown.
- Make the right sidecar width drag smoother.
- Do not reintroduce run outputs, command output, tool logs, or scheduler/run
  artifacts into this UI.

## Current Findings

- `frontend/lib/agent-runtime/artifacts.ts` filters out commands, logs, and todos,
  but still treats any artifact with `file_path` as deliverable. That is too broad
  for a file-only conversation deliverables surface.
- `frontend/components/bioinfoflow/agent-runtime/agent-transcript.tsx` renders
  assistant text and actions, but it does not receive or render artifacts per turn.
- `frontend/components/bioinfoflow/agent-runtime/artifact-preview-drawer.tsx`
  already has a list and preview state, but the list reads like low-detail
  artifact rows instead of file delivery cards.
- `frontend/components/bioinfoflow/markdown-renderer.tsx` uses pale secondary
  surfaces for inline code and code blocks, so long paths and code samples blend
  into the page.
- `frontend/components/ui/resize-handle.tsx` uses mouse events and incremental
  deltas. `frontend/components/bioinfoflow/agent-runtime/files-tab.tsx` has a
  smoother pointer-event pattern based on absolute pointer position.

## Phase 1: File-Only Artifact Semantics

Files:
- Modify `frontend/lib/agent-runtime/artifacts.ts`
- Modify `frontend/lib/agent-runtime/artifacts.test.ts`

Implementation:
- Introduce a stricter conversation deliverable predicate that accepts only file
  artifact types and requires a file path or renderable file resource.
- Keep accepted types narrow: `file`, `html`, `image`, `pdf`, `report`,
  `markdown`, `sheet`, and `spreadsheet`.
- Reject `command`, `log_summary`, `todo_list`, `run`, `workflow`, and unknown
  file-path records unless they explicitly become a supported file type later.

Tests first:
- Add a failing test proving command/log/todo/run/workflow artifacts with
  `file_path` are excluded.
- Add a failing test proving supported file artifacts are retained and sorted in
  input order.

Validation:
- `rtk bun run test frontend/lib/agent-runtime/artifacts.test.ts`
- Commit: `fix: restrict agent deliverables to generated files`

## Phase 2: Chat Cards and Deliverables Center

Files:
- Modify `frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx`
- Modify `frontend/components/bioinfoflow/agent-runtime/agent-transcript.tsx`
- Create or modify a focused card component under
  `frontend/components/bioinfoflow/agent-runtime/`
- Modify `frontend/components/bioinfoflow/agent-runtime/artifact-preview-drawer.tsx`
- Modify `frontend/components/bioinfoflow/agent-runtime/artifact-viewers.tsx`
- Modify `frontend/messages/en.json`
- Modify `frontend/messages/zh-CN.json`
- Add or update component tests under `frontend/tests/unit/components/`

Implementation:
- Pass file-only deliverables from `AgentWorkbench` into `AgentTranscript`.
- Render compact generated-file cards below the assistant response for artifacts
  whose `turn_id` matches the entry.
- Card actions: preview/open in right sidecar, download when possible, copy path.
- Opening a card should open the sidecar, switch to the deliverables tab, and
  select the file.
- The sidecar default state should be “all deliverables”; selecting one file
  should show a preview with a clear back affordance.
- Keep labels file-focused: generated files, all files, preview, download, copy
  path. Avoid “run output”, “tool log”, and command-oriented wording.

Tests first:
- Add a failing transcript test that renders generated file cards for matching
  turn artifacts and excludes command/run artifacts.
- Add a failing sidecar test that selecting a card opens the artifact preview.
- Add i18n coverage by updating both locale files.

Validation:
- `rtk bun run test frontend/tests/unit/components/agent-transcript.test.tsx frontend/tests/unit/components/agent-workbench.test.tsx`
- `rtk bun run lint:i18n`
- Commit: `feat: add generated file deliverables UI`

## Phase 3: Code Contrast and Smooth Resize

Files:
- Modify `frontend/components/bioinfoflow/markdown-renderer.tsx`
- Modify `frontend/components/ui/resize-handle.tsx`
- Modify `frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx`
- Update relevant tests under `frontend/tests/unit/components/`

Implementation:
- Treat weak code contrast as a UI bug.
- Use stronger bordered/tinted surfaces for inline code and fenced code blocks.
- Preserve syntax highlighting and copy button behavior.
- Extend `ResizeHandle` with pointer events, pointer capture where available,
  text-selection suppression during drag, and absolute coordinate reporting.
- Update the agent sidecar resize to compute width from the panel boundary rather
  than relying on incremental mouse deltas.
- Preserve keyboard resize behavior and accessibility attributes.

Tests first:
- Add a failing Markdown renderer test asserting the stronger code classes.
- Add or update resize tests for keyboard deltas and pointer drag behavior.

Validation:
- `rtk bun run test frontend/tests/unit/components/markdown-renderer.test.tsx frontend/tests/unit/components/agent-workbench.test.tsx`
- Commit: `fix: improve code contrast and sidecar resizing`

## Final Validation and Review

Commands:
- `rtk bun run lint`
- `rtk bun run test`
- `rtk bun run lint:i18n`

Visual review:
- If the app needs a protected route visual pass, set `AUTH_MODE=dev` in this
  worktree's repo-root `.env`, restart services, and inspect `/agent`.

Parallel review:
- Spawn one reviewer for file-only artifact scope.
- Spawn one reviewer for UI/UX and code contrast.
- Spawn one reviewer for resize/accessibility.
- Fix validated findings, rerun affected tests, and commit fixes.

PR:
- Sync `origin/main` before opening the PR.
- Push `codex/artifact-deliverables-ux`.
- Open a PR titled `feat: refine generated file deliverables UX`.
