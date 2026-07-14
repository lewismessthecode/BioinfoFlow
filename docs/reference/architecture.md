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
4. initialize the database and verify Alembic schema state
5. ensure the default workspace and synchronize the LLM catalog
6. start the persistent run scheduler and resource monitor
7. wire run dispatch through `SchedulerDispatcher`
8. recover stale runs
9. recover orphaned AgentCore turns
10. start task runners and remaining background tasks

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
metadata. Authorization-relevant changes also advance a monotonic
`permission_policy_version`. Turns are queued as background tasks; each turn
publishes persisted events that the frontend consumes through SSE.

The runtime flow is:

```text
user input
  -> AgentCore service
  -> async runtime loop
  -> fresh permission-context resolver
  -> durable tool-call batch barrier
  -> tool dispatcher and conditional action claim
  -> persisted actions, events, and artifacts
  -> frontend SSE stream
```

Tools implement the `AgentTool` protocol and define an `AgentToolSpec` with
input and output schemas, risk level, scopes, timeout, audit text, and optional
artifact policy. Tools are registered through `build_default_tool_registry()`.

Toolsets are:

- `default`: read-oriented tools for inspection
- `plan`: planning and clarification tools
- `bio`: read-only bioinformatics and platform inspection tools
- `execution`: all registered tools, still subject to permission policy

Permission modes control approval behavior:

- `ask_each_action`: ask before every non-read side effect
- `guarded_auto`: allow reads and low-risk actions, ask for elevated risk
- `bypass` (shown as **Full access**): allow ordinary non-critical actions
  without a prompt

Automation policy, hard blocks, protected resources, interaction requirements,
and the execution boundary remain independent. Full access does not grant new OS
or SSH privileges. High-confidence catastrophic command matches remain hard
denied, while statically uncertain or indirect forms can require explicit
approval. This classifier is defense in depth rather than confinement: the true
boundary is the active local OS sandbox or the remote account and server policy.
Mandatory user and plan interactions remain independent.

`PermissionContextResolver` forces a fresh session read immediately before tool
exposure and risk evaluation. It resolves a coherent snapshot of policy version,
permission and automation modes, role/toolset, execution target, effective roots,
local sandbox state, or selected SSH identity. Each action records
`evaluated_policy_version` and a bounded `permission_context_snapshot`, including
structured command-risk data when applicable. A policy update that commits
before a later evaluation is therefore visible during the same active turn.

Each assistant message containing tool calls creates an
`agent_tool_call_batches` row. Actions keep the batch id, provider call id, and
stable ordinal. The batch is the continuation barrier: every provider tool call
receives exactly one terminal result before the model can continue. Interaction
tools are exclusive; siblings are explicitly cancelled or deferred rather than
executed behind a user prompt. The database, not an in-process queue, is the
correctness source.

Approval, execution, and continuation transitions use compare-and-set updates:

```text
waiting_decision -> requested or rejected
requested -> running
ready batch -> continuing -> terminal
```

Duplicate decisions and workers therefore cannot intentionally claim the same
side effect or continuation twice. Recovery is batch-first: waiting approvals
stay waiting, requested actions are re-enqueued, all-terminal batches can claim
one continuation, and an action found running after process loss fails the turn
for manual reconciliation instead of being replayed. Legacy actions without
batch or audit metadata remain readable and use the compatibility recovery path.

Session updates accept `pending_strategy`. Omitting it uses `future_only`, which
changes later evaluations only. `approve_pending_tools` atomically updates the
policy and approves eligible waiting tool actions, while excluding user-input
and plan-approval interactions; the response includes affected, excluded, and
already-resolved counts.

Local shell and remote SSH execution use the same structured command assessor.
It records semantic effects, confidence, referenced paths, protected resources,
target identity, and whether a boundary is actually enforced. Local sandboxed
commands can rely on the active OS adapter. Unsandboxed local and SSH commands
cannot: SSH is authorized by the selected remote Unix account and server policy,
and a remote working root is not confinement. Unknown, outside-root, or
symlink-sensitive remote paths require approval when safety cannot be proven.
Protected command destinations are detected lexically, including common link,
archive-extraction, and synchronization forms. This analysis does not resolve
pre-existing filesystem symlinks or inspect archive members, so it is defense in
depth rather than an OS boundary. Opaque archive extraction, process
substitution, executable heredocs, compound shell grammar, and wrapper options
that cannot be parsed confidently require explicit approval even in bypass
mode. Actual confinement comes from the active local sandbox or the remote Unix
account and server controls.

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
current agent session. `remote.read_file` and `remote.list_dir` are preferred
for bounded inspection. `remote.exec` is assessed per command and target rather
than assigned one static risk: safe reads can remain low risk, while writes,
network access, destructive operations, protected resources, uncertain paths,
or a connection mismatch are escalated or blocked. The configured remote root
is a working directory and policy signal, not an OS confinement boundary.
