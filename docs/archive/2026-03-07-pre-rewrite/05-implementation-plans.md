# Bioinfoflow Implementation Plans [CANONICAL]

**Last Updated:** 2026-03-07

This document consolidates all implementation plans for the Bioinfoflow platform.

---

## Table of Contents

1. [Backend Implementation Plan (MVP)](#1-backend-implementation-plan-mvp)
2. [Frontend-Backend Bridge Plan](#2-frontend-backend-bridge-plan)
3. [Iteration: 2026-01-19 (Agent + Observability)](#3-iteration-2026-01-19)
4. [Iteration: 2026-01-20 (LLM Providers + Stability)](#4-iteration-2026-01-20)
5. [Iteration: 2026-01-21 (Demo Reliability + Agent UX)](#6-iteration-2026-01-21-demo-reliability--agent-ux)

---

## 1. Backend Implementation Plan (MVP)

**Python target:** 3.13 (>=3.13)
**Package manager:** uv only (no pip/poetry)
**Formatting/linting:** ruff
**Testing:** pytest + pytest-asyncio + httpx.AsyncClient

### Global Decisions

- **Response envelope**: Always return `{success, data|error, meta}`. `meta` always includes `timestamp` and `request_id`.
- **Pagination**: Cursor-based with stable ordering `(created_at DESC, id DESC)`. Cursor is base64url-encoded JSON.
- **UUID**: Implement a `GUID` TypeDecorator (store as `CHAR(36)` in SQLite, native UUID in Postgres).
- **Run lifecycle**: `PENDING → QUEUED → RUNNING → COMPLETED/FAILED/CANCELLED`.
- **Event envelope (SSE)**: Every event includes `{id, event, project_id, timestamp, data}`.
- **Workflow registry**: Store local uploads under `workflow_registry_root/local/{workflow_id}/`.

### Implementation Steps

#### Step 1: Scaffold Backend Workspace
- Create `backend/` package layout (app/, tests/, scripts/, alembic/)
- Add `pyproject.toml` with Python 3.13 and explicit deps
- Add `.env.example` containing all env vars
- Add `backend/tests/conftest.py` with async fixtures

#### Step 2: Configuration and Settings
- Add typed settings with env support via `pydantic-settings`
- Expose a cached `settings` object

#### Step 3: Bootstrap FastAPI App
- Add FastAPI app with lifespan hooks, CORS, API version prefix
- Wire OpenAPI endpoints at `/api/v1/docs` and `/api/v1/openapi.json`

#### Step 4: Async Database Engine and Alembic
- Implement async SQLAlchemy engine + session maker
- Add Alembic config for async database URL
- Add naming convention and GUID TypeDecorator

#### Step 5: Core ORM Models
- Implement models: Project, Workflow, Run, DockerImage, Conversation, Message
- Use UUID PKs and timestamp mixins
- Ensure `RunStatus` includes PENDING

#### Step 6: Initial Migration and Seed Data
- Create Alembic revision for core tables
- Add `scripts/init_db.py` and `scripts/seed_data.py`

#### Step 7: Pydantic Schemas and Response Helpers
- Create request/response schemas per resource
- Implement standard response envelope and cursor pagination

#### Step 8: Repository Layer
- Create generic async CRUD repository
- Add resource-specific repositories with filters and pagination

#### Step 9: Project and Workflow Services + API
- Implement CRUD services for projects and workflows
- Handle local workflow registry storage
- Expose REST endpoints per API design

#### Step 10: File Service and Files API
- Enforce workspace-root safety
- Support list/read/write/scan operations
- File scanning for FASTQ/FQ, BAM, VCF, CRAM

#### Step 11: Docker and Image Services
- Implement Docker image listing/pull/delete
- Persist image records and emit progress events

#### Step 12: Event Bus and SSE Endpoint
- Implement in-memory event bus with per-project subscriptions
- Provide `/api/v1/events/stream` with optional filters

#### Step 13: Task Runner and Run Service
- Implement in-process async task runner
- Add run lifecycle transitions and status updates

#### Step 14: Nextflow and MiniWDL Execution
- Implement command construction and workspace execution
- Add event parsing for Nextflow and MiniWDL

#### Step 15: Runs API Endpoints
- Expose create/list/get/logs/dag/outputs/cancel/resume/retry/delete
- Use `run_id` in URLs

#### Step 16: Agent System and Agent API
- Implement agent state, tools, LangGraph workflow
- Persist all message types with metadata
- Emit agent events to SSE

#### Step 17: Error Handling and Logging
- Define custom exceptions and global exception handler
- Add structured logging helpers

#### Step 18: Containerization
- Add Dockerfile and docker-compose for local dev
- Document setup in backend README

---

## 2. Frontend-Backend Bridge Plan

**Frontend framework:** Next.js App Router
**HTTP client:** Native `fetch` + typed helpers
**API base:** `NEXT_PUBLIC_API_BASE_URL` (defaults to `http://localhost:8000/api/v1`)

### Implementation Steps

#### Step 1: API Base Config + Fetch Wrapper
- Add `frontend/.env.local` with `NEXT_PUBLIC_API_BASE_URL`
- Create API helper that prefixes base URL and parses response envelope
- Add typed response helpers in `frontend/lib/`

#### Step 2: Projects + Sidebar Integration
- Replace mock projects with `/projects` list
- Wire "New Project" to `/projects` create
- Update active project state

#### Step 3: Workflows Page Integration
- Replace mock workflows with `/workflows` list
- Wire "Register Workflow" dialog to POST `/workflows`
- Wire delete action to DELETE `/workflows/{id}`

#### Step 4: Runs Page Integration
- Replace mock runs with `/runs` list (filter + pagination)
- Wire actions: Cancel, Retry, Resume, Delete
- Wire logs panel to `/runs/{run_id}/logs`

#### Step 5: Images Page Integration
- Replace mock images with `/images` list
- Wire pull action to POST `/images/pull`
- Wire delete to DELETE `/images/{id}`

#### Step 6: Agent Chat Integration
- Wire chat input to POST `/agent/message`
- Load conversation history from `/agent/conversations/{id}`
- Persist `conversation_id` in UI state

#### Step 7: SSE Subscriptions
- Open `/events/stream?project_id=...` and filter events
- Update UI in real-time: `run.status`, `run.log`, `image.progress`, `agent.*`
- Ensure cleanup on unmount

#### Step 8: Loading, Empty, and Error States
- Add skeletons/spinners for list loading
- Show empty states when lists are empty
- Normalize error envelope handling to toast + UI messages

#### Step 9: Manual Smoke Checklist
- Required routes: `/agent`, `/workflows`, `/runs`, `/images`
- Verify CRUD operations reflect in UI
- Verify SSE updates appear without page refresh

---

## 3. Iteration: 2026-01-19

**Focus:** Agent Observability + Demo UX + Run Reliability

### Goals
1. Replace simple rule-based graph with LangGraph tool-calling loop
2. Provide model/tool visibility via structured logs and optional LangSmith tracing
3. Add 2-3 predefined demos (virus, E. coli, yeast) with real public data
4. Fix run hangs, surface errors quickly, expose detailed logs
5. Add skeletons for subpages, improve Agent intro UX, fix Runs detail sidebar

### Implementation Steps

#### Step 1: Observability Configuration
- Extend backend settings with LangSmith env vars and log verbosity toggles
- Add structured log helpers for agent prompt/response and tool timing
- Ensure request IDs are logged for API endpoints

#### Step 2: Agent Graph Upgrade
- Replace linear agent graph with LangGraph loop (agent -> tools -> agent)
- Tool calls persisted as `thinking` events, outputs as `artifact` events
- Preserve Anthropic as primary model with Gemini fallback

#### Step 3: Agent Plan Metadata
- Standardize plan metadata shape (pipeline, dataset IDs, sample counts, resources, steps)
- Ensure plan events are persisted and sent to SSE

#### Step 4: Run Execution Fixes
- Drain stdout and stderr concurrently in Nextflow and MiniWDL services
- Capture errors and send to SSE and run status updates
- Add timeout/guard to mark runs failed on unexpected exit

#### Step 5: Improved Runtime Logs
- Richer logging around run start, tool execution, process completion
- Failure logs include exit code and stderr summary

#### Step 6: Demo Catalog
- Create lightweight demo catalog with 2-3 entries:
  - SARS-CoV-2 (NCBI accession)
  - E. coli (NCBI accession)
  - Yeast (S. cerevisiae, NCBI accession)
- Each entry includes dataset IDs, expected runtime, workflow/params mapping

#### Step 7: Agent Quick Actions
- Add placeholder guidance in agent input
- Show demo quick actions at top of Agent page
- Hide intro/quick actions after user sends message

#### Step 8: Skeleton Loading
- Implement skeletons in `loading.tsx` for Runs/Workflows/Images
- Match skeleton layout to each page's table/card structure

#### Step 9: Images Deletion UX
- Handle 204 responses without expecting JSON
- Confirm delete clears image entry and surfaces success state

#### Step 10: Runs Detail Sidebar
- Adjust sidebar width/scrolling
- Prevent overflow clipping on smaller screens

---

## 4. Iteration: 2026-01-20

**Focus:** LLM Provider Support + UX Fixes + Runtime Stability

### Implementation Steps

#### Step 1: Demo Workspace Path Clarification
- Update demo-plan.md with correct workspace path guidance
- Add note about shared Workflows/Images + project-scoped Runs

#### Step 2: LLM Provider Configuration
- Extend backend settings with:
  - `AGENT_PROVIDER` defaulting to `gemini`
  - OpenAI-compatible settings: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`
  - Optional model overrides for Gemini/Anthropic
- Update `.env.example` with new vars

#### Step 3: Provider Routing
- Update agent graph to select provider based on `AGENT_PROVIDER`
- Gemini is default, Anthropic only when explicitly selected
- Add OpenAI-compatible path using LangChain

#### Step 4: Image Pull Task Session Scope
- Background image pull tasks use their own async DB session
- Acquire fresh session inside task runner

#### Step 5: Run Status Storage Normalization
- Normalize Run status storage (string values only)
- Align defaults and updates to always store `.value`

#### Step 6: Cancel Run Implementations
- Implement real cancellation for Nextflow and MiniWDL
- Track process PID or run identifier on start
- Terminate process or invoke engine cancel command

#### Step 7: SSE Stability
- Add timeout or heartbeat in SSE loop
- Set queue max size in EventBus

#### Step 8: File/Log Streaming
- Stream file reads to avoid loading entire files
- Change `tail=0` to mean "return all logs"

#### Step 9: Fix 204 Delete Responses
- Ensure delete handlers never write response body on 204
- Update frontend delete flows if necessary

#### Step 10: Cache Image Sync
- Add caching or background sync for local Docker image discovery
- Avoid repeated calls on Images page load

#### Step 11: Frontend Skeletons + Run Detail Layout
- Replace "Loading…" placeholders with skeletons
- Fix Run detail sheet width/scroll

#### Step 12: Shared-Scope UX Labels
- Add "Shared across projects" label on Workflows/Images headers
- Add a short UX note: Workflows/Images are shared across projects, while Runs are project-scoped.
- Add optional filter to show "Used by this project"

#### Step 13: Workspace Tree Expansion
- Enable recursive fetch or lazy-load children in workspace tree

#### Step 14: Update Memory Bank
- Update progress.md and architecture.md with changes

#### Step 15: Manual Smoke Checks
- Verify: `/agent`, `/workflows`, `/runs`, `/images`
- Core flows: create project, register workflow, start run, view logs/outputs, delete image/run

---

## 5. Iteration: 2026-01-20 (Landing Page UI Refinements)

**Focus:** Visual polish, scroll animations, component hierarchy

### Goals
1. Fix hero section line-break and add "Agentic workflows" highlight effect
2. Improve trust bar visibility and section integration
3. Enhance product tabs visual hierarchy
4. Refine bento grid spacing and visual coordination
5. Polish how-it-works timeline connectors and cards
6. Improve results section KPIs and chart styling
7. Add framer-motion scroll animations across all sections

### Implementation Steps

#### Step 1: Install Framer Motion
- Add `framer-motion` dependency to frontend
- Create reusable scroll animation components

#### Step 2: Hero Section Improvements
- Fix "real-world biology" line-break with `white-space: nowrap`
- Add highlight marker effect to "Agentic workflows"
- Style: semi-transparent gradient underline (monochrome)

#### Step 3: Trust Bar Enhancement
- Increase logo text opacity and size
- Add more vertical padding for breathing room
- Smooth gradient fade borders for section transition

#### Step 4: Product Tabs Refinement
- Larger preview window with better shadows
- Improved tab active state styling
- Add fade transition on tab switch

#### Step 5: Bento Grid Polish
- Reduce whitespace in large feature cards
- Coordinate icon and visual element sizing
- Add subtle hover scale animation

#### Step 6: How It Works Timeline
- Add proper dashed connector lines
- Include chevron arrows between steps
- Staggered fade-in animation for each step

#### Step 7: Results Section Refinement
- Larger KPI numbers with better typography
- Animated counters on scroll
- Enhanced chart visual styling

#### Step 8: Apply Scroll Animations
- Wrap all sections with fade-in-on-scroll
- Stagger card animations in grids
- Respect prefers-reduced-motion

#### Step 9: Testing and Verification
- Visual QA across all landing sections
- Responsive testing (mobile/tablet/desktop)
- Animation performance check

---

## 6. Iteration: 2026-01-21 (Demo Reliability + Agent UX)

**Focus:** Demo 一键可跑、对话管理、可观测性、体验清晰度

### Goals
1. 三个 Demo 卡片做到 **一键运行 + 稳定结束**
2. Agent 聊天体验清晰：Thinking / Tool / Plan / Status 分层可读
3. 支持多对话（New Conversation + 历史列表），不依赖 `/clear`
4. 引入 Slash Commands + Cmd+K 搜索
5. 显示可用的 LLM Trace / Tool Trace（仅开发模式）
6. Docker 不可用时 Images 页面不崩溃
7. 解决 SSR hydration mismatch（Radix IDs / theme）

### Implementation Steps

#### Step 1: Demo Registry + One‑Click Run
- 在 backend 增加 Demo catalog（id/title/species/accession/workflow/params）
- Demo 点击后自动注册 workflow（如不存在，需复制到 workflow registry）
- 自动创建/复用专用 **Demo Project**
- 直接创建 run 并跳转 Runs 页面
- Demo 参数默认使用 `demo/workspace`，并可在 UI 中显示数据来源
- 相对路径统一按 **repo root** 解析（避免 backend cwd 造成的路径错误）

#### Step 2: Docker / Nextflow 运行前检查
- 启动 run 前检测 Docker socket 可用性
- 不可用时自动禁用 Docker（config override）并移除 `-profile docker`
- 在 UI 显示 “Docker not running” banner

#### Step 3: Agent Trace & LLM Observability
- 持久化 `agent.prompt` / `agent.response`（可截断，仅 `AGENT_OBSERVABILITY=true` 时启用）
- 增加 Trace API（按 conversation / message 查询）
- 前端 Debug Drawer 展示 prompt/response/tool calls
- Trace 默认不返回 prompt/response，需 `include_prompt=true`

#### Step 4: Thinking + Tool Trace UI 重构
- Tool calls 去重、合并展示
- 空结果卡片显示明确空态
- Thinking block 仅显示“摘要 + trace”，不显示模型推理

#### Step 5: Conversation 管理
- 新建 `/agent/conversations` 创建接口
- UI 提供 New Conversation + 历史列表（支持重命名 / 删除 / Pin）
- `/clear` 只清空当前 UI，不删除历史

#### Step 6: Slash Commands + Cmd+K
- 输入框支持 `/new /clear /run /demo /publish /help`
- Command Palette 搜索 Projects / Runs / Workflows / Conversations（基于 `cmdk`）

#### Step 7: Hydration Mismatch 修复
- Theme / time formatting 使用 `mounted` guard（如未复现可跳过）
- Radix Trigger 组件延迟渲染或 `suppressHydrationWarning`
- 修复 `toLocaleTimeString` 在 SSR 的一致性

#### Step 8: Images Page Resilience
- Docker 不可用时返回空列表 + 状态
- UI 显示 Docker 状态与重试入口

#### Step 9: Demo Run 完整验证
- Corona / E. coli / Yeast 分别跑通
- 运行日志、Outputs 正常生成

---

## 7. Active Sprint Plans

Active sprint plans are maintained in the `docs/plans/` directory:

| Plan | Status | Focus |
|------|--------|-------|
| [2026-03-05 Run Reliability](plans/2026-03-05-run-reliability-implementation-plan.md) | Active | Run lifecycle hardening, stale run recovery, runspec persistence |
| [2026-02-05 Frontend i18n](plans/2026-02-05-frontend-i18n-completion.md) | Completed | Frontend internationalization |

Completed plans are archived in `docs/plans/archive/`.
