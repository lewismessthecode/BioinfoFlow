# Agent transcript controls restoration

## Goal

Restore the agent transcript to a lightweight work-log feel while keeping the
existing timeline ordering intact.

## Scope

1. Tool activity groups render as quiet status rows:
   - no outer card border
   - no obvious background block
   - no always-visible trailing chevron
   - expanded details avoid nested bordered containers
2. The files sidecar remains resizable but uses a narrower tree pane.
3. Streaming turns show a live status row below the current assistant output so
   long streaming text does not hide the status at the top.
4. Completed assistant turns show a small action bar with real copy and retry
   behavior.

## Non-goals

- Do not reintroduce the PR 84 transcript redesign.
- Do not change timeline segment ordering in `frontend/lib/agent-runtime`.
- Do not add new backend retry semantics; retry resubmits the original turn
  input through the existing send path.

## Validation

- Focused frontend unit tests for transcript and file pane behavior.
- Frontend lint and i18n lint after locale changes.
- Visual check with `AUTH_MODE=dev` if running the app locally is needed.
