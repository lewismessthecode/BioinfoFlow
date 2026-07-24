# Agent Compaction Continuity Fix

## Problem

Transcript compaction currently replaces older messages with a line-by-line
summary that truncates every message to 240 characters. Long-running turns can
therefore supersede the user's initiating request and the full `todo_write`
state while the UI still renders the durable todo artifact. Repeated compaction
then truncates the previous summary again, amplifying the loss.

## Design

Keep the existing deterministic compaction path, but add a small durable
continuity state to each compaction summary:

- latest real user request;
- latest complete `todo_write` checklist;
- carry both forward from prior compaction metadata when their original
  messages have already been superseded.

Render these anchors as explicit authoritative sections after the historical
message digest. The digest remains bounded and historical; current intent and
work state no longer depend on its per-message truncation.

This follows the shared invariant in Hermes, OpenCode, pi, and Goose: compacted
history is a checkpoint containing current intent, active work, pending tasks,
and the next continuation state, not merely a shortened transcript.

## Verification

- Add a regression test where the initiating request and todo tool result fall
  outside the retained tail.
- Compact again and verify the anchors survive after the original messages are
  already superseded.
- Run the focused compaction tests, backend test suite, and Ruff.
