# Codebase Cleanup Plan

## Goal

Simplify BioinfoFlow module by module without changing observable behavior.
Remove code only when call sites, tests, configuration, and relevant history show
that it is dead or superseded.

## Guardrails

- Preserve inputs, outputs, side effects, ordering, and error behavior.
- Do not modify tests merely to accommodate a behavior change.
- Keep backend database access behind repositories and preserve CLI/API contracts.
- Keep frontend copy localized in both locale files.
- Avoid broad formatting churn and unrelated renames.
- Validate and commit each phase independently.

## Phases

1. Cross-repository tooling, configuration, scripts, demos, and confirmed dead
   compatibility paths outside the application modules.
2. Frontend routes, components, hooks, utilities, tests, and locale usage.
3. Backend services, API, scheduler, runtime, engine, repositories, and CLI.
4. Independent review passes for behavior regressions, incomplete dead-code
   removal, and unnecessary complexity introduced by the cleanup.
5. Full verification, rebase onto `origin/main`, push, and open a PR.

## Verification

- Backend: `rtk uv run pytest` and `rtk uv run ruff check .` from `backend/`.
- Frontend: `rtk bun run lint`, `rtk bun run test`, and
  `rtk bun run lint:dead-code` from `frontend/`; run `rtk bun run lint:i18n`
  when locale files change.
- Repository/docs: `rtk git diff --check` plus targeted checks for changed
  tooling.
- Final: repeat the complete backend and frontend verification matrix and inspect
  the final diff and commit series.
