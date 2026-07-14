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
- AgentCore provides durable agent sessions, streamed turns, tool actions,
  artifacts, approvals, skills, subagents, and bounded tool execution.
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

## Agent Runtime

Agent Runtime lives in:

```text
backend/app/services/agent_core/
```

AgentCore stores sessions, turns, actions, artifacts, model selection, prompt
snapshots, toolset policy, and context policy in the backend database. Turns run
as asynchronous tasks and publish persisted events that the frontend reads over
SSE.

The default flow is:

```text
user input
  -> AgentCore service
  -> async runtime loop
  -> fresh, versioned permission context
  -> durable tool-call batch and approval barrier
  -> tool dispatch
  -> persisted actions, events, and artifacts
  -> frontend SSE stream
```

Tools implement the `AgentTool` protocol and describe themselves with
`AgentToolSpec`. The default registry exposes file, shell, search, memory,
skills, platform, web, subagent, and SSH remote tools. Toolsets include
`default`, `plan`, the read-only `bio` policy, and `execution`; higher-risk
actions can pause for approval before they run.

Permission mode is an approval policy, not an operating-system capability.
AgentCore resolves the current session policy and execution target immediately
before authorizing each tool call. Authorization-relevant changes increment a
monotonic policy version, and actions record the version and bounded context
used for their decision. A model response containing several tool calls is
stored as one durable batch: every call must have a terminal result before one
database-claimed continuation may invoke the model again.

"Full access" is the UI name for bypassing ordinary risk approvals on the
selected target. High-confidence catastrophic matches remain hard denied;
protected-resource writes, indirect command forms, and sandbox opt-out can still
require explicit approval. The classifier is not a complete shell security
boundary: actual confinement comes from an enabled local OS sandbox or, for SSH,
the remote account and server controls. Explicit user/plan interactions and
workspace or administrator policy remain independent.

## Remote Connections

Remote Connections live under the `/api/v1/connections` API and the
`frontend/app/(app)/connections/` route.

They are workspace-scoped SSH profiles with five authentication methods:

- password
- pasted private key
- SSH config alias
- backend key file path
- backend SSH agent

For the simple Termius-style path, Bioinfoflow stores encrypted passwords or
private key contents and uses an in-process SSH client with bounded output. Host
keys are trusted on first use by the backend and must remain stable on later
connections. Advanced backend SSH methods store aliases or file paths instead
and run the system `ssh` binary with `BatchMode=yes`, timeouts, bounded output,
and PTY allocation for project terminals. The UI can test a connection, stream a
short probe command over WebSocket, and open an interactive terminal for remote
projects.

When a user selects a connection in the Agent composer, AgentCore can expose
read-only remote file and directory inspection tools plus `remote.exec` for
short diagnostic commands. Local shell and remote SSH commands share one
command-risk vocabulary, but risk is adjusted for the actual target. A safe,
bounded remote read may be low risk; writes, network activity, destructive
commands, uncertain paths, and protected resources receive stronger handling.
The remote working root is a navigation default and risk signal, not a security
boundary: SSH commands have the authority of the selected remote account and
the remote server's controls.

## Local-First Path Model

Bioinfoflow requires the host, backend, workflow runner, and task containers to
see the same absolute paths under `BIOINFOFLOW_HOME`. Docker Compose
identity-mounts that root so workflow outputs and cached engine files remain
inspectable from both the UI and the host shell.

See [Storage And Data Layout](concepts/storage.md) for the storage model and
[Docker Quick Start](getting-started/docker.md) for deployment details.
