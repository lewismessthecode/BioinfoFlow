# Cursor-style agent home refinement

## Goal

Refine the Agent home experience after PR 99 so the composer and workspace sidebar more closely match Cursor's compact interaction model while keeping Bioinfoflow's neutral visual system.

## Phase 1: Composer and selector palette

- Remove the internal project/workspace title from the centered composer.
- Make the composer shorter, softer, and more rounded, with tighter bottom controls.
- Restore brighter Cursor-like mode pill colors: green for execution/ask-like states and warm amber for plan-like states.
- Reduce composer selector chip sizes and dropdown proportions for mode, model, runtime location, and permission controls.
- Keep the main welcome heading outside the composer.

## Phase 2: Workspace sidebar tree

- Keep the section label as `工作区`.
- Convert the workspace area into a Cursor-like collapsible tree.
- Add a section-level toggle that hides or shows all projects.
- Keep project-level toggles for child conversations.
- For empty projects, show no empty-state text; keep only the project row and its hover `+` action.
- Move project creation toward compact header/row actions instead of explanatory sidebar copy.

## Validation

- Run focused component tests after each phase.
- Run frontend lint and the full frontend test suite after the integrated changes.
- Launch the app and visually verify the Agent page in the browser before final completion.
