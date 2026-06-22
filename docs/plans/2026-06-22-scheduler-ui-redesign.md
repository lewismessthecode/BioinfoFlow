# Scheduler UI Redesign Plan

## Goal

Refactor the scheduler page into a calmer operations console that matches the dashboard design language: focused state summary, clearer card regions, restrained status color, and compact resource details.

## Design direction

- Use the dashboard shell rhythm: `max-w-6xl`, stacked `CardRoot` sections, small headers, muted supporting copy, and restrained badges.
- Make the first scan answer whether the scheduler can accept and dispatch work.
- Split the current monolithic resources panel into decision-oriented cards: dispatch readiness, capacity status, active runs, and resource trends.
- Keep advanced diagnostics available but out of the primary scan path.

## Phases

1. Plan and baseline validation
   - Record the redesign scope and implementation phases.
   - Validate the plan file with a lightweight diff check.

2. Scheduler page implementation
   - Rework `frontend/app/(app)/scheduler/page.tsx` around a dashboard-like state strip and compact queue metrics.
   - Rework `frontend/app/(app)/scheduler/components/resource-monitor.tsx` into clearer card regions while preserving existing stream, chart, drawer, and shortcut behavior.
   - Adjust supporting scheduler components only where needed for hierarchy and empty states.
   - Keep locale keys synchronized in English and Simplified Chinese.

3. Verification and visual review
   - Run targeted frontend tests, lint, and i18n checks.
   - Start the app with `AUTH_MODE=dev` if a browser review is needed, inspect `/scheduler`, and fix visual regressions.

4. Review and PR
   - Spawn parallel review agents for correctness and UI quality.
   - Fix confirmed findings, rerun relevant checks, commit the review phase if changes were needed, then open a PR.
