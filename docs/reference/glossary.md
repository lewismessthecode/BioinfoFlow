# Glossary

This page keeps Bioinfoflow-specific terms grounded in the current codebase.

## Platform Terms

### `BIOINFOFLOW_HOME`

The absolute platform data root used by the backend, workflow runners, task
containers, and the UI. It stores state, auth data, project data, shared input
sources, engine caches, run inputs, and run outputs.

The repo-root `.env` is the default place to configure it. If unset,
`docker-compose.yml` uses the repo-local `data/` directory while
`docker-compose.prod.yml` uses `/srv/bioinfoflow`.

### Identity-Mount Path Contract

Workflow execution assumes `BIOINFOFLOW_HOME_HOST` and `BIOINFOFLOW_HOME`
resolve to the same absolute path. Docker Compose bind-mounts the host
directory to the identical container path, so Nextflow, MiniWDL, backend code,
and task containers can pass absolute paths without translation.

### Run Workspace

The per-run directory under a project's `runs/<run_id>/` tree. It contains
materialized inputs, engine work directories, results, and audit metadata.

### Managed Project

A project whose data and runs live under
`BIOINFOFLOW_HOME/projects/<project_id>/`.

### External Project

A project whose root is an absolute path supplied at project creation or update
time. External roots are useful when a lab already has a project directory on a
shared filesystem. Bioinfoflow still creates the same `data/` and `runs/`
layout inside that root.

### Remote Project

A project associated with a Remote Connection and an absolute POSIX path on the
SSH host. Remote projects support browsing and interactive terminals but do not
dispatch workflow runs over SSH.

## Workflow Terms

### Engine Adapter

The interface implemented by the Nextflow and WDL adapters. It hides
engine-specific command generation, schema extraction, event parsing, and resume
behavior behind the common run scheduler.

### Execution Backend

The strategy used to launch a workflow engine. Current backend code includes
local process execution and containerized MiniWDL execution.

### Form Spec

A workflow input schema generated from Nextflow or WDL source. The backend
stores it with workflow metadata and the frontend uses it to render run forms.

## Scheduler Terms

### Persistent Scheduler

The database-backed queue in `backend/app/scheduler/`. It tracks priority,
slots, resource pressure, retry policy, timeout handling, cleanup, and
completion hooks. It survives backend restarts and recovers stale runs.

### Slot

A unit of scheduler concurrency. Workflows may have a weight, and the scheduler
dispatches only when enough slots and resources are available.

## Agent Terms

### Agent Runtime

The default agent orchestration path under `backend/app/services/agent_core/`.
It stores durable sessions, turns, actions, artifacts, model selection, prompt
snapshots, toolset policy, and context policy.

### Tool Dispatch

The map from model tool requests to Python tool implementations. Tools implement
the `AgentTool` protocol and describe themselves with `AgentToolSpec`, including
input/output schemas, risk level, scopes, timeout, audit text, and optional
artifact policy.

### Toolset

The policy that decides which registered tools are visible to the agent. Current
toolsets are `default`, `plan`, the read-only `bio` policy, and `execution`.

### Approval

The review gate produced by permission policy and risk assessment. Approval
decisions are conditional database transitions, so duplicate submissions do not
intentionally enqueue the same action twice.

### Permission Mode

The policy that decides when AgentCore asks before a tool action. The modes are
`ask_each_action`, `guarded_auto`, and `bypass`. Permission mode is separate from
the local OS sandbox and from SSH account authority.

### Full Access

The UI name for `bypass` permission mode. It auto-approves every action on the
selected target unless the action is hard blocked. Protected-resource writes,
indirect command forms, and sandbox opt-out requests remain risk-classified and
audited but do not prompt. High-confidence catastrophic matches remain hard
denied. Classification is not complete confinement; the true execution boundary
is an enabled local OS sandbox or the remote account and server controls.
Explicit user or plan interactions and workspace policy remain independent.

### Permission Policy Version

A monotonic session counter advanced when authorization-relevant state changes.
AgentCore resolves it freshly before authorizing a tool and records the evaluated
version and bounded context snapshot on each new action.

### Pending Strategy

The effect of a permission update on already waiting tools. `future_only` is the
backward-compatible default. `approve_pending_tools` also approves eligible
waiting tool actions atomically, but excludes user-input and plan interactions.

### Tool-call Batch

The durable continuation barrier for one assistant response containing tool
calls. The model continues only after every call has one terminal result and one
worker conditionally claims the batch continuation.

### Execution Boundary

The authority and confinement that actually apply to a tool process. A local
command may have an enforced OS sandbox; an SSH command instead has the selected
remote Unix account's privileges and server controls. A working directory is not
an execution boundary.

### Remote Connection

A workspace-scoped SSH profile stored by Bioinfoflow. It can use an SSH config
alias, a backend-visible key file path, the backend user's SSH agent, a stored
password, or a stored private key. Remote Connections support backend tests,
streamed probes, interactive project terminals, and selected AgentCore remote
tools. See `docs/guides/remote-connections.md` for the full setup model.

### Agent Skill

Connection- or workflow-specific instructions that guide AgentCore behavior.
For Remote Connections, skill text usually describes remote paths, modules,
service endpoints, and operational rules.

## Abbreviations

| Term | Meaning |
| --- | --- |
| BIF | Bioinfoflow and the `bif` CLI |
| DAG | Directed acyclic graph, used to display workflow structure and progress |
| SSE | Server-Sent Events, used for run, image, and agent streams |
| WDL | Workflow Description Language |
| NF | Nextflow |
| WAL | SQLite write-ahead logging mode |
