# Architecture Reference

This page describes the implementation boundaries for the Bioinfoflow backend,
frontend, workflow engine, scheduler, AgentCore runtime, and remote connection
features.

## Backend

The backend is a FastAPI app in `backend/app/main.py`.

Startup lifecycle:

1. configure logging from `backend/app/config.py`
2. enforce the `BIOINFOFLOW_HOME` identity-mount invariant with `assert_identity_mount()`
3. create platform storage roots with `ensure_platform_layout()`
4. initialize AgentCore state
5. initialize the database and verify Alembic schema state
6. ensure the default workspace
7. reconcile stale agent responses
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

The frontend talks to the backend through REST for normal API calls, SSE for
long-running run and agent events, and WebSocket for local terminal sessions,
remote project SSH PTY terminal sessions, and remote connection probes.

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

`BIOINFOFLOW_HOME` is the default platform root for managed state, managed
projects, shared inputs, references, and engine caches. Projects may also use
external roots outside `BIOINFOFLOW_HOME`; those roots keep the same internal
`data/` and `runs/` layout.

Docker Compose identity-mounts that path:

```yaml
- ${BIOINFOFLOW_HOME:-${PWD}/data}:${BIOINFOFLOW_HOME:-${PWD}/data}
```

This identity mount is the path contract for workflow execution. Backend,
workflow runner, and task containers must see the same absolute paths for every
root Bioinfoflow puts into engine inputs: `BIOINFOFLOW_HOME`, shared source
roots, and any external project root used by a run.
For WDL/MiniWDL task containers, Bioinfoflow binds only the platform roots a
task should see: shared data roots read-only, the current project's `data/`
read-only, the current run's `input/` read-only, and the current run's
`results/` read-write. These are sibling mounts rather than a broad project-root
mount, which keeps output writes isolated while still making manifest-referenced
Project Data paths visible inside task containers.

Each run owns only its canonical `runs/<run_id>/` subtree. New-schema output
resolution uses `runs/<run_id>/results`; legacy configured `outdir` fallback is
read-only compatibility and is not used for destructive cleanup.

Workflow execution uses a thin run service facade plus dedicated submission, DAG, lifecycle, archive, and dispatch services. New business logic should go into focused services instead of growing the facade.

Workflow runs execute from the backend scheduler through registered engine
adapters. The current engine registry supports Nextflow and WDL/MiniWDL. SSH
Remote Connections are used for diagnostics and agent-assisted inspection; they
can also back interactive project terminals, but they do not dispatch workflow
runs.

## AgentCore Runtime

AgentCore lives under:

```text
backend/app/services/agent_core/
```

Durable agent sessions record role profile, permission mode, automation mode,
model selection, prompt snapshot, toolset policy, context policy, and session
metadata. Turns are queued as background tasks; each turn publishes persisted
events that the frontend consumes through SSE.

The runtime flow is:

```text
user input
  -> AgentCore service
  -> async runtime loop
  -> tool dispatcher
  -> persisted actions, events, and artifacts
  -> frontend SSE stream
```

Tools implement the `AgentTool` protocol and define an `AgentToolSpec` with
input and output schemas, risk level, scopes, timeout, audit text, and optional
artifact policy. Tools are registered through `build_default_tool_registry()`.

Toolsets are:

- `default`: read-oriented tools for inspection
- `plan`: planning and clarification tools
- `execution`: all registered tools, still subject to permission policy

Tool execution can pause for approvals, interaction requests, or plan approval.
Completed tools persist actions, events, and artifacts.

## Remote Connections

Remote Connections are workspace-scoped SSH profiles stored by the backend and
managed from `frontend/app/(app)/connections/`.

API routes live under:

```text
/api/v1/connections
```

Authentication methods:

- `password`: use an encrypted stored SSH password
- `private_key`: use an encrypted stored OpenSSH private key and optional
  passphrase
- `ssh_config`: pass the saved alias as the exact SSH target
- `key_file`: run SSH with a backend-visible key path
- `agent`: use the backend user's `ssh-agent`

Stored password and private-key methods use an in-process SSH transport so users
do not need backend-visible `~/.ssh/...` paths. Advanced backend SSH methods
continue to execute the system `ssh` binary with argv-based subprocess calls,
`BatchMode=yes`, connect timeouts, bounded stdout/stderr for command-style
operations, and PTY allocation for remote project terminals. The Connections
page supports CRUD, testing, and a streamed WebSocket probe. The project
terminal WebSocket can also bind to a remote project root through the saved
connection profile.

AgentCore remote tools only resolve connections explicitly selected in the
current agent session. `remote.read_file` and `remote.list_dir` are read tools;
`remote.exec` is an elevated tool for short diagnostic commands.
