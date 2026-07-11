# Architecture Codemap

**Last Updated:** 2026-07-11

## Runtime Shape

```text
Browser / bif CLI
  -> FastAPI /api/v1
  -> focused services
  -> repositories + SQLAlchemy models
  -> persistent run scheduler
  -> Nextflow or MiniWDL engine adapter
  -> run events, logs, artifacts, and results
```

The Next.js frontend uses REST for normal requests, SSE for persisted run and
AgentCore events, and WebSocket endpoints for local terminals, remote SSH PTYs,
and connection probes.

## Major Boundaries

| Area | Current entrypoints | Responsibility |
| --- | --- | --- |
| Backend app | `backend/app/main.py`, `backend/app/api/v1/router.py` | lifecycle, middleware, and HTTP routing |
| Services | `backend/app/services/` | business logic and workflow/run coordination |
| Persistence | `backend/app/repositories/`, `backend/app/models/` | async database access and durable state |
| Scheduler | `backend/app/scheduler/` | persistent run queue, resources, retries, timeouts, and hooks |
| Engines | `backend/app/engine/` | Nextflow and WDL/MiniWDL execution adapters |
| AgentCore | `backend/app/services/agent_core/` | durable sessions, turns, events, actions, artifacts, memory, tools, skills, and subagents |
| Frontend | `frontend/app/`, `frontend/components/` | protected application routes, auth routes, and interactive UI |
| CLI | `backend/app/cli/` | HTTP-only `bif` client for a running backend |

## Startup Order

The backend establishes storage paths, initializes and verifies the database,
ensures the default workspace, synchronizes the LLM catalog, starts scheduler
and resource monitoring, recovers stale runs, recovers orphaned AgentCore turns,
and then starts task/background workers.

## Storage Contract

`BIOINFOFLOW_HOME` is identity-mounted so the host, backend, workflow runner,
and task containers see the same absolute paths. Managed and external-local
projects use `data/` and `runs/` subtrees. SSH-backed remote projects are for
remote browsing and terminals, not workflow dispatch.

## AgentCore Flow

```text
user message
  -> durable turn
  -> explicit runtime loop
  -> model response and tool dispatch
  -> permission / interaction / plan gates
  -> persisted events, actions, messages, and artifacts
  -> SSE projection to the frontend workbench
```

Tools are exposed through the registry and policy toolsets (`default`, `plan`,
`bio`, and `execution`). Skills, plugins, subagents, selected SSH connections,
and execution targets extend the runtime without reviving the retired legacy
conversation/Planner/Executor stack.

## External Systems

- Docker daemon and container registries
- Nextflow and MiniWDL
- Better Auth with a shared SQLite database
- LiteLLM plus direct provider SDKs/configuration
- SSH through AsyncSSH or the system `ssh` client
