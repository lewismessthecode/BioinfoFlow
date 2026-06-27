# Connections UI and Copy Refresh Plan

**Goal:** Make the connection center feel like a calm remote-operations console: clearer hierarchy, fewer competing surfaces, and concise product copy that helps users set up and use SSH connections without exposing backend implementation details.

**Design direction:** Refined minimalism. Keep the existing page structure, but reduce visual noise by using fewer nested cards, quieter dividers, tighter status language, and definition-list style details. The modal should read as two intentional columns: connection access on the left, Agent context on the right.

## Phase 1: Plan and scope

- Confirm affected files and tests.
- Record the design and copy direction in this plan.
- Validate Markdown formatting with a lightweight diff check.
- Commit this plan.

## Phase 2: UI and copy implementation

- Update `frontend/app/(app)/connections/page.tsx` to improve hierarchy:
  - Make the list a quieter index with more compact rows.
  - Turn the selected connection view into a single calm detail surface.
  - Reduce icon repetition and excessive card borders.
  - Keep core actions visible but visually prioritized.
  - Make the add/edit modal more spacious and less implementation-led.
- Update `frontend/messages/en.json` and `frontend/messages/zh-CN.json`:
  - Remove the implementation-heavy security and backend-resolution sentences from the frontend.
  - Use short, direct helper copy for credentials, SSH aliases, and Agent context.
  - Keep English and Chinese keys aligned.
- Update affected tests if copy or accessible labels change.
- Run focused frontend tests and i18n validation.
- Commit the implementation.

## Phase 3: Visual validation and review

- Run lint/tests appropriate for the changed frontend files.
- Launch the app with dev auth if needed and visually inspect `/connections` plus the add/edit SSH dialog.
- Spawn independent review agents for UI polish, copy quality, and code correctness.
- Fix confirmed findings and rerun validation.
- Commit review fixes.

## Phase 4: PR

- Sync with `origin/main` before PR creation.
- Push the worktree branch.
- Open a PR with a concise Conventional Commit title and verification summary.
