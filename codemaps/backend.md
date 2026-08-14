# Backend Codemap

**Last Updated:** 2026-08-14

## Entrypoints

- `backend/app/main.py`: FastAPI lifecycle, middleware, router mounting, scheduler/resource startup, and workflow/Agent recovery.
- `backend/app/api/v1/router.py`: registers API routers beneath `/api/v1`.
- `backend/app/cli/main.py`: Typer-based `bif` HTTP client.
- `backend/app/config.py`: environment loading and runtime settings.
- `backend/app/path_layout.py`: platform, project, run, asset, and identity-mount paths.

## API Routers

| Prefix | Area |
| --- | --- |
| `/connections` | SSH profiles, tests, and probes |
| `/container-registries` | workflow-image registries and credentials |
| `/projects` | projects, bindings, and pins |
| `/workflows` | registration, inspection, and workflow metadata |
| `/files`, `/storage` | managed files, uploads, assets, and storage roots |
| `/images` | local image inventory, pulls, and imports |
| `/events`, `/notifications`, `/stats` | event and summary surfaces |
| `/runs`, `/runs/batch` | workflow-run lifecycle, outputs, and batches |
| `/scheduler` | status, slots, and resource information |
| `/agent` | Agent Harness sessions, commands, snapshots, SSE, attachments, artifacts, and context search |
| `/llm` | provider templates, credentials, models, and profiles |
| `/system`, `/terminal` | readiness/system data and terminal WebSockets |

## Service And Persistence Boundaries

Business logic belongs under `backend/app/services/` and uses repository methods
from `backend/app/repositories/` for database access. Workflow-run behavior is
split into submission, DAG, lifecycle, archive, dispatch, scheduler, and
engine-focused modules; `run_service.py` remains a delegating facade.

Current persistence domains include workspaces, projects, workflows, project
workflow bindings/pins, workflow runs/configs, batches, notifications, images,
audit logs, container registries, Remote Connections, LLM catalog/profile/
credential state, and Agent Harness state.

## Scheduler And Engines

- `backend/app/scheduler/`: persistent database-backed workflow scheduling, resource checks, concurrency slots, retry policy, timeout enforcement, cleanup, and completion hooks.
- `backend/app/engine/`: shared engine contracts plus Nextflow and MiniWDL implementations.
- `backend/app/runtime/`: runtime-facing support used during workflow execution.

Bioinfoflow schedules whole workflow runs. Engine-specific task retries and
scatter execution remain inside Nextflow or MiniWDL unless a run-level
scheduler policy is explicitly configured.

## Complete Agent Harness

`backend/app/services/agent_harness/` is the only Agent runtime. Its main
boundaries are:

- `runtime.py` and `harness.py`: process-wide dispatch, run leases, cancellation, and recovery.
- `loop.py`, `context.py`, and `compression.py`: context-model-tool iteration, durable compaction, retry, and completion.
- `workspace_runtime.py` and `sandbox/`: local or remote workspace execution and OS confinement.
- `tools/`: exactly five built-ins — `read`, `bash`, `edit`, `write`, and `ask_user`.
- `events.py` and `contracts.py`: snapshot-first SSE and strict command/history/event contracts.
- `assets.py`: Attachment ingestion/preview and Artifact persistence/download.
- `factory.py`: model resolution, workspace snapshots, scoped `bif` environment, and runtime assembly.

Agent state is represented by `Session`, `Run`, `Entry`, `Attachment`,
`Artifact`, and `AgentToken`, backed by
`backend/app/repositories/agent_harness_repo.py` and
`backend/app/repositories/agent_token_repo.py`.

### Agent HTTP Contract

- `POST/GET /agent/sessions` creates or lists sessions.
- `GET/DELETE /agent/sessions/{session_id}` reads or deletes a session.
- `GET /agent/sessions/{session_id}/snapshot` returns the authoritative projection.
- `POST /agent/sessions/{session_id}/commands` accepts `prompt`, `steer`, `follow_up`, `respond`, and `cancel`.
- `GET /agent/sessions/{session_id}/events` streams `snapshot`, `run.updated`, `assistant.delta`, `tool.updated`, `interaction.requested`, and `entry.committed` SSE events.
- Session attachment, artifact, and context-search endpoints live under the same `/agent` router.

## CLI

The CLI is an HTTP-only client. Command groups include `config`, `project`,
`workflow`, `file`, `system`, `events`, `open`, `run`, `agent`, and `doctor`.
Use `uv run bif --help` for the authoritative command list.
