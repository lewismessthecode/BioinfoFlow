# Architecture Codemap

**Last Updated:** 2026-08-14

## Runtime Shape

```text
Browser / bif CLI
  -> FastAPI /api/v1
  -> focused services
  -> repositories + SQLAlchemy models
  -> workflow scheduler + Nextflow/MiniWDL, or Agent Harness
  -> durable state plus REST/SSE projections
```

The Next.js frontend uses REST for normal requests and WebSockets for local
terminals, remote SSH PTYs, and connection probes. The Agent backend exposes a
snapshot-first SSE stream; the frontend Agent workbench still needs to complete
its migration to that new contract.

## Major Boundaries

| Area | Current entrypoints | Responsibility |
| --- | --- | --- |
| Backend app | `backend/app/main.py`, `backend/app/api/v1/router.py` | lifecycle, middleware, recovery, and HTTP routing |
| Services | `backend/app/services/` | business logic and workflow/run coordination |
| Persistence | `backend/app/repositories/`, `backend/app/models/` | async database access and durable state |
| Scheduler | `backend/app/scheduler/` | persistent workflow-run queue, resources, retries, timeouts, and hooks |
| Engines | `backend/app/engine/` | Nextflow and WDL/MiniWDL execution adapters |
| Agent Harness | `backend/app/services/agent_harness/` | the single context-model-tool loop, recovery, permissions, workspaces, and event projection |
| Frontend | `frontend/app/`, `frontend/components/` | protected application routes, auth routes, and interactive UI |
| CLI | `backend/app/cli/` | HTTP-only `bif` client for a running backend |

## Startup Order

The backend establishes storage paths, initializes and verifies the database,
ensures the default workspace, synchronizes the LLM catalog, starts scheduler
and resource monitoring, recovers workflow runs, recovers unfinished Agent
Harness runs, and then serves requests.

## Storage Contract

`BIOINFOFLOW_HOME` is identity-mounted so the host, backend, workflow runner,
and task containers see the same absolute paths. Managed and external-local
projects use `data/` and `runs/` subtrees. Agent sessions snapshot either a
local workspace root or a remote SSH workspace; workflow dispatch remains a
separate platform concern.

## Agent Harness Flow

```text
prompt / steer / follow-up / response / cancel command
  -> Session command queue
  -> one active Run with lease + checkpoint
  -> context assembly and model invocation
  -> read, bash, edit, write, or ask_user
  -> durable Entry / Attachment / Artifact state
  -> snapshot + SSE events for clients
```

The Harness owns context construction, model calls, tool selection and
execution, permission decisions, user interaction, compaction, retry,
cancellation, and same-version recovery. `AgentToken` is a short-lived,
revocable credential scoped to one user, workspace, session, and active run; it
is injected only when sandboxed `bash` invokes an allowed `bif` command.

Durable history uses `message`, `interaction_request`,
`interaction_response`, `compaction`, and `notice` entries. Live SSE delivery
starts with `snapshot`, followed by `run.updated`, `assistant.delta`,
`tool.updated`, `interaction.requested`, and `entry.committed` events. The
snapshot is authoritative; live events are a projection, not a second ledger.

## External Systems

- Docker daemon and container registries
- Nextflow and MiniWDL
- Better Auth with a shared SQLite database
- LiteLLM and provider SDKs/configuration
- SSH through AsyncSSH or the system `ssh` client
