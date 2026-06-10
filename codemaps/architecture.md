# Architecture Codemap
<!-- Generated: 2026-05-16 | Files scanned: current backend/frontend snapshot | Token estimate: ~900 -->
**Last Updated:** 2026-05-16
**Entry Points:** `backend/app/main.py`, `backend/app/api/v1/router.py`, `backend/app/runtime/events.py`, `backend/app/cli/main.py`, `frontend/app/layout.tsx`, `frontend/app/(app)/layout.tsx`

## Architecture
```
Browser (Next.js UI + next-intl i18n)
   │  REST + SSE + WebSocket (terminal)
   ▼
FastAPI /api/v1  ───────────────►  SQLite (aiosqlite)
   │                               ▲
   │                               │
   ├─ Services (projects, project-workflows, runs, workflows, files,
   │            storage, images, demos, stats, batch, notifications,
   │            audit, terminal, llm catalog, workspaces,
   │            dag-parser, trace-parser, validators)
   │
   ├─ RunService facade (delegates to RunSubmissionService,
   │  RunDagService, RunLifecycleService, RunArchiveService,
   │  RunDispatcher) — identity-mounted run paths
   │
   ├─ Agent Runtime (explicit async loop — default)
   │    ├─ Tool dispatch (BaseTool + runtime + legacy tools)
   │    ├─ LLM client + provider adapters + streaming
   │    ├─ Planner + Executor
   │    ├─ Approval workflow (ACT_HIGH gating)
   │    ├─ Todo/Task/Background managers
   │    ├─ Skill loader + subagent support
   │    ├─ Context compaction (micro/auto/manual)
   │    └─ Stream events + SSE bridge
   │
   ├─ Engine abstraction
   │    ├─ EngineAdapter (Nextflow/WDL)
   │    ├─ ExecutionBackend (LocalBackend, MiniWDLContainerBackend)
   │    ├─ MiniWDL mount resolver (identity-mounted paths)
   │    └─ Schema extractor
   │
   ├─ Scheduler
   │    ├─ Priority task queue
   │    ├─ Resource monitor + slot tracker (CPU/mem/disk/GPU)
   │    ├─ Retry policies + timeout watcher
   │    ├─ Cleanup policies
   │    └─ Completion hooks (audit, notifications, batch)
   │
   ├─ CLI (`bif` command — Typer + Rich)
   │    ├─ Agent (incl. approvals), project, workflow, run (incl. outputs/batch),
   │    │   file, events, system, doctor, config commands
   │    ├─ SSE event streaming (NDJSON in --output json)
   │    ├─ JSON envelope on stdout / parseable error envelope on stderr
   │    ├─ Standard flags: -V/--version, -h/--help, -p/--project, -q/--quiet
   │    ├─ Confirm-by-default destructive verbs (--force/-f to skip)
   │    └─ Config store (~/.config/bioinfoflow/cli.toml) + HTTP RemoteTransport
   │
   └─ Workflow execution
        ├─ Nextflow adapter
        └─ MiniWDL adapter (container + local backends)
```

