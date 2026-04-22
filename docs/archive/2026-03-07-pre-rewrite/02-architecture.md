# Bioinfoflow Architecture [CANONICAL]

**Version:** 1.1.0
**Status:** MVP
**Last Updated:** 2026-03-07

---

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Frontend (Next.js)                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            FastAPI Application                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                         │
│  │ REST API    │  │ SSE Stream  │  │ Task Runner │                         │
│  │ Endpoints   │  │ Handler     │  │ (In-process)│                         │
│  └─────────────┘  └─────────────┘  └─────────────┘                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Service Layer                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ Project     │  │ Workflow    │  │ Run         │  │ File        │        │
│  │ Service     │  │ Service     │  │ Service     │  │ Service     │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                         │
│  │ Agent       │  │ Docker      │  │ Nextflow    │                         │
│  │ Service     │  │ Service     │  │ Service     │                         │
│  └─────────────┘  └─────────────┘  └─────────────┘                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Infrastructure Layer                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                         │
│  │ SQLite      │  │ Docker      │  │ File System │                         │
│  │ (Local)     │  │ Engine      │  │             │                         │
│  └─────────────┘  └─────────────┘  └─────────────┘                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Technology Stack

| Component | Technology | Version | Purpose |
|-----------|------------|---------|---------|
| **Runtime** | Python | 3.13+ | Core language |
| **Package Manager** | uv | Latest | Dependency management |
| **Framework** | FastAPI | 0.115+ | REST API & SSE |
| **ORM** | SQLAlchemy | 2.0+ | Database abstraction |
| **Database** | SQLite | 3.x | MVP local data store |
| **Vector Store** | Local Markdown + lightweight search | - | Skills retrieval (MVP) |
| **Background Tasks** | In-process async task runner | - | Run execution & image pull |
| **Validation** | Pydantic | 2.x | Data validation |
| **Agent Framework** | LangGraph | Latest | Agentic orchestration |
| **LLM** | Auto (Gemini/OpenAI/Anthropic based on available keys) | gemini-2.5-flash / gpt-4o-mini / claude-sonnet-4-5 | Agent reasoning |
| **Workflow Engines** | Nextflow + MiniWDL (WDL) | Latest | Pipeline execution |

---

## 3. Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI entry point
│   ├── config.py                  # Pydantic Settings
│   ├── database.py                # SQLAlchemy async engine
│   │
│   ├── models/                    # SQLAlchemy ORM models
│   │   ├── base.py               # Base model with common fields
│   │   ├── project.py
│   │   ├── workflow.py
│   │   ├── run.py
│   │   ├── image.py
│   │   ├── agent_trace.py
│   │   ├── conversation.py
│   │   └── message.py
│   │
│   ├── schemas/                   # Pydantic schemas
│   │   ├── common.py             # Shared response schemas
│   │   ├── agent.py
│   │   ├── demo.py
│   │   ├── file.py
│   │   ├── image.py
│   │   ├── project.py
│   │   ├── run.py
│   │   └── workflow.py
│   │
│   ├── api/
│   │   ├── deps.py               # Dependency injection
│   │   └── v1/
│   │       ├── router.py         # API router aggregation
│   │       ├── projects.py
│   │       ├── workflows.py
│   │       ├── runs.py
│   │       ├── images.py
│   │       ├── agent.py
│   │       ├── files.py
│   │       ├── demos.py
│   │       └── events.py
│   │
│   ├── services/                  # Business logic
│   │   ├── project_service.py
│   │   ├── workflow_service.py
│   │   ├── workflow_validator.py # NEW: Workflow validation & schema extraction
│   │   ├── run_service.py
│   │   ├── image_service.py
│   │   ├── file_service.py
│   │   ├── dag_parser.py
│   │   ├── demo_catalog.py
│   │   ├── demo_service.py
│   │   ├── nextflow_service.py
│   │   ├── miniwdl_service.py
│   │   ├── docker_service.py
│   │   ├── trace_parser.py
│   │   └── agent/
│   │       ├── agent_service.py
│   │       ├── conversation_manager.py
│   │       ├── executor.py       # Plan executor
│   │       ├── graph.py          # LangGraph definition
│   │       ├── planner.py        # Task planner
│   │       ├── state.py          # Agent state schema
│   │       ├── trace.py          # Trace helpers
│   │       ├── trace_service.py  # Trace queries
│   │       ├── tools/            # Agent tools (file/code/search/workflow)
│   │       └── skills/           # Registry placeholder
│   │
│   ├── repositories/              # Data access layer
│   │   ├── base.py               # Generic CRUD repository
│   │   ├── agent_trace_repo.py
│   │   ├── conversation_repo.py
│   │   ├── image_repo.py
│   │   ├── message_repo.py
│   │   ├── project_repo.py
│   │   ├── run_repo.py
│   │   └── workflow_repo.py
│   │
│   ├── runtime/                   # In-process task runner & event bus
│   │   ├── jobs.py
│   │   ├── task_runner.py
│   │   └── events.py
│   │
│   └── utils/
│       ├── exceptions.py         # Custom exceptions
│       ├── logging.py            # Structured logging
│       ├── pagination.py         # Cursor pagination
│       ├── paths.py              # Path resolution helpers
│       ├── process.py            # Process helpers
│       └── responses.py          # Standard response helpers
│
├── tests/
├── alembic/                       # Database migrations
├── scripts/
│   ├── init_db.py                # Database initialization
│   └── seed_data.py              # Development seed data
│
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

