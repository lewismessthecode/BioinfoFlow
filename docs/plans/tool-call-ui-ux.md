# Tool Call UI/UX Optimization Plan

## Current Problems

- Tool activity occupies too much vertical space in long agent turns, especially when many `bash`, file, and platform API calls are emitted back-to-back.
- Similar calls are split into repeated blocks. Examples from the screenshots include repeated `bash` groups, repeated file-edit groups, repeated `glob`, and repeated workflow reads.
- Some titles are misleading because classification scans broad text. `workflows.list` is displayed as registering a workflow even though it is a read/query action.
- Group titles expose inconsistent mental models: "Use tools", "Read project structure", "Register workflow", and "Create or edit files" can alternate for routine investigation work.
- Each child call repeats a details affordance, which adds visual noise when the useful default view should be a compact summary.
- Low-level tool names such as `images__list`, `images.list`, `workflows.source`, and `bash` are too prominent in the collapsed view.
- File activity summaries repeat counts but do not make the changed-file feedback feel like a single compact operation.

## Requirements

- Keep this change limited to frontend tool-call UI/UX. Do not change tool execution, permission, retry, timeout, or backend protocol behavior.
- Use coarse, user-facing categories:
  - read/query for `list`, `get`, `source`, `glob`, `grep`, `search`, `cat`, and related inspection calls.
  - command for shell, docker, install, build, and other command execution.
  - file changes for create/edit/delete/move file activity.
  - workflow operations only for actual workflow registration, validation, run submission, and run/result operations.
  - workspace preparation for setup/path/workspace initialization actions.
- Prefer stable tool-name classification before scanning arguments or previews. Arguments should not cause `workflows.list` to look like registration.
- Merge same-category tool calls inside one contiguous tool burst into a single collapsed group, even when different categories are interleaved in that burst.
- Keep assistant text, decisions, and errors in their existing narrative order. Do not move tool activity across surrounding assistant text or approvals.
- Default completed groups to collapsed. The group-level arrow is the primary disclosure. Child rows remain lightweight and details open only when needed.
- Keep failed, cancelled, rejected, waiting, running, and building statuses visible in the summary row.
- Update both English and Simplified Chinese UI copy.

## Implementation Notes

- Modify `frontend/lib/agent-runtime/activity-groups.ts` so classification first uses normalized tool names and only then checks previews/arguments for command/file hints.
- Add a new `command` activity kind and map shell-like actions to it instead of generic "other".
- Modify `frontend/lib/agent-runtime/segments.ts` so contiguous runs of activity groups are compacted by kind within the run. This preserves surrounding narrative text while combining same-type calls.
- Update `frontend/components/bioinfoflow/agent-runtime/activity-group.tsx` only if needed for clearer summary copy or testability.
- Update locale files under `frontend/messages/`.
- Add focused tests in `frontend/tests/unit/components/agent-transcript.test.tsx` and reducer/timeline tests where useful.

## Verification

- Run the focused transcript/component tests first.
- Run the focused agent-runtime reducer tests if grouping logic changes.
- Run `rtk bun run lint:i18n` after message changes.
- Run `rtk bun run lint` and the relevant frontend test command before completion.