## Key Modules
| Module | Purpose | Exports | Dependencies |
| --- | --- | --- | --- |
| `backend/app/main.py` | FastAPI app + scheduler/monitor wiring | `app` | FastAPI, API router, config, ResourceMonitor |
| `backend/app/api/v1/router.py` | API route aggregation (17 routers) | `api_router` | API route modules |
| `backend/app/runtime/events.py` | SSE event bus | `publish_event`, `subscribe_events` | asyncio queues |
| `backend/app/services/agent/agent_service.py` | Agent orchestration with compatibility fallback | `AgentService` | runtime, LLM clients |
| `backend/app/services/agent/runtime/loop.py` | Agent Runtime core loop | `agent_loop` | LLM client, dispatch |
| `backend/app/services/agent/runtime/dispatch.py` | Unified tool dispatch map | `build_dispatch` | BaseTool, runtime tools |
| `backend/app/services/agent/runtime/llm_client.py` | Provider-agnostic LLM wrapper | `LLMClient` | provider adapters |
| `backend/app/services/agent/runtime/llm_streaming.py` | Streaming LLM response handler | streaming helpers | httpx-sse |
| `backend/app/services/agent/runtime/providers.py` | Provider registry (Anthropic/OpenAI/Gemini/Ollama/...) | provider map | langchain-* |
| `backend/app/services/agent/planner.py` | Multi-step task planning | `TaskPlanner`, `ExecutionPlan` | LangChain, LLM |
| `backend/app/services/agent/executor.py` | Plan execution engine | `PlanExecutor` | Planner, tools |
| `backend/app/services/agent/approval_service.py` | High-risk action approval | `ApprovalService` | repos, events |
| `backend/app/services/run_service.py` | RunService facade (delegation only) | `RunService` | submission/dag/lifecycle/archive services |
| `backend/app/services/run_submission_service.py` | Wizard/table/unified run creation | `RunSubmissionService` | repos, dispatcher |
| `backend/app/services/run_dag_service.py` | DAG repair + mock variants | `RunDagService` | dag_parser |
| `backend/app/services/run_lifecycle_service.py` | State transitions (cancel/resume/retry) | `RunLifecycleService` | repos, dispatcher |
| `backend/app/services/run_dispatch.py` | Engine dispatch coordination | `RunDispatcher` | scheduler, engine |
| `backend/app/services/storage_service.py` | Project storage mode + external root | `StorageService` | identity-mounted paths |
| `backend/app/services/terminal_service.py` | Terminal session management | `TerminalService` | pty, asyncio |
| `backend/app/engine/registry.py` | Engine adapter registry | `get_adapter`, `register_adapter` | adapters |
| `backend/app/engine/miniwdl_container_backend.py` | MiniWDL containerized execution | backend class | Docker SDK |
| `backend/app/engine/miniwdl_mounts.py` | Host↔container mount resolution | mount helpers | identity-mounted paths |
| `backend/app/scheduler/scheduler.py` | Run scheduler orchestration | `RunScheduler` | queue, engine, hooks |
| `backend/app/scheduler/monitor.py` | Background resource sampler | `ResourceMonitor` | psutil |
| `backend/app/scheduler/slots.py` | Concurrency slot accounting | slot helpers | resources |
| `backend/app/cli/main.py` | CLI entry point (`bif` command) | Typer app, `--version`/`-h`/`-p`/`-q`/`-v` root flags | commands, transport, config_store |
| `backend/app/cli/errors.py` | `handle_errors` decorator + JSON error envelope | `handle_errors`, `_emit_error` | client, context |
| `backend/app/cli/render.py` | Output formatter (Rich tables / JSON envelopes) | `Renderer` | client, jsonio |
| `frontend/lib/api.ts` | API helper with envelope parsing | `apiRequest` | Fetch, types |
| `frontend/hooks/use-events.ts` | SSE subscription hook | `useEvents` | EventSource, types |
| `frontend/hooks/use-agent-chat.ts` | Chat state management | `useAgentChat` | API, SSE, types |
| `frontend/hooks/use-terminal-session.ts` | Terminal WebSocket connection | `useTerminalSession` | WebSocket |
| `frontend/components/bioinfoflow/chat-stream.tsx` | Chat UI + agent actions | `ChatStream` | API + SSE |

## Data Flow
- UI sends REST requests via `apiRequest` to `/api/v1/*` and renders responses.
- Long-running actions (agent, runs, image pulls) emit SSE events via `EventBus` to `useEvents`.
- Terminal sessions use WebSocket connections at `/terminal/sessions/{id}/ws`.
- Services orchestrate repositories, workflow adapters, and the agent runtime.
- **Storage layout:** run artifacts live under a unified `runs/<run_id>/` layout; `Project.storage_mode` (`managed`/`external`) plus `external_root_path` control where they anchor. Database is the source of truth.
- Agent Runtime uses an explicit async loop with between-turn hooks, context compaction, and dynamic system prompts.
- High-risk tool calls go through ApprovalService for user confirmation.
- Runs queue via Scheduler, dispatched through RunDispatcher when resources/slots allow, executed via Engine adapters.
- ResourceMonitor samples CPU/mem/disk/GPU every 30s; slot tracker enforces concurrency caps; both exposed via `/scheduler/resources`.
- Completion hooks trigger audit logging, notifications, and batch status updates.
- i18n handled by next-intl with cookie-based locale detection (en, zh-CN).
- CLI (`bif`) is an HTTP-only client for a running backend. Output is human (Rich tables/panels) by default and switches to a JSON envelope (`{success, data, error?, meta?}` on stdout, parseable error envelope on stderr) under `--output json`. Settings resolve in order CLI flag → env (`BIOFLOW_*`) → `~/.config/bioinfoflow/cli.toml` → default. Exit codes: 0 ok / 1 general / 2 usage / 3 backend / 4 connection.

## External Dependencies
- Backend: FastAPI, SQLAlchemy (async), Alembic, LangGraph, LangChain (Anthropic/OpenAI/Gemini/OpenRouter/Ollama/DeepSeek/xAI), Docker SDK, MiniWDL, Typer, Rich, psutil, structlog.
- Frontend: Next.js 16, React 19, Radix UI, Better Auth, React Flow, Tailwind CSS 4, Framer Motion, next-intl, xterm.js.

## Related Areas
- [Backend Codemap](backend.md)
- [Frontend Codemap](frontend.md)
- [Data Codemap](data.md)
