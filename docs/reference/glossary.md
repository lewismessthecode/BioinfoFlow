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

The production vocabulary is intentionally small: Session, Run, History Entry,
Tool Call, Tool Result, User Interaction, Context, Compaction, Checkpoint, and
Workspace Runtime.

### Agent Harness

The single agent runtime under `backend/app/services/agent_harness/`. It owns
context assembly, model invocation, the model-tool loop, user interaction,
compression, retry, cancellation, and recovery. It is not selected through an
engine registry.

### Session

A durable conversation container bound to a user and workspace, optionally a
project. It stores model, workspace, permission, and stable prompt snapshots.

### Run

One continuous unit of work started by a prompt. A Run may be queued, running,
waiting for the user, completed, failed, or cancelled. A Session has at most one
active Run.

### History Entry

One append-only canonical history record. Entry types are message,
interaction request, interaction response, compaction, and notice. Old
conversations render from entries without requiring the original Harness
process or checkpoint.

### Tool Call And Tool Result

A model request for one of `read`, `bash`, `edit`, `write`, or `ask_user`, and
the ordered result returned to the model. Both are stored as canonical history
content.

### User Interaction

The single persisted request/response channel for questions, dangerous-command
confirmation, and recovery choices.

### Permission Mode

The Session policy controlling tool availability and confirmations. Modes are
`read_only`, `ask_dangerous`, and `full_access`. Permission mode does not grant
filesystem, network, SSH, or Bioinfoflow API authority.

### Full Access

The most permissive Session mode. It reduces confirmation prompts but does not
override explicit-confirmation rules, hard workspace boundaries, OS sandboxing,
remote account authority, or server-side API authorization.

### Context And Compaction

Context is the provider request derived from the stable prompt snapshot,
attachments, compaction summaries, and recent permanent history. Compaction
appends a continuity summary; it does not delete the original entries.

### Checkpoint

Private unfinished-Run state used only for same-version recovery. It is not the
conversation rendering source. Invalid or incompatible checkpoints fall back to
permanent history, and unknown Bash effects are never silently replayed.

### Workspace Runtime

The local or remote SSH adapter behind the same five tools. It enforces root
boundaries, command sandboxing, cancellation, output limits, and secret
redaction. Remote execution additionally requires a verified Bubblewrap sandbox
on the SSH host.

### Execution Boundary

The authority and confinement that actually apply to a tool process. Local Bash
uses Bubblewrap on Linux or Seatbelt on macOS. Remote tools use a verified
Bubblewrap sandbox inside the selected SSH account. Server ACLs, sudo rules,
scheduler policy, and Bioinfoflow API authorization remain independent layers.

### Remote Connection

A workspace-scoped SSH profile stored by Bioinfoflow. It can use an SSH config
alias, a backend-visible key file path, the backend user's SSH agent, a stored
password, or a stored private key. Remote Connections support backend tests,
streamed probes, interactive project terminals, and remote Harness workspaces.
See `docs/guides/remote-connections.md` for the full setup model.

### Agent Skill

A reusable instruction package whose `SKILL.md` can be read by the Harness with
the normal `read` tool. Session prompt snapshots list available skill names,
descriptions, and paths without adding a dedicated skill-loading model tool.

## Abbreviations

| Term | Meaning |
| --- | --- |
| BIF | Bioinfoflow and the `bif` CLI |
| DAG | Directed acyclic graph, used to display workflow structure and progress |
| SSE | Server-Sent Events, used for run, image, and agent streams |
| WDL | Workflow Description Language |
| NF | Nextflow |
| WAL | SQLite write-ahead logging mode |
