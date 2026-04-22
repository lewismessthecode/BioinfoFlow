# Architecture Codemap
<!-- Generated: 2026-04-17 | Files scanned: 216 backend + 294 frontend | Token estimate: ~900 -->
**Last Updated:** 2026-04-17
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
   │            audit, terminal, user-settings, workspaces,
   │            dag-parser, trace-parser, validators)
   │
   ├─ RunService facade (delegates to RunSubmissionService,
   │  RunDagService, RunLifecycleService, RunArchiveService,
   │  RunDispatcher) — path contract v2
   │
   ├─ Agent Runtime v2 (explicit async loop — default)
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
   │    ├─ MiniWDL mount resolver (path contract v2)
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
   │    ├─ Agent, project, workflow, run, file, system commands
   │    ├─ SSE event streaming + approval resolution
   │    └─ Config store + remote/local/auto transport
   │
   └─ Workflow execution
        ├─ Nextflow adapter
        └─ MiniWDL adapter (container + local backends)
```

## Key Modules
| Module | Purpose | Exports | Dependencies |
| --- | --- | --- | --- |
| `backend/app/main.py` | FastAPI app + scheduler/monitor wiring | `app` | FastAPI, API router, config, ResourceMonitor |
| `backend/app/api/v1/router.py` | API route aggregation (18 routers) | `api_router` | API route modules |
| `backend/app/runtime/events.py` | SSE event bus | `publish_event`, `subscribe_events` | asyncio queues |
| `backend/app/services/agent/agent_service.py` | Agent orchestration (v1 + v2) | `AgentService` | runtime, LLM clients |
| `backend/app/services/agent/runtime/loop.py` | Agent Runtime v2 core loop | `agent_loop` | LLM client, dispatch |
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
| `backend/app/services/storage_service.py` | Project storage mode + external root | `StorageService` | path contract v2 |
| `backend/app/services/terminal_service.py` | Terminal session management | `TerminalService` | pty, asyncio |
| `backend/app/engine/registry.py` | Engine adapter registry | `get_adapter`, `register_adapter` | adapters |
| `backend/app/engine/miniwdl_container_backend.py` | MiniWDL containerized execution | backend class | Docker SDK |
| `backend/app/engine/miniwdl_mounts.py` | Host↔container mount resolution | mount helpers | path contract v2 |
| `backend/app/scheduler/scheduler.py` | Run scheduler orchestration | `RunScheduler` | queue, engine, hooks |
| `backend/app/scheduler/monitor.py` | Background resource sampler | `ResourceMonitor` | psutil |
| `backend/app/scheduler/slots.py` | Concurrency slot accounting | slot helpers | resources |
| `backend/app/cli/main.py` | CLI entry point (`bif` command) | Typer app | commands, transport |
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
- **Path contract v2:** run artifacts live under a unified `runs/<run_id>/` layout; `Project.storage_mode` (`managed`/`external`) plus `external_root_path` control where they anchor. Database is the source of truth.
- Agent Runtime v2 uses an explicit async loop with between-turn hooks, context compaction, and dynamic system prompts.
- High-risk tool calls go through ApprovalService for user confirmation.
- Runs queue via Scheduler, dispatched through RunDispatcher when resources/slots allow, executed via Engine adapters.
- ResourceMonitor samples CPU/mem/disk/GPU every 30s; slot tracker enforces concurrency caps; both exposed via `/scheduler/resources`.
- Completion hooks trigger audit logging, notifications, and batch status updates.
- i18n handled by next-intl with cookie-based locale detection (en, zh-CN).
- CLI (`bif`) supports `remote`/`local`/`auto` transports; local mode runs the full ASGI app in-process for offline/script use.

## External Dependencies
- Backend: FastAPI, SQLAlchemy (async), Alembic, LangGraph, LangChain (Anthropic/OpenAI/Gemini/OpenRouter/Ollama/DeepSeek/xAI), Docker SDK, MiniWDL, Typer, Rich, psutil, structlog.
- Frontend: Next.js 16, React 19, Radix UI, Better Auth, React Flow, Tailwind CSS 4, Framer Motion, next-intl, xterm.js.

## Related Areas
- [Backend Codemap](backend.md)
- [Frontend Codemap](frontend.md)
- [Data Codemap](data.md)
