# Composer discovery pixel refinement

## Goal

Refine the starter composer suggestions and command discovery hints so the empty
agent surface closely matches the provided Codex and Cursor references.

## Design targets

- Starter suggestions should read as a lightweight Codex-style action list below
  the composer: one-line rows, muted icons, soft dividers, no titles, no
  descriptions, no numeric markers, and no card-like module chrome.
- Command discovery should read as a Cursor-style ambient footer hint: one
  centered sentence, one inline command token, no icon, no hint rail, and no
  banner/card treatment.
- Hint copy should rotate one item at a time with a slow text-state swap:
  old text exits upward with blur/fade, then the new text enters from below.
- Copy should point to real current capabilities: `@workflow`, slash skill
  selection, `Shift+Tab` plan/act mode switching, and input/run preparation.

## Implementation

- Keep the existing empty-composer placement and `agent-center-stage` rail
  compensation.
- Rework `StarterSuggestionList` to render one-line button rows with quiet
  outline icons and text-only prompts.
- Rework `CommandDiscoveryHints` to manage the rotating hint state in React and
  use global text-swap CSS for the three-phase animation.
- Update English and Simplified Chinese locale strings and the workbench unit
  tests.

## Validation

- Run i18n lint, frontend lint, and focused workbench tests.
- Run a browser visual review with `AUTH_MODE=dev` if local services are needed
  to inspect the protected `/agent` route.
