# Backend Codemap

**Last Updated:** 2026-07-11

## Entrypoints

- `backend/app/main.py`: FastAPI lifecycle, middleware, router mounting, scheduler/resource startup, and recovery.
- `backend/app/api/v1/router.py`: registers 18 API routers beneath `/api/v1`.
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
| `/runs`, `/runs/batch` | run lifecycle, outputs, and batches |
| `/scheduler` | status, slots, and resource information |
| `/agent` | AgentCore sessions, turns, actions, events, artifacts, tools, skills, and targets |
| `/llm` | provider templates, credentials, models, and profiles |
| `/system`, `/terminal` | readiness/system data and terminal WebSockets |

## Service And Persistence Boundaries

Business logic belongs under `backend/app/services/` and uses repository methods
from `backend/app/repositories/` for database access. Run behavior is split into
submission, DAG, lifecycle, archive, dispatch, scheduler, and engine-focused
modules; `run_service.py` remains a delegating facade.

Current persistence domains include workspaces, projects, workflows, project
workflow bindings/pins, runs/configs, batches, notifications, images, audit logs,
container registries, Remote Connections, LLM catalog/profile/credential state,
and AgentCore sessions/turns/messages/events/actions/artifacts/memory.

## Scheduler And Engines

- `backend/app/scheduler/`: persistent database-backed run scheduling, resource checks, concurrency slots, retry policy, timeout enforcement, cleanup, and completion hooks.
- `backend/app/engine/`: shared engine contracts plus Nextflow and MiniWDL implementations.
- `backend/app/runtime/`: runtime-facing support used during workflow execution.

Bioinfoflow schedules whole runs. Engine-specific task retries and scatter
execution remain inside Nextflow or MiniWDL unless a run-level scheduler policy
is explicitly configured.

## AgentCore

`backend/app/services/agent_core/` contains the durable runtime, prompt/context
assembly, models/providers, tool registry and dispatcher, permission handling,
event projection, memory, skills/plugins, execution targets, and subagent
coordination. Tools implement `AgentTool` and `AgentToolSpec` and are registered
from `tools/__init__.py`.

## CLI

The CLI is an HTTP-only client. Command groups are `config`, `project`,
`workflow`, `file`, `system`, `events`, `open`, `run`, `agent`, and `doctor`.
Use `uv run bif --help` for the authoritative command list.