## 4. Database Design

### Entity Relationship Diagram

```
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│   Project    │       │   Workflow   │       │     Run      │
├──────────────┤       ├──────────────┤       ├──────────────┤
│ id (PK)      │       │ id (PK)      │       │ id (PK)      │
│ name         │──┐    │ name         │──┐    │ run_id       │
│ description  │  │    │ source       │  │    │ project_id   │──┐
│ workspace_path│ │    │ engine       │  │    │ workflow_id  │──│───┐
│              │  │    │ version      │  │    │              │  │   │
│ created_at   │  │    │ schema_json  │  │    │ status       │  │   │
│ updated_at   │  │    │ created_at   │  │    │ config       │  │   │
└──────────────┘  │    └──────────────┘  │    │ started_at   │  │   │
                  │                       │    │ completed_at │  │   │
                  │                       │    │ error_msg    │  │   │
                  │                       │    └──────────────┘  │   │
                  │                       │           │          │   │
                  │                       └───────────│──────────│───┘
                  │                                   │          │
                  └───────────────────────────────────│──────────┘
                                                      │
                                                      ▼
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│ Conversation │       │ ChatMessage  │       │ DockerImage  │
├──────────────┤       ├──────────────┤       ├──────────────┤
│ id (PK)      │──┐    │ id (PK)      │       │ id (PK)      │
│ project_id   │  │    │ conv_id (FK) │───────│ name         │
│ created_at   │  │    │ role         │       │ tag          │
└──────────────┘  │    │ type         │       │ full_name    │
                  │    │ content      │       │ status       │
                  │    │ metadata     │       │ size_bytes   │
                  │    │ created_at   │       │ pull_progress│
                  │    └──────────────┘       └──────────────┘
                  │           │
                  └───────────┘
```

### Core Models

- Conversations include optional `title` and `pinned` fields for UI pinning.
- Agent trace events are stored in `agent_traces` and exposed via `/agent/conversations/{id}/trace` when `AGENT_OBSERVABILITY=true`.

#### Run Status Lifecycle
`PENDING → QUEUED → RUNNING → COMPLETED/FAILED/CANCELLED`

#### Workflow Sources
- `nf-core`: Pre-registered nf-core pipelines
- `github`: GitHub repository
- `local`: User-uploaded .nf/.wdl files

#### Workflow Engines
- `nextflow`: Nextflow pipelines
- `wdl`: WDL workflows (via MiniWDL)

---

## 5. Design Principles

