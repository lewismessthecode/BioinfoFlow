# Backend Overview

## Stack And Entry Points

- App entry: `backend/app/main.py`
- API prefix: `/api/v1`
- OpenAPI/docs: `/api/v1/openapi.json`, `/api/v1/docs`
- Core stack: FastAPI, async SQLAlchemy, Alembic, native Anthropic/OpenAI/Gemini providers, Docker SDK, MiniWDL

## Router Inventory

The backend currently exposes these router groups:

- `/projects`
- `/projects/{project_id}/workflows`
- `/workflows`
- `/files`
- `/images`
- `/events`
- `/runs`
- `/runs/batch`
- `/notifications`
- `/scheduler`
- `/agent`
- `/stats`
- `/terminal`
- `/system`

## Main Service Boundaries

- `ProjectService`: project CRUD and managed/external root provisioning.
- `WorkflowService`: workflow registration, metadata extraction, source retrieval, and DAG/schema helpers.
- `ProjectWorkflowService`: enable/disable workflows for a project and manage pins.
- `RunService`: request validation, preflight, archive materialization, status normalization, retry/resume/cancel, DAG repair/mock helpers, outputs, cleanup, and audit access.
- `BatchService`: multi-run submission, batch status aggregation, and batch cancellation.
- `NotificationService`: webhook config CRUD and delivery.
- `AuditService`: operational audit logging.
- `AgentService`: conversation/message lifecycle and runtime dispatch.
- `TerminalService`: PTY-based project-scoped terminal sessions with WebSocket I/O, resize, and directory navigation.

## Run Execution Architecture

Current seam:

1. API -> `RunService`
2. `RunService` -> active `RunDispatcher`
3. `RunDispatcher` -> `RunScheduler`
4. `RunScheduler` -> `ExecutionBackend`
5. `ExecutionBackend` -> `EngineAdapter`

Supporting subsystems:

- `backend/app/engine/`: engine abstraction and local backend.
- `backend/app/scheduler/`: queue, resources, retry, timeout, cleanup, and completion hooks.
- `backend/app/runtime/`: SSE bus plus generic background/task runner support.

## Agent Runtime

- Runtime v2 is the live agent runtime.
- It owns the async loop, dynamic system prompt, message persistence, tasks, background commands, skills, and subagents.
- Approval records, trace capture, and conversation policy mode exist, but approval enforcement is not yet the default live-chat behavior.

## Configuration Highlights

Selected backend settings from `app/config.py`:

- App/DB: `APP_NAME`, `DEBUG`, `BIOINFOFLOW_HOME`, `DATABASE_URL`
- Engine binaries: `NEXTFLOW_BIN`, `MINIWDL_BIN`
- Agent runtime: provider/model keys, `AGENT_MAX_ROUNDS`, `AGENT_COMPACT_THRESHOLD`
- Scheduler: `SCHEDULER_MAX_CONCURRENCY`, `SCHEDULER_MAX_QUEUE_DEPTH`, `SCHEDULER_POLL_INTERVAL`, `SCHEDULER_STALE_TIMEOUT_MINUTES`, resource safety margins
- Docker/CORS: `DOCKER_SOCKET`, `CORS_ORIGINS`

Default operational posture:

- Scheduler dispatch is always persistent
- resource checks are enabled by default

## Testing Hotspots

- `backend/tests/test_scheduler/`: queueing, recovery, retry, timeout, cleanup, resources, and hooks
- `backend/tests/test_engine/`: adapters, backend execution, schema extraction
- `backend/tests/test_api/`: lifecycle, scheduler API, batch API, agent API, files/images/projects/workflows
- `backend/tests/test_agent/`: runtime loop, tool dispatch, providers, approvals, and traces
