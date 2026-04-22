# Bioinfoflow Documentation

Source-of-truth documentation for the Bioinfoflow platform, written against the current codebase.

## Scope

- Source-of-truth docs for product behavior, backend/frontend architecture, API contracts, operations, and contribution workflow.
- Written against the current code in `backend/` and `frontend/`.
- Historical rewrites and completed implementation plans are kept under `docs/archive/`.

## Active Docs Map

- `product-overview.md` ([中文版](product-overview-zh.md)): product overview — what it does, who it's for, current state, and roadmap.
- `architecture/system.md`: runtime architecture, startup lifecycle, execution paths, SSE model, and reliability boundaries.
- `architecture/data-model.md`: current tables, relationships, enums, and migrations.
- `backend/overview.md`: backend modules, service boundaries, scheduler/engine execution path, and configuration.
- `backend/agent-runtime.md`: runtime v2 agent loop, event persistence, tool dispatch, skills/tasks, and background work.
- `frontend/overview.md`: route map, app shell, client data flow, SSE wiring, auth, and i18n.
- `api/reference.md`: `/api/v1` endpoint catalog and contract notes.
- `../RUNBOOK.md`: canonical setup and troubleshooting guide for users.
- `operations/runbook.md`: operations supplement for deployment/runtime context.
- `development/contributing.md`: commands, testing gates, conventions, and doc maintenance rules.

## Recommended Reading Order

1. `product-overview.md` for product context
2. `architecture/system.md`
3. `architecture/data-model.md`
4. `backend/overview.md`
5. `frontend/overview.md`
6. `api/reference.md`
7. `backend/agent-runtime.md` when working on chat/agent behavior

## Archive

- `archive/2026-03-07-pre-rewrite/`: docs snapshot from before the 2026-03-07 rewrite.
- `archive/2026-03-18-implementation-plans/`: completed implementation plans archived during this refresh.

## Maintenance Rules

1. Update `api/reference.md` in the same change when endpoint shape, status codes, or router inventory changes.
2. Update `architecture/system.md` when run dispatch, scheduler behavior, or SSE event names change.
3. Update `architecture/data-model.md` when models, enums, or Alembic migrations change.
4. Update `frontend/overview.md` when route structure, app-shell behavior, or SSE consumption changes.
5. Keep `docs/plans/` for active work only; archive completed plans under `docs/archive/<date>-<label>/`.
