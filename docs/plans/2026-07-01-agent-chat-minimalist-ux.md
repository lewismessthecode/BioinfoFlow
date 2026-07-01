# Agent Chat Minimalist UX Plan

## Goal

Redesign the Bioinfoflow agent transcript into a hybrid chat/work-log UI:
assistant text stays primary, active work remains visible while running, completed
tool groups collapse by default, and repeated source chips are suppressed unless
they are newly introduced or directly cited.

## Design Reading

This is a redesign-preserve task for a dense product workspace, not a landing
page. The target language is quiet, document-like, and technical: warm neutral
surfaces, low shadow, crisp 8-12px radii, subtle motion, and restrained status
color.

## Phases

1. Planning baseline
   - Write this plan.
   - Verify Markdown diff with `rtk git diff --check`.
   - Commit the plan.

2. Runtime source and segment behavior
   - Update transcript source display so previously introduced URLs do not
     repeat below later text blocks.
   - Keep citation rendering intact.
   - Add or update unit tests around repeated source footer behavior.
   - Verify with focused Vitest and i18n checks if copy changes.
   - Commit data behavior.

3. Transcript and activity UI redesign
   - Move active thinking/status into the streaming response flow.
   - Make all completed activity groups collapsed by default.
   - Restyle transcript, activity groups, tool rows, and source chips with the
     minimalist visual direction.
   - Add bilingual copy for active status labels.
   - Verify with focused tests, lint, i18n, and visual review when practical.
   - Commit UI behavior.

4. Review, fixes, and PR
   - Spawn review agents in parallel.
   - Fix actionable findings.
   - Run final frontend verification.
   - Push branch and open a PR.

## Primary Files

- `frontend/lib/agent-runtime/segments.ts`
- `frontend/lib/agent-runtime/sources.ts`
- `frontend/lib/agent-runtime/types.ts`
- `frontend/components/bioinfoflow/agent-runtime/agent-transcript.tsx`
- `frontend/components/bioinfoflow/agent-runtime/activity-group.tsx`
- `frontend/components/bioinfoflow/agent-runtime/tool-activity-row.tsx`
- `frontend/components/bioinfoflow/agent-runtime/agent-sources.tsx`
- `frontend/messages/en.json`
- `frontend/messages/zh-CN.json`
- `frontend/tests/unit/components/agent-transcript.test.tsx`
- `frontend/tests/unit/agent-runtime/sources.test.ts`

## Non-goals

- No backend event schema migration.
- No new model/tool protocol.
- No large animation framework unless the existing stack cannot support the
  desired subtle transitions.
- No marketing-page visual language.
