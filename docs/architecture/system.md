# System Architecture

## High-Level Topology

- Frontend: Next.js App Router UI in `frontend/`, with next-intl, Better Auth, REST calls, and SSE subscriptions.
- Backend API: FastAPI app in `backend/app/main.py`, mounted at `/api/v1`.
- Persistence: SQLite via async SQLAlchemy and Alembic migrations.
- Execution stack:
  - `RunService` owns API-facing run lifecycle rules.
  - `RunDispatcher` is the scheduler-backed dispatch seam.
  - `RunScheduler` is the persistent queue/execution orchestrator.
  - `ExecutionBackend` manages local process execution.
  - `EngineAdapter` owns engine-specific command building and event semantics.
- Realtime transport: SSE fan-out from `backend/app/runtime/events.py`.

## Startup Lifecycle

FastAPI lifespan currently does the following:

1. Initialize the database.
2. Ensure the default workspace exists.
3. Reconcile stale Hermes responses.
4. Start `RunScheduler` with `LocalBackend`.
5. Start the resource monitor, recover stale runs, then start `task_runner` and `background_tasks`.
6. On shutdown, stop terminal manager, scheduler, background tasks, task runner, and DB connections.

Important boundary: `task_runner` still exists for non-run background work. Run execution stays on the scheduler path.

## Run Execution Path

Default path for create/retry/resume:

1. API validates request and calls `RunService`.
2. `RunService` verifies project/workflow existence, workflow binding, run-scoped path safety, engine binaries, and path-like inputs.
3. `RunService` persists run metadata under `projects/<project_id>/runs/<run_id>/submission` and `audit`.
4. Status moves `pending -> queued` and an SSE `run.status` event is published.
5. Dispatcher enqueues the run on the persistent scheduler.
6. Scheduler claims queued tasks, optionally waits for resources, and executes via `LocalBackend` + engine adapter.
7. Engine events update logs, DAG state, current task, terminal status, audit logs, batch status, cleanup, and notifications.

## Agent Execution Path

Default chat path is runtime v2:

1. `POST /agent/message` persists the user message and resolves or creates the conversation.
2. `AgentService` creates `SessionState`, `SkillLoader`, optional `TaskManager`, `BackgroundManager`, and the dispatch map.
3. `agent_loop()` runs the async conversation loop with a dynamic system prompt and provider-agnostic LLM client.
4. Each emitted event is persisted as a `messages` row and then republished over SSE.
5. Terminal conversation state emits `agent.done` or `agent.cancelled`.

## Eventing Model

SSE stream endpoint: `GET /api/v1/events/stream`

- Required query: `project_id`
- Optional filters: `conversation_id`, `run_id`, `image_id`
- Transport: EventSource/SSE with heartbeat support from the backend event bus

Backend event families in active use:

- Runs: `run.status`, `run.log`, `run.dag`
- Images: `image.progress`
- Agent: `agent.thinking`, `agent.plan`, `agent.artifact`, `agent.message`, `agent.done`, `agent.cancelled`

Backend approval endpoints and records exist, but approval request/resolution events are not the main UI-driven flow today.

## Reliability And Safety Boundaries

- Path resolution is derived from `BIOINFOFLOW_HOME` and constrained to managed source roots.
- Run preflight checks validate engine binaries, local workflow sources, and path-like inputs before queueing.
- Scheduler recovers stale queued/dispatched work after restart.
- Retry, timeout, cleanup, audit, batch aggregation, and notification delivery are handled as scheduler-owned concerns.
- Output archive generation skips unsafe paths and symlinks.
- Resource monitoring can gate dispatch based on CPU, memory, disk, and GPU capacity.
