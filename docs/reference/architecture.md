# Architecture Reference

This page describes the implementation boundaries for the Bioinfoflow backend,
frontend, workflow engine, scheduler, Agent Harness, and remote connection
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
9. recover unfinished Agent Harness Runs from durable history and checkpoints
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

## Agent Harness

The production Harness lives under:

```text
backend/app/services/agent_harness/
```

`AgentHarness` is the single deep module used by HTTP, SSE, and `bif agent`. Its
public operations are opening a Session, dispatching a command, reading an
authoritative snapshot, and streaming events. Commands are limited to:

- `prompt`: start a Run
- `steer`: add guidance at the next safe point of the active Run
- `follow_up`: queue the next Run
- `respond`: answer a question, confirmation, or recovery interaction
- `cancel`: cancel the active Run

One Session has at most one active Run. The Harness owns context assembly,
provider calls, tool iteration, streaming, compression, retries, cancellation,
and recovery. `backend/app/services/model_runtime/` handles provider wire
protocols but does not control the agent loop.

The model-visible tool surface is fixed to:

- `read`
- `bash`
- `edit`
- `write`
- `ask_user`

`bash` covers ordinary shell programs and authenticated `bif --output json`
operations. Bioinfoflow does not expose one model tool for each platform API.
The executor validates arguments, applies permission and command-risk rules,
serializes Bash and same-path mutations where required, permits independent
reads, and commits results in model call order. A pending `ask_user` interaction
pauses the Run until the user responds.

Permission modes are `read_only`, `ask_dangerous`, and `full_access`.
`read_only` blocks mutable tools and non-read-only Bash. `ask_dangerous` asks for
destructive or critical commands. Commands explicitly marked as requiring
confirmation still ask in every mode. Hard workspace, authorization, and
sandbox violations are always blocked.

Durable state is split by purpose:

- `agent_sessions`: user, workspace, optional project, model, workspace runtime,
  prompt, and permission snapshots
- `agent_runs`: one continuous unit of work, current phase, lease, draft,
  progress, checkpoint, usage, and termination state
- `agent_entries`: the append-only Session history and interaction
  history
- `agent_attachments` and `agent_artifacts`: input files, multimodal content,
  large command output, and downloadable results

Entries are messages, interaction requests, interaction responses, compaction
summaries, or notices. Historical rendering and later context assembly use
entries, not private checkpoints. Compression appends a summary while retaining
the original entries.

Checkpoints fence unfinished state with the Harness version and history
revision. `read` is safe to retry, `edit` and `write` require verification, and
unknown `bash` effects require a user recovery choice. Invalid or incompatible
checkpoints fall back to permanent history.

SSE is snapshot-first. A connection receives the authoritative Session/Run
snapshot and then only `run.updated`, `assistant.delta`, `tool.updated`,
`interaction.requested`, and `entry.committed` changes. Reconnect by fetching a
new authoritative snapshot and then applying only new live changes.

For `bif` calls, the Harness issues a short-lived token scoped to the current
user, workspace, Session, Run, project, and remote connection. Only its hash is
stored. The plaintext is injected only for a proven plain `bif` command, is
revoked when the Run or Session ends, and must not appear in argv, history,
logs, tool output, or artifacts. The API still reloads the user and applies
route-level project and connection scope checks.

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
- `jump`: resolve `jump_connection_id` to one saved direct connection in the
  same workspace, authenticate to it, and run the target connection as a nested
  SSH command

Stored password and private-key methods use an in-process SSH transport so users
do not need backend-visible `~/.ssh/...` paths. Advanced backend SSH methods
continue to execute the system `ssh` binary with argv-based subprocess calls,
`BatchMode=yes`, connect timeouts, bounded stdout/stderr for command-style
operations, and PTY allocation for remote project terminals. The Connections
page supports CRUD, testing, and a streamed WebSocket probe. The project
terminal WebSocket can also bind to a remote project root through the saved
connection profile.

`RemoteConnectionService.resolve_connection_config()` is the routing boundary
for jump mode. It resolves `jump_connection_id`, rejects self-references,
cross-workspace references, and nested jump connections, and attaches the
direct jump configuration to the target configuration. The execution layer
then builds the target command as an inner system-SSH invocation:

```text
Bioinfoflow backend
  -> authenticate outer SSH session to saved jump connection
  -> run: ssh -o BatchMode=yes -- user@target '<command>'
  -> target host
```

This is session-level chained SSH rather than OpenSSH `ProxyJump`. Bioinfoflow
supplies credentials only for the outer saved connection. The inner command is
executed by the jump host's local OpenSSH client and inherits that host's SSH
config, agent, keys, and known-host policy. Only one direct hop is supported.
The resolver and nested-command flow are shared by connection tests, streamed
probes, remote project terminals, and the Harness workspace adapter.

A Session bound to a remote project keeps the same five model tools as a local
Session. `read`, `edit`, and `write` use bounded remote helpers; `bash` runs on
the selected SSH host. Before any of these operations, the adapter verifies a
remote Bubblewrap executable and trusted shell/Python runtime outside writable
project roots. It binds only declared read/write roots and fails closed when the
sandbox cannot be established. The remote account, ACLs, sudo policy, and
scheduler controls remain independent server-side boundaries.

Remote authenticated `bif` use additionally requires a trusted remote `bif`
executable and a non-loopback `BIOINFOFLOW_PUBLIC_API_BASE_URL` reachable from
the SSH host. The scoped Agent token is sent through stdin for the proven plain
`bif` invocation rather than embedded in SSH or shell argv.