1. **Async-First**: All I/O operations use `asyncio`
2. **Type-Safe**: Full type annotations with Pydantic models
3. **Layered Architecture**: Clear separation of API, Service, Repository layers
4. **Event-Driven**: Single SSE event stream for real-time updates
5. **Fail-Safe**: Graceful degradation and automatic recovery
6. **Observable**: Structured logging and metrics

---

### Observability & Debugging (gated)

**目标：** 让开发者能看到完整的 LLM prompt/response、tool calls、运行日志。

**设计要点：**
- 在 Agent graph 中记录 `agent.prompt` / `agent.response`（可截断）
- 将 tool call 的 args / output / timing 结构化持久化
- 增加 Trace API：`/agent/conversations/{conversation_id}/trace`（可选 message_id）
- SSE 附加 debug 事件（仅在 `AGENT_OBSERVABILITY=true` 时启用）
- UI 提供 Debug Drawer（Prompt / Response / Tools / Token / Latency）

**实施细节（当前实现）：**
- Trace 持久化仅在 `AGENT_OBSERVABILITY=true` 时启用
- Prompt/Response 写入前截断（默认 `agent_log_truncate_chars`）
- Tool trace 记录 `name/status/elapsed_ms`，输出做摘要或截断
- Trace 查询默认返回 response + tool，prompt 需 `include_prompt=true` 才会返回

---

## 6. Architecture Changelog

### 2026-03-07 (Run Reliability + Demo Reconciliation)
- Hardened run lifecycle: unified run payload defaults with profile resolution, added run preflight and safe resume contract
- Persisted resolved runspec and added recovery for stale runs (`416f514`, `9bb3012`, `2267910`)
- Demo reconciliation system: curate stable demos, reconcile demo projects, remove obsolete Demo project on startup (`380bf75`, `f3ecdb7`)
- Added `run_workflow` tool for agent-driven workflow execution with confirmation handling (`12c6716`)
- Completed frontend i18n (`d52e643`)
- Workflow detail page with DAG/source/parameters/tasks tabs (`f77f306`)
- Fixed agent history ordering to preserve user-first ordering (`278204b`)
- CSS cleanup: removed unused classes and consolidated duplicate `formatSize` utilities (`3c2f347`)
- Fixed turbopack panic from external tailwind source scan (`77b123f`)

### 2026-02-04 (Workflow DAG Visualization)
- Added `workflow_validator.py` service for parsing and extracting schema from Nextflow/WDL workflows
- Fixed Nextflow DSL2 dependency extraction to handle complex patterns: `PROCESS(OTHER.out.stats.collect())`
- Added regex-based WDL dependency extraction with miniwdl fallback
- Created demo workflows: `genomics-pipeline-nf` (4-step Nextflow) and `genomics-pipeline-wdl` (4-step WDL)
- Added `scripts/revalidate_workflows.py` to update existing workflows with fixed dependency extraction
- Comprehensive test suite: 14 tests in `test_workflow_validator.py` covering Nextflow and WDL parsing
- Results: viral-mini-nf shows 2 dependencies, genomics pipelines show 3-edge linear chains

### 2026-01-21 (Auth Page + Better Auth Integration)
- Better Auth database migration (`npx @better-auth/cli migrate`) creates `user`, `session`, `account`, `verification` tables in SQLite.
- Frontend auth config (`lib/auth-config.ts`) reads `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` to enable OAuth providers.
- Auth page UI enhanced with official GitHub/Google SVG icons, improved spacing (`gap-16`, `p-10`), and larger typography for better visual breathing.
- SSO callback routes: `/api/auth/callback/github`, `/api/auth/callback/google` (handled by Better Auth).

