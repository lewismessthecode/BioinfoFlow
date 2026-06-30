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
- Remote Connections store SSH metadata for diagnostics and agent-assisted
  inspection. SSH is not the workflow dispatch backend.
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
  -> tool dispatch and approvals
  -> persisted actions, events, and artifacts
  -> frontend SSE stream
```

Tools implement the `AgentTool` protocol and describe themselves with
`AgentToolSpec`. The default registry exposes file, shell, search, memory,
skills, platform, web, subagent, and SSH remote tools. Toolsets are `default`,
`plan`, and `execution`; higher-risk actions can pause for approval before they
run.

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
and run the system `ssh` binary with `BatchMode=yes`, timeouts, and bounded
output. The UI can test a connection and stream a short probe command over
WebSocket.

When a user selects a connection in the Agent composer, AgentCore can expose
read-only remote file and directory inspection tools plus an approval-gated
`remote.exec` tool for short diagnostic commands.

## Local-First Path Model

Bioinfoflow requires the host, backend, workflow runner, and task containers to
see the same absolute paths under `BIOINFOFLOW_HOME`. Docker Compose
identity-mounts that root so workflow outputs and cached engine files remain
inspectable from both the UI and the host shell.

See [Storage And Data Layout](concepts/storage.md) for the storage model and
[Docker Quick Start](getting-started/docker.md) for deployment details.
