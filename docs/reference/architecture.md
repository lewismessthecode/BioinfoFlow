# Architecture Reference

This page summarizes the current implementation boundaries visible in `backend/`, `frontend/`, and `docker-compose.yml`.

## Backend

The backend is a FastAPI app in `backend/app/main.py`.

Startup lifecycle:

1. configure logging from `backend/app/config.py`
2. enforce Path Contract v3 with `assert_identity_mount()`
3. create platform storage roots with `ensure_platform_layout()`
4. initialize Hermes/agent state
5. initialize the database and verify Alembic schema state
6. ensure the default workspace
7. reconcile stale Hermes responses
8. start the persistent run scheduler and resource monitor
9. wire run dispatch through `SchedulerDispatcher`
10. recover stale runs
11. start task runner and background tasks

Core backend areas:

- `backend/app/api/`: API routers and request dependencies
- `backend/app/services/`: service layer for projects, workflows, runs, storage, agents, and runtime behavior
- `backend/app/repositories/`: database access patterns used by services
- `backend/app/scheduler/`: persistent queue, slots, resource checks, retries, timeouts, cleanup, and completion hooks
- `backend/app/engine/`: workflow engine abstraction for Nextflow and WDL/MiniWDL
- `backend/app/cli/`: Typer-based `bif` CLI
- `backend/app/auth/`: backend auth/session support used by protected API paths

## Frontend

The frontend is a Next.js App Router app under `frontend/`.

Current stack:

- Next.js 16
- React 19
- Tailwind CSS 4
- Radix UI
- React Flow
- next-intl
- Better Auth

Protected application routes live under:

```text
frontend/app/(app)/
```

Auth routes live under:

```text
frontend/app/auth/
frontend/app/api/auth/[...all]/
```

The frontend talks to the backend through REST for normal API calls, SSE for long-running run/agent events, and WebSocket for terminal sessions.

## Configuration

The repo-root `.env` is the default source for Docker and local development.

Backend precedence:

1. shell environment
2. `backend/.env`
3. repo-root `.env`
4. code defaults

Frontend local scripts load the repo-root `.env`; `frontend/.env.local` is the frontend-only override.

`NEXT_PUBLIC_*` values are build-time frontend configuration. Rebuild or restart the frontend after changing them.

## Storage And Execution

`BIOINFOFLOW_HOME` is the single platform root for state, project data, shared inputs, references, engine caches, and run outputs.

Docker Compose identity-mounts that path:

```yaml
- ${BIOINFOFLOW_HOME:-${PWD}/data}:${BIOINFOFLOW_HOME:-${PWD}/data}
```

This is Path Contract v3. Backend, workflow runner, and task containers must see the same absolute paths.

Workflow execution uses a thin run service facade plus dedicated submission, DAG, lifecycle, archive, and dispatch services. New business logic should go into focused services instead of growing the facade.

## Agent Runtime

Agent Runtime lives under:

```text
backend/app/services/agent/runtime/
```

The default flow is:

```text
user input -> agent service -> async runtime loop -> tool dispatch -> persisted/SSE events -> frontend
```

Agent tools use the `BaseTool` abstract class plus `@register_tool`. Tool risk levels are `read`, `act_low`, and `act_high`.