## 2026-01-20 (iteration: provider support + runtime stability)
- Agent model selection is provider-driven (`AGENT_PROVIDER`), auto-selects from configured keys (Gemini/OpenAI/Anthropic), and supports OpenAI-compatible routing (base URL + model overrides) via LangChain chat models.
- Runtime cancellation captures execution PIDs via run events and stores them in `run.config.runtime`, enabling process-tree termination for Nextflow and MiniWDL.
- EventBus now uses bounded per-project queues with a drop strategy; SSE streams include heartbeats to detect disconnects reliably.
- Image pull tasks acquire their own async DB session, and local Docker image sync is cached with a short TTL to avoid repeated scans.
- File and log reads are streamed line-by-line (no full-file loads), with `tail=0` explicitly returning complete logs.
- Frontend surfaces shared-scope labeling for Workflows/Images, adds optional project filters, uses skeleton loaders across data-heavy pages, and lazy-loads workspace tree folders.

### 2026-01-20 (Landing Page UI Refinements)
- Added `framer-motion` dependency for scroll-triggered animations across landing page components.
- Created `frontend/components/ui/scroll-animations.tsx` with reusable animation components: `FadeInOnScroll`, `StaggerContainer`, `StaggerItem`, `CountUp`, `HoverScale`.
- Added custom CSS classes in `globals.css`: `.highlight-marker` (hero text emphasis), `.nowrap` (prevent line breaks), `.gradient-fade-border-*` (smooth section transitions).
- All animations respect `prefers-reduced-motion` media query for accessibility.

### 2026-01-20 (Landing Integration)
- The Next.js root route `/` now renders the marketing landing page, while application screens remain grouped under `(app)`.
- Landing UI is modularized under `frontend/components/landing/` to keep marketing components separate from app UI.
- Shared theme tokens and utilities in `frontend/app/globals.css` include landing-specific styles.
- Global metadata/icons are centralized in `frontend/app/layout.tsx`.

### 2026-01-19 (Agent + Observability Iteration)
- Agent orchestration now uses a LangGraph loop (agent -> tools -> agent) with tool results emitted as artifact events and plan metadata carrying demo dataset IDs.
- Observability includes request-id structured logging, optional LangSmith tracing via env vars, and per-tool timing logs when enabled.
- Run execution streams now drain stdout/stderr concurrently to avoid deadlocks; run failures capture exit codes and propagate error logs to SSE.
- Agent page now surfaces demo quick actions and stronger placeholder guidance; Runs detail sidebar uses improved scrolling/height constraints.

### 2026-01-18 (Demo + Last-Mile)
- Files API now supports download/upload/delete endpoints that respect workspace-root safety.
- Run execution now persists log output to `.bioinfoflow/{run_id}/run.log`.
- Image service supports loading tarball uploads (Docker `load`).
- Agent graph can optionally use Gemini via `GEMINI_API_KEY` when Anthropic is not configured.
- Added local demo pipelines and input assets under `demo/` for self-contained Nextflow + WDL coronavirus flow.

### 2026-01-17 (Frontend Bridge)
- Frontend now uses a centralized API helper that prefixes `NEXT_PUBLIC_API_BASE_URL`, parses the `{success,data,error,meta}` envelope.
- Active project selection is shared via a lightweight ProjectContext.
- Workflows/Runs/Images pages now fetch backend data and invoke CRUD/run-control endpoints.
- Frontend SSE consumption is centralized in `use-events`, which builds `/events/stream` URLs and dispatches events.
- Agent chat now persists `conversation_id` per project, hydrates history from API, and merges SSE events.

### 2026-01-17 (Backend Core)
- Backend scaffold uses a FastAPI app with a versioned router (`/api/v1`) and OpenAPI endpoints.
- Configuration is centralized in `app/config.py` using `pydantic-settings`.
- Database layer uses async SQLAlchemy with a shared `Base` and a GUID type for UUID portability.
- Alembic is configured for async migrations with SQLite batch mode support.
- Domain models are organized by resource with UUID PKs and timestamp mixins.
- Repository layer encapsulates CRUD + cursor pagination.
- Service layer mediates business rules.
- Runtime layer includes an in-memory EventBus with per-project queues.
- Run execution is dispatched via a job runner that updates lifecycle state and publishes events.
- Agent orchestration uses a LangGraph state graph that emits structured events and persists each as a Message row.
- Global exception handling standardizes error envelopes via AppError mappings.
