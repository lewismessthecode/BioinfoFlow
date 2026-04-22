# Backend Codemap
<!-- Generated: 2026-04-17 | Files scanned: 216 | Token estimate: ~1000 -->
**Last Updated:** 2026-04-17
**Entry Points:** `backend/app/main.py`, `backend/app/api/v1/router.py`, `backend/app/cli/main.py`, `backend/alembic/env.py`

## Architecture
```
HTTP /api/v1
   │
   ▼
API Routers (18) → Services → Repositories → SQLite (aiosqlite)
   │                  │
   │                  ├─ Workflow adapters (Nextflow / MiniWDL local / MiniWDL container)
   │                  ├─ Engine abstraction (adapter registry + backends + mounts)
   │                  ├─ Agent Runtime v2 (async loop + 17 modules)
   │                  ├─ Planning system (Planner + Executor)
   │                  ├─ Approval workflow (ACT_HIGH gating)
   │                  ├─ Scheduler (queue + slots + resources + monitor + retry + timeout)
   │                  ├─ Run service facade (submission/dag/lifecycle/archive/dispatch)
   │                  ├─ Storage service (path contract v2)
   │                  ├─ Batch processing
   │                  ├─ Terminal sessions (pty + WebSocket)
   │                  └─ Notifications + audit logging
   │
   ├─ SSE EventBus (runtime/events.py)
   │
   └─ CLI (`bif` — Typer + Rich)
        ├─ Agent, project, workflow, run, file, system commands
        ├─ SSE streaming + approval resolution
        └─ Config store + remote/local/auto transport
```

## API Routes (18 routers)
| Prefix | Module | Notes |
| --- | --- | --- |
| `/projects` | `projects.py` | CRUD + search + storage mode |
| `/projects/{id}/workflows` | `project_workflows.py` | Bind/unbind + pin workflows |
| `/workflows` | `workflows.py` | Registry + metadata + DAG + source |
| `/files` | `files.py` | Scan/read/write/upload/download |
| `/storage` | `storage.py` | Project storage backend + external roots (path contract v2) |
| `/images` | `images.py` | Docker images + pull + load |
| `/demos` | `demos.py` | Demo catalog + run |
| `/events` | `events.py` | SSE stream (filtered by conversation/run/image) |
| `/batch` | `batch.py` | Batch run creation + status + cancel |
| `/runs` | `runs.py` | Run lifecycle + logs + outputs + DAG + cancel/resume/retry |
| `/notifications` | `notifications.py` | Notification config CRUD |
| `/scheduler` | `scheduler.py` | Scheduler status + resources + slots |
| `/agent` | `agent.py` | Conversations + messages + traces + approvals |
| `/stats` | `stats.py` | Dashboard metrics aggregation |
| `/system` | `system.py` | Health check + GPU status + metrics |
| `/terminal` | `terminal.py` | Terminal sessions (create/close + WebSocket I/O) |
| `/user-settings` | `user_settings.py` | Per-user preferences CRUD |
| `/providers` | `providers.py` | LLM provider catalog + model listing |

## Services (30+ files, grouped)
**Run pipeline (RunService facade)**
| Module | Purpose |
| --- | --- |
| `run_service.py` | Thin facade — delegates only, never holds logic |
| `run_submission_service.py` | Wizard/table/unified run creation |
| `run_dag_service.py` | DAG repair + mock variants |
| `run_lifecycle_service.py` | State transitions (cancel/resume/retry) |
| `run_dispatch.py` | Engine dispatch coordination (RunDispatcher) |
| `run_archive.py` | Archive/export of completed runs |
| `run_profile_service.py` | Profile-based run configuration |
| `run_helpers.py` | Shared run utilities |
| `dag_parser.py` | Workflow DAG parsing |
| `trace_parser.py` | Execution trace parsing |

**Storage + Workflow**
| Module | Purpose |
| --- | --- |
| `storage_service.py` | Project storage mode (managed/external), external root paths |
| `project_workflow_service.py` | Workflow binding + pinning |
| `workflow_service.py` | Workflow registry operations |
| `workflow_validator.py` | WDL/Nextflow validation |
| `validators/` | Per-engine validation modules |

**Agent / Approval**
| Module | Purpose |
| --- | --- |
| `agent/agent_service.py` | Agent orchestration (v1 + v2) |
| `agent/graph.py` | LangGraph agent loop (v1 fallback) |
| `agent/planner.py` + `executor.py` | Task decomposition + plan execution |
| `agent/approval_service.py` | ACT_HIGH tool gating |
| `agent/conversation_manager.py` | Conversation state |
| `agent/tools/*.py` | BaseTool + file/code/search/workflow tools + sandbox |

