# Inline token mentions and timestamps

## Goal

Update the agent composer and transcript so selected skills and workflow versions behave like inline token entities, preserve visible mention tokens in user messages, and add lightweight conversation timestamps.

## Scope

- Composer: render selected `/skill` and `@workflow` entities inside the input surface instead of external labeled chip rows.
- Transcript: render selected entities inside the user bubble and keep backend-safe `workflow_ref`/`active_skill_names` payloads intact.
- Sidebar and transcript dates: show relative dates in the conversation list and quiet send timestamps in the opened transcript.
- Backend skill loading and installation are intentionally out of scope.

## Implementation phases

1. Plan and branch setup
   - Write this plan.
   - Validate with `rtk git diff --check`.
   - Commit the planning checkpoint.

2. Inline composer and transcript tokens
   - Add red tests for inline composer tokens and preserved transcript mention rendering.
   - Extend `AgentRuntimeWorkflowRefPart` with optional display metadata.
   - Add display metadata when converting selected workflow mentions into `workflow_ref` input parts.
   - Replace external active skill/workflow rows with a shared inline token strip in the composer input surface.
   - Render user bubble token entities from `input_parts` and `active_skill_names`.
   - Run focused frontend tests, then commit.

3. Sidebar and transcript timestamps
   - Add red tests for zh/en sidebar relative labels and transcript message timestamps.
   - Add frontend date formatting helpers with fixed-calendar-day behavior.
   - Render sidebar conversation dates and transcript send timestamps.
   - Run focused frontend tests and i18n checks, then commit.

4. Review, visual check, and PR
   - Spawn review agents for UI/UX and data/test coverage.
   - Fix actionable findings.
   - Run frontend lint/test/build checks that match the changed surface.
   - Do a browser visual pass with `AUTH_MODE=dev` if local services are needed.
   - Rebase on `origin/main`, push, and open a PR.
