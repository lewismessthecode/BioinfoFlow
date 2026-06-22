# Agent Artifacts And Files UI Implementation Plan

## Rewritten Requirements

1. Replace the weak "Showing recent activity" experience in agent chat. After a page refresh, earlier model answers and tool activity should not disappear just because the initial event fetch was capped. If history is intentionally partial, the UI must say so clearly and offer a useful recovery path.
2. Group Docker images by repository/name in card view. The same image with different tags, such as `minibwa:1.0`, `minibwa:1.1`, and `minibwa:1.0-FIXED`, should be one card with version/tag rows or chips inside it, not multiple nearly identical cards.
3. Make the first right-drawer tab an output artifact preview area, not a tool-call log. It should show model-generated or model-referenced output files, especially HTML, PDF, spreadsheet, and Markdown artifacts. Tool invocations and command logs belong in transcript activity, not this tab.
4. Redesign the file browser/tree area to feel closer to the Codex reference: preview/content on the left, searchable file tree on the right, compact rows, recognizable file/folder icons, strong selected state, and toolbar actions like add-to-context and copy path that feel integrated rather than floating awkwardly.

## Phase 0: Planning

- Create this plan in `docs/plans/`.
- Validate with `rtk git diff --check`.
- Commit as `docs: plan agent artifact and file UI updates`.

## Phase 1: Agent History And Artifact Semantics

Files:
- `frontend/hooks/use-agent-runtime.ts`
- `frontend/lib/agent-runtime/client.ts`
- `frontend/components/bioinfoflow/agent-runtime/agent-transcript.tsx`
- `frontend/components/bioinfoflow/agent-runtime/artifact-preview-drawer.tsx`
- `frontend/components/bioinfoflow/agent-runtime/artifact-viewers.tsx`
- `frontend/tests/unit/hooks/use-agent-runtime.test.tsx`
- `frontend/tests/unit/components/agent-runtime-panel.test.tsx`
- `frontend/tests/unit/components/agent-transcript.test.tsx`

Implementation:
- Add tests that prove the initial session restore requests complete event history, while SSE still resumes from the latest loaded event.
- Remove or bypass the initial 500-event cap for normal refresh restoration. Keep the API client capable of capped requests for explicit uses.
- Remove tool-log rendering from the artifact preview drawer. `command` and `log_summary` artifacts should not appear in the preview tab at all.
- Extend file artifact rendering so Markdown uses the existing `MarkdownRenderer`, HTML renders in a sandboxed iframe, spreadsheet-like payloads render as a table, and PDF artifacts render via an embedded viewer when a URL or resource reference is available. Fall back to code/plain text when only content is present.
- Update copy in both locale files if any visible strings change.

Validation:
- `rtk bun run test -- --run tests/unit/hooks/use-agent-runtime.test.tsx tests/unit/components/agent-runtime-panel.test.tsx tests/unit/components/agent-transcript.test.tsx`
- `rtk bun run lint:i18n`
- Commit as `fix: restore agent history and focus artifact previews`.

## Phase 2: Docker Image Grouped Cards

Files:
- `frontend/app/(app)/images/components/image-views.tsx`
- `frontend/app/(app)/images/use-images-page.ts`
- `frontend/tests/unit/components/image-card-grid.test.tsx`
- `frontend/tests/unit/hooks/use-images-page.test.tsx`
- `frontend/messages/en.json`
- `frontend/messages/zh-CN.json`

Implementation:
- Introduce a card-view grouping model based on registry + repository/name.
- Render one card per image group. Show the repository once, then list tags/versions with size and status badges.
- Keep existing actions available per version: details, copy name, copy pull command, delete local, and pull/re-pull.
- Keep table view as the ungrouped detailed list unless tests or UI patterns show table grouping is already expected.
- Ensure search matches group name, description, full name, and tags.

Validation:
- `rtk bun run test -- --run tests/unit/components/image-card-grid.test.tsx tests/unit/hooks/use-images-page.test.tsx`
- `rtk bun run lint:i18n`
- Commit as `feat: group image versions in cards`.

## Phase 3: Codex-Like File Browser UI

Files:
- `frontend/components/bioinfoflow/agent-runtime/files-tab.tsx`
- `frontend/components/bioinfoflow/agent-runtime/agent-workspace-tree.tsx`
- `frontend/components/bioinfoflow/agent-runtime/agent-file-preview.tsx`
- `frontend/tests/unit/components/files-tab.test.tsx`
- `frontend/messages/en.json`
- `frontend/messages/zh-CN.json`

Implementation:
- Keep the split layout but tune it toward the Codex reference: preview left, tree right, flush panels with subtle borders, compact tree rows, strong search field, and selected row treatment.
- Move tree actions into hover/focus-visible controls on each row, with stable sizing so rows do not jump.
- Add file-type icon/color handling for Markdown, shell, Docker/compose, WDL/NF, JSON/table-like files, PDFs, HTML, and unknown files.
- Improve preview toolbar hierarchy so Add to context and Copy path are icon-led buttons with clear labels where space allows.
- Preserve current async tree loading, stale-response handling, filtering, and refresh behavior.

Validation:
- `rtk bun run test -- --run tests/unit/components/files-tab.test.tsx`
- `rtk bun run lint:i18n`
- Visual review with `AUTH_MODE=dev` if local services can be started.
- Commit as `feat: refine agent file browser UI`.

## Phase 4: Full Verification, Review Agents, Fixes, PR

- Run frontend checks: `rtk bun run lint`, `rtk bun run test`, and `rtk bun run lint:i18n`.
- Start the app for visual review if feasible, using repo-root `.env` with `AUTH_MODE=dev` for protected routes.
- Spawn parallel review agents after implementation to review requirements coverage, React/UI quality, and tests.
- Fix critical or important findings and rerun targeted checks.
- Sync remote main before PR: `rtk git fetch origin --prune && rtk git rebase origin/main`.
- Push branch and open a PR with a Conventional Commit style title.
