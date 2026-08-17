# Scope transcript artifacts to their creating turn

## Problem

The right-side Artifacts panel is a project-wide workspace browser, but transcript
artifact cards currently reuse that project-wide list and infer ownership from a
file timestamp after the conversation started. This makes unrelated conversations
claim the same files and re-appends old cards after later turns.

## Invariant

A transcript artifact card belongs to exactly one creating run. Project files with
no evidence tying them to a run remain available in the right-side Artifacts panel
and do not appear in the transcript.

## Implementation

1. Replace conversation-wide timestamp inference with run-scoped evidence:
   authoritative session artifact `runId`, a completed `write`/`edit` activity for
   the exact path, or a run-bounded filesystem update explicitly named by the
   assistant after a successful mutating activity.
2. Assign every supplemental card a non-null creating `runId`.
3. Merge each card immediately after the final assistant message for that run,
   rather than appending all cards at the end of the conversation.
4. Cover cross-conversation leakage, same-conversation later turns, stale files,
   timezone-normalized run windows, and existing artifact references with tests.

## Verification

- Targeted unit and integration tests.
- Frontend lint, i18n lint, dead-code lint, full tests, and production build.
- Visual checks in all three existing conversations, including dark and light
  themes and opening the XLSX artifact in the right panel.