**Scheduler-adjacent + infrastructure**
| Module | Purpose |
| --- | --- |
| `audit_service.py` | Action audit trail |
| `batch_service.py` | Batch run orchestration |
| `notification_service.py` | Notification delivery |
| `terminal_service.py` + `terminal_shell/` | Terminal session management |
| `docker_service.py` / `image_service.py` | Docker + image lifecycle |
| `miniwdl_service.py` / `nextflow_service.py` | Engine helpers |
| `file_service.py` | File scan / read / write |
| `gpu_service.py` | GPU detection |
| `stats_service.py` / `demo_service.py` / `demo_catalog.py` | Dashboard + demo seed |
| `user_settings_service.py` / `workspace_service.py` / `project_service.py` | Account + workspace ops |

## Agent Runtime v2 (backend/app/services/agent/runtime/, 17 modules)
| Module | Purpose |
| --- | --- |
| `loop.py` | Core async agent loop with between-turn hooks |
| `dispatch.py` | Unified tool dispatch map (BaseTool + legacy + runtime tools) |
| `llm_client.py` | Provider-agnostic LLM wrapper |
| `llm_providers.py` | Provider implementations (Anthropic/OpenAI/Gemini/Ollama/...) |
| `llm_streaming.py` | Streaming response handler |
| `providers.py` | Provider registry + selection |
| `messages.py` | Plain dict message helpers (Anthropic Messages API format) |
| `session_state.py` | Per-session state container |
| `system_prompt.py` | Dynamic system prompt with todo/skills/tasks injection |
| `compact.py` | 3-layer context compaction (micro/auto/manual) |
| `todo.py` | TodoManager with nag reminders |
| `tasks.py` | TaskManager + persistent DAG in .tasks/ JSON files |
| `background.py` | BackgroundManager: daemon threads for shell commands |
| `skills.py` | SkillLoader: two-layer injection from agent-skills/ |
| `subagent.py` | Context-isolated child agent loop |
| `stream_events.py` | Stream event schema + SSE bridge |

## Engine Abstraction (backend/app/engine/)
| Module | Purpose |
| --- | --- |
| `adapter.py` | Abstract EngineAdapter interface |
| `backend.py` | EngineEvent/EngineEventType + abstract ExecutionBackend |
| `local.py` | LocalBackend: local process execution with event streaming |
| `miniwdl_container_backend.py` | Containerized MiniWDL execution backend |
| `miniwdl_mounts.py` | Host↔container mount resolution (path contract v2) |
| `registry.py` | Adapter registry with built-in Nextflow/WDL registration |
| `schema_extractor.py` | Workflow schema extraction via engine adapters |
| `adapters/nextflow.py` | NextflowAdapter: GPU detection, resume support |
| `adapters/wdl.py` | WDLAdapter: MiniWDL binary resolution |

## Scheduler (backend/app/scheduler/)
| Module | Purpose |
| --- | --- |
| `scheduler.py` | Main orchestrator: engine execution, DAG, events, status |
| `queue.py` | Priority task queue (DB-backed) |
| `resources.py` | SystemResources dataclass |
| `slots.py` | Concurrency slot accounting (by engine/project) |
| `monitor.py` | Background CPU/mem/disk/GPU sampler |
| `retry.py` | Exponential backoff retry policies |
| `timeout.py` | Run timeout watcher (default 24h) |
| `cleanup.py` | Workspace cleanup policies |
| `hooks.py` | Completion hooks (audit, notifications, batch) |
| `config.py` | Scheduler configuration (concurrency, polling, resources) |
| `models.py` | ScheduledTask, TaskPriority, TaskState |

## CLI (backend/app/cli/)
| Module | Purpose |
| --- | --- |
| `main.py` | Entry point, Typer app registration |
| `transport.py` | HTTP transport layer (remote/local/auto) |
| `api_helpers.py` | Shared API call patterns |
| `render.py` | Rich console output formatting |
| `config_store.py` | Persistent config (TOML file) |
| `context.py` | CLI context (project/conversation state) |
| `errors.py` | Error handling + user-friendly messages |
| `commands/agent.py` + `agent_approvals.py` | Agent chat, streaming, approvals |
| `commands/project.py` / `workflow.py` / `run.py` / `run_batch.py` / `run_outputs.py` | Core entity commands |
| `commands/file.py` / `events.py` / `system.py` / `config_cmd.py` / `doctor.py` | File ops, SSE streaming, diagnostics |

## External Dependencies
- FastAPI, Uvicorn, Pydantic + pydantic-settings
- SQLAlchemy async + aiosqlite, Alembic
- LangGraph + LangChain (Anthropic/OpenAI/Gemini/OpenRouter/Ollama/DeepSeek/xAI)
- Docker SDK, MiniWDL, psutil, structlog
- Typer, Rich (CLI)

## Related Areas
- [Architecture Codemap](architecture.md)
- [Data Codemap](data.md)
