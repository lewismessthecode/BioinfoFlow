# Agent temporal context

## Goal

Give the agent a reliable current date without changing system instructions on
every model iteration.

## Design

- Keep the stable system prompt free of wall-clock data.
- Accept the browser IANA time zone on every user turn.
- Resolve a `current_date` and time zone once when the turn is created.
- Persist the resolved state in the turn snapshot for auditability.
- Add a structured `<environment_context>` block to the user transcript only
  for the first known state or when the date/time zone changes.
- Store the latest emitted temporal state in server-owned transcript message
  metadata so client-supplied session metadata cannot suppress an update.
- Carry the latest temporal state into compaction summaries so repeated
  compression cannot remove the agent's current date baseline.
- Fall back to `Etc/UTC` when no valid IANA time zone is available.
- Use a clock or shell tool for tasks that require exact wall-clock time.

## Verification

- Backend regression tests for first injection, stable same-day turns, date
  changes, and stable repeated model-context assembly.
- Frontend tests that the browser IANA time zone accompanies every turn.
- Backend test suite and Ruff.
- Frontend lint and tests.
