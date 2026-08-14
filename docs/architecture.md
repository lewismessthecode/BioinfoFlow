# Architecture

This is the canonical public architecture entrypoint for Bioinfoflow. For the
full implementation map, see [Architecture Reference](reference/architecture.md).

## System Shape

Bioinfoflow is a local-first web app for registering, running, and observing
bioinformatics workflows on infrastructure you control.

- `frontend/` is a Next.js App Router application.
- `backend/` is a FastAPI service with a Typer CLI (`bif`).
- Nextflow and WDL/MiniWDL execution live behind a workflow engine abstraction.
- A persistent scheduler owns queue depth, slots, resource checks, retries,
  timeouts, cleanup, and run completion hooks.
- Agent Harness owns durable sessions, the model-tool loop, streamed Run state,
  history, recovery, attachments, artifacts, and bounded tool execution.
- Remote Connections store SSH metadata for diagnostics, remote project
  terminals, and agent-assisted inspection. SSH is not the workflow dispatch
  backend.
- `BIOINFOFLOW_HOME` is the shared platform root for state, inputs, references,
  caches, and outputs.

## Request And Run Flow

```text
browser or bif CLI
  -> FastAPI routes
  -> service layer
  -> repositories and storage roots
  -> run submission / DAG / lifecycle services
  -> scheduler dispatch
  -> Nextflow or WDL adapter
  -> logs, events, outputs
  -> SSE / REST / WebSocket back to frontend
```

The run service is intentionally thin. New business logic should go into focused
submission, DAG, lifecycle, archive, dispatch, scheduler, or engine modules
instead of growing a catch-all facade.

## Agent Harness

The complete Harness lives under:

```text
backend/app/services/agent_harness/
```

It is the single owner of context assembly, model invocation, tool execution,
user interaction, compression, retries, cancellation, and same-version
recovery. One prompt starts one Run, and one Session has at most one active Run.
The public command surface is deliberately small: `prompt`, `steer`,
`follow_up`, `respond`, and `cancel`.

```text
command -> durable history -> context -> model -> tools -> results
              ^                                      |
              +------ compression and recovery ------+
```

The model sees exactly five tools: `read`, `bash`, `edit`, `write`, and
`ask_user`. Bioinfoflow product operations use the authenticated `bif --output
json` CLI through `bash`; the platform does not mirror every product operation
as a model tool. Tool calls and results are appended to canonical history, and
the Harness continues the model only after the current ordered results are
available.

Sessions use `read_only`, `ask_dangerous`, or `full_access`. These modes control
tool availability and confirmation prompts; they never expand filesystem,
network, SSH, or server-side authorization. Dangerous confirmations, ordinary
questions, and recovery choices all use the same persisted user-interaction
channel.

Canonical history is append-only and independent from private Run checkpoints.
Checkpoint state is only for resuming unfinished work. If recovery cannot trust
it, the Harness falls back to saved history. A `bash` operation that may have
started but lacks a committed result is never silently replayed.

## Remote Connections

Remote Connections live under the `/api/v1/connections` API and the
`frontend/app/(app)/connections/` route.

They are workspace-scoped SSH profiles with six authentication methods:

- password
- pasted private key
- SSH config alias
- backend key file path
- backend SSH agent
- a single saved jump host

Jump connections resolve one direct connection in the same workspace and run
the target command through that host's SSH environment. Nested jump connections
are not supported.

For the simple Termius-style path, Bioinfoflow stores encrypted passwords or
private key contents and uses an in-process SSH client with bounded output. Host
keys are trusted on first use by the backend and must remain stable on later
connections. Advanced backend SSH methods store aliases or file paths instead
and run the system `ssh` binary with `BatchMode=yes`, timeouts, bounded output,
and PTY allocation for project terminals. The UI can test a connection, stream a
short probe command over WebSocket, and open an interactive terminal for remote
projects.

For a remote project, the same five Harness tools operate through its selected
SSH connection and remote root. Remote file helpers and Bash run inside a
verified Bubblewrap sandbox on the remote host; if Bubblewrap or its trusted
runtime paths cannot be verified, execution fails closed. The SSH account,
server ACLs, and scheduler policy remain additional authority boundaries.

Remote `bif` calls require `BIOINFOFLOW_PUBLIC_API_BASE_URL` to be reachable
from the SSH host. The short-lived Agent token is supplied only to a proven
plain `bif` invocation and is not placed in shell argv, history, logs, or
artifacts.

## Local-First Path Model

Bioinfoflow requires the host, backend, workflow runner, and task containers to
see the same absolute paths under `BIOINFOFLOW_HOME`. Docker Compose
identity-mounts that root so workflow outputs and cached engine files remain
inspectable from both the UI and the host shell.

See [Storage And Data Layout](concepts/storage.md) for the storage model and
[Docker Quick Start](getting-started/docker.md) for deployment details.
