# Bioinfoflow Development Log

**Last Updated:** 2026-03-07

This document consolidates progress logs, code review findings, and demo documentation.

---

## Table of Contents

1. [Progress Log](#1-progress-log)
2. [Code Review Findings](#2-code-review-findings)
3. [Demo Plan](#3-demo-plan)

---

## 1. Progress Log

### 2026-03-07 (Run Reliability + Demo Reconciliation + CSS Cleanup)

- Refactored CSS: removed unused classes and consolidated duplicate `formatSize` utility (`3c2f347`)
- Fixed agent history ordering to preserve user-first ordering (`278204b`)
- Fixed turbopack panic caused by external tailwind source scan (`77b123f`)
- Removed obsolete Demo project during demo reconciliation (`f3ecdb7`)
- Curated stable demos and reconciled demo projects (`380bf75`)
- Persisted resolved runspec and added recovery for stale runs (`416f514`)
- Unified run payload defaults with profile resolution (`9bb3012`)
- Added run preflight and safe resume contract (`2267910`)
- Auto-rebuilt better-sqlite3 on ABI mismatch (`84c01d5`)
- Completed frontend i18n (`d52e643`)
- Resolved WorkflowNotEnabledError in demo runs (`19418e7`)
- Added `run_workflow` tool and improved agent confirmation handling (`12c6716`)
- Fixed premature PlanCard rendering and added batch trace writes (`0420a37`)
- Fixed source code overflow in workflow detail page (`47e5cc9`)
- Improved code organization and fixed architectural issues (`3ab0d2c`)
- Added workflow detail page with DAG/source/parameters/tasks tabs (`f77f306`)
- Fixed workflow DAG visualization with dependency extraction (`3b520c5`)
- Added comprehensive contributor guide and operational runbook (`bf1deda`)

**Tests run:** `uv run pytest`, `bun run lint`

---

### 2026-01-21 (Demo Reliability + Agent UX Implementation)

- Added backend **demo catalog** with auto-run endpoint that creates a dedicated Demo project and registers local workflows into the registry.
- Resolved **workspace paths** relative to repo root and normalized stored workspace paths to absolute paths.
- Added **Docker availability checks**: Images list returns `meta.status.docker=unavailable`; Nextflow runs fall back to local profile with `docker.enabled=false`.
- Implemented **multi-conversation UX**: create/update/delete/pin conversations, sidebar history list, and per-project conversation persistence.
- Added **slash commands** and **Cmd+K** command palette covering projects, runs, workflows, conversations, and demo actions.
- Implemented **agent trace persistence + debug drawer** (dev-only, `AGENT_OBSERVABILITY=true`) for prompt/response/tool events with truncation.
- Updated shared-scope labels for Workflows/Images and added run highlighting on demo runs.
- Fixed demo run payload handling (ignore empty project_id) and surfaced demo data source in the UI.
- Hardened Nextflow execution: auto-resolve binary from PATH, emit failure if missing, and catch runtime exceptions to avoid stuck runs.
- Adjusted demo pipeline input pairing to eliminate tuple warnings and created unique workflow names per demo card.

Tests run:
- `python3 -m compileall backend/app`
- `npm run lint` (warnings in existing files: unused vars, missing hook deps)

### 2026-01-21 (Auth Page UI + Better Auth Migration)

- Fixed **Better Auth database error** (`no such table: verification`) by running `npx @better-auth/cli migrate` to create required tables (`user`, `session`, `account`, `verification`)
- Enhanced **SSO buttons** in `auth-actions.tsx`:
  - Added official **GitHub** and **Google SVG icons** (colorful Google, monochrome GitHub)
  - Larger buttons (`h-14`), centered layout with `gap-3`
  - Smooth hover effects (`hover:shadow-md`, `hover:bg-secondary/50`)
  - Added `Loader2` spinner for loading state
- Improved **auth page layout** (`app/auth/page.tsx`):
  - Increased container width (`max-w-[1100px]`) and padding (`px-8 py-20`)
  - Better spacing between sections (`gap-16`)
  - Larger typography: title `text-[42px]`, body `text-[17px]`
  - Enhanced right panel quote card (`p-6`, `mt-12`)
  - Improved bullet point sizing (`size-2`, `gap-3`)

**Files modified:** `frontend/components/auth/auth-actions.tsx`, `frontend/app/auth/page.tsx`

---

### 2026-01-21 (Runs Page UI Refinements)

- Enhanced **Run Detail Sheet** with modern, polished layout:
  - Added sticky header with `border-b` separator for run ID
  - Wrapped metadata (Pipeline, Status, Started, Duration, Workspace) in a styled card (`rounded-xl bg-secondary/30 p-5`)
  - Improved typography hierarchy with uppercase tracking labels (`text-xs font-medium uppercase tracking-wider`)
  - Better grid spacing (`gap-x-8 gap-y-5`) for metadata fields
  - Workspace field separated with subtle `border-t border-border/50`
- Refined **Tabs Section**: grid layout (`grid grid-cols-3 h-11`), flexible height content areas
- Polished **Action Buttons**: taller `h-11` buttons, Delete styled with `hover:bg-destructive/10`
- Overall spacing improvements with consistent `p-6` padding throughout sheet

**Files modified:** `frontend/app/(app)/runs/page.tsx`

---

### 2026-01-21 (Proposal: Demo Reliability + Agent UX)

- 识别 Demo 卡片与执行路径的阻塞点：workflow 未注册、tool 结果为空、run 卡死
- 规划 Demo 一键运行：自动注册 workflow、自动创建 run、失败时给出 Docker/Nextflow 指示
- 规划多对话管理（New Conversation + 历史列表）与 Slash Commands
- 规划 Agent Trace / LLM 可观测性（Prompt/Response/Tool calls）
- 提出 hydration mismatch 修复方向（Theme/Time + Radix Trigger）
- Images 页面在 Docker 不可用时降级为提示态而非 500

## 2026-01-20 (iteration: provider support + runtime stability)
- Added `AGENT_PROVIDER` plus OpenAI-compatible settings with base URL support; agent graph now routes providers consistently with tool-calling enabled.
- Defaulted Gemini to first-class provider, while Anthropic/OpenAI are opt-in; updated `.env.example` and dependencies accordingly.
- Fixed background image pulls to use a dedicated DB session and added a cached Docker image sync window to avoid repeated scans.
- Normalized run status persistence to string values, added runtime status normalization, and implemented PID-based cancellation for Nextflow/MiniWDL.
- Added SSE heartbeats + bounded EventBus queues, and switched file/log reads to streamed access (with `tail=0` returning all logs).
- UI updates: skeleton loaders on Runs/Workflows/Images, widened Runs detail sheet, shared-scope labels + project filters, and lazy-loaded workspace tree.
- Hardened delete flows by tolerating empty/whitespace 204 responses in the API client.

Tests run:
- `uv run pytest`

### 2026-01-20 (Landing Page UI Refinements)

- Added **framer-motion** dependency for scroll-triggered animations
- Created reusable scroll animation components in `frontend/components/ui/scroll-animations.tsx`:
  - `FadeInOnScroll`, `StaggerContainer`, `StaggerItem`, `CountUp`, `HoverScale`
- Fixed hero section: "real-world biology" stays on one line (nowrap) + "Agentic workflows" highlight marker effect
- Improved trust bar visibility: larger text, better opacity, gradient fade borders
- Enhanced product tabs: animated tab indicator with motion.div layoutId, AnimatePresence for content transitions
- Refined bento grid: better spacing, proportional icons, hover scale animations
- Updated how-it-works: dashed timeline connectors, chevron arrows between steps
- Improved results section: larger KPIs (`text-7xl`), animated counters, enhanced chart styling
- Added custom CSS classes in `globals.css`: `.highlight-marker`, `.nowrap`, `.gradient-fade-border-*`
- All animations respect `prefers-reduced-motion` for accessibility

**Tests run:** `npm run build` (passes), visual QA via browser preview

---

### 2026-01-20 (Landing Page Integration)

- Integrated the v0 landing page into the main Next.js app (`frontend/app/page.tsx`) with new components under `frontend/components/landing/`
- Added landing-specific design tokens/utilities to `frontend/app/globals.css` (dot grid, section spacing, announcement colors, fade/slide animations)
- Updated global metadata/icons and font variables in `frontend/app/layout.tsx` to match landing SEO requirements
- Removed the standalone `landing-page-build/` app after integration

**Tests run:** Manual verification recommended for `/`

---

### 2026-01-19 (Agent Observability + Demo UX + Run Reliability)

- Upgraded agent graph to a LangGraph tool-calling loop with structured plan metadata and demo dataset references
- Added agent prompt/tool logging hooks plus optional LangSmith tracing configuration
- Fixed run execution deadlocks by draining stdout/stderr concurrently and improved run failure logging
- Restored Workspace panel to live file API; added agent quick demos, clearer placeholders, and intro dismissal UX
- Added skeleton loading states for Runs/Workflows/Images and improved Runs detail sidebar scroll/spacing
- Updated frontend API helper to handle 204 responses for delete flows

**Tests run:** Manual verification recommended for `/agent`, `/workflows`, `/runs`, `/images`

---

### 2026-01-18 (Demo Assets)

- Added local demo pipelines and data under `demo/` for a coronavirus UI flow (Nextflow + WDL)
- Created `memory-bank/demo-plan.md` with an end-to-end UI runbook and expected outputs

---

### 2026-01-18 (Last-Mile Wiring)

- Added file download/upload/delete endpoints (`/files/download`, `/files/upload`, `DELETE /files`) and workspace-panel wiring to live file tree with preview/download/delete actions
- Added Docker image tarball load endpoint (`/images/load`) and frontend tarball import flow
- Persisted run logs to workspace (`.bioinfoflow/{run_id}/run.log`) so `/runs/{run_id}/logs` returns real output; run outputs/download now open server-generated archives
- Workflow run dialog now posts `/runs` with params/inputs, and Agent plan "Start Analysis" scans FASTQ files, writes `samplesheet.csv`, and launches a run
- Added Gemini fallback in agent graph using `GEMINI_API_KEY` (only when Anthropic key absent)

---

### 2026-01-17 (Bridge Plan Steps 5-9)

- Added a shared SSE hook to listen for run/image/agent events on the unified `/events/stream`
- Images page now sends `project_id` on pulls and updates local image status/progress on `image.progress` events
- Runs page now updates status/logs in real time via `run.status` and `run.log` SSE events
- Agent chat now loads conversation history from the API, persists `conversation_id` per project, and streams agent responses via SSE with loading/empty states

**Tests run:** `npm run lint` (passes with existing unused-variable warnings)

---

### 2026-01-17 (Bridge Plan Steps 1-5)

- Added API base configuration, response envelope handling, and typed frontend API models
- Wired project sidebar to real `/projects` data with create flow and active project context shared across pages
- Connected Workflows, Runs, and Images pages to backend list/create/delete endpoints; runs now load logs/outputs from the API
- Added ESLint v9 flat config + dependencies so `npm run lint` can execute; removed non-deterministic sidebar skeleton widths

**Tests run:** `npm run lint` (passes)

---

### 2026-01-17 (Backend Steps 16-18)

- Added agent system with LangGraph workflow, tool wrappers, agent service, and Agent API endpoints for messaging plus conversation list/history
- Persisted agent message types with metadata and emitted SSE events (`agent.thinking`, `agent.plan`, `agent.artifact`, `agent.message`, `agent.done`)
- Added structured logging helpers with global exception handling that returns standard error envelopes
- Added Dockerfile, docker-compose, and backend README to document containerized dev workflow

**Tests run:** `uv run pytest`

---

### 2026-01-17 (Backend Steps 11-15)

- Added Docker integration and Image service with pull/delete workflows plus image metadata persistence
- Introduced in-memory event bus and SSE endpoint for real-time run/image updates
- Implemented task runner + run job orchestration with Nextflow/MiniWDL execution services
- Added Runs API endpoints (create/list/get/logs/dag/outputs/cancel/resume/retry/delete) and Images API endpoints

**Tests run:** `uv run pytest`

---

### 2026-01-17 (Schema Fix)

- Updated schema tests to use valid UUIDs for ProjectRead payloads

**Tests run:** `uv run pytest tests/test_schemas.py`

---

### 2026-01-17 (Backend Steps 4-10)

- Added async database engine/session, GUID type, and Alembic config + initial migration
- Implemented core ORM models (Project, Workflow, Run, DockerImage, Conversation, Message) with UUID PKs and timestamps
- Added init/seed scripts and verified migrations
- Implemented schemas, response envelope, and cursor pagination helpers
- Built repository layer with CRUD + cursor pagination and resource-specific filters
- Implemented Project/Workflow services and API endpoints; added File service + Files API with workspace safety and scanning

**Tests run:**
- `uv run alembic current`
- `uv run pytest tests/test_models.py`
- `uv run alembic upgrade head`
- `uv run python scripts/seed_data.py`
- `uv run pytest tests/test_schemas.py`
- `uv run pytest tests/test_repositories.py`
- `uv run pytest tests/test_api/test_projects.py`
- `uv run pytest tests/test_api/test_workflows.py`
- `uv run pytest tests/test_api/test_files.py`

---

### 2026-01-17 (Backend Steps 1-3)

- Scaffolded backend workspace with `backend/` layout, `pyproject.toml`, and `.env.example`
- Added typed settings loader and a cached `settings` object
- Bootstrapped FastAPI app with CORS, versioned routing, and OpenAPI endpoints under `/api/v1`
- Added basic async pytest fixtures and smoke tests

---

## 2. Code Review Findings

**Date:** 2026-01-19

### Critical

| Issue | Location | Description |
|:---|:---|:---|
| Background job uses request-scoped DB session | `image_service.py:59, 126` | `ImageService._pull_task` uses `self.repo` bound to the request `AsyncSession` after the request completes. Use a fresh `async_session_maker()` inside the task. |
| Run status type mismatch (enum vs string) | `run.py:31`, `jobs.py:46`, `run_service.py:72` | `Run.status` is a `String` column with a default of `RunStatus.PENDING` (enum object). This can serialize inconsistently. Use SQLAlchemy `Enum` type or store `.value` everywhere. |

### High

| Issue | Location | Description |
|:---|:---|:---|
| Cancel endpoints do not actually cancel running workflows | `nextflow_service.py:90`, `miniwdl_service.py:92`, `run_service.py:93` | Cancel methods are stubbed. Implement real cancellation (track process PID, call `nextflow cancel`, kill WDL subprocess). |

### Medium

| Issue | Location | Description |
|:---|:---|:---|
| SSE stream can hang and leak subscribers | `events.py:25` | `event_generator` blocks on `queue.get()` and only checks disconnect before await. Add timeout or cancel scopes. |
| EventBus uses unbounded queues | `events.py:10` | Slow clients can accumulate events indefinitely. Consider maxsize with drop/backpressure. |
| `scan_directory` mislabels paired-end detection | `file_service.py:204` | Once `file_format` is set to `"single-end"`, it never upgrades. |
| `read_file` loads full file into memory | `file_service.py:148` | Use streaming with `itertools.islice`. |
| Blocking shell call in async tool | `tools.py:139` | `subprocess.run` executes on event loop. Use `asyncio.to_thread` or `create_subprocess_exec`. |
| `tail=0` returns empty logs | `run_service.py:204` | `deque(maxlen=0)` drops all lines. Special case `tail=0` to return full logs. |

### Low / Missing

| Issue | Location | Description |
|:---|:---|:---|
| Workspace tree does not expand | `workspace-panel.tsx:100` | `recursive: false` used for listing. Add recursive fetch or lazy load. |
| DAG panel is static | `dag-panel.tsx:74` | Uses hardcoded nodes/edges. Integrate backend DAG data. |
| Image name parsing breaks with registries/ports | `images/page.tsx:108` | `split(":")` mishandles `ghcr.io:443/org/image:tag`. Use `lastIndexOf(":")`. |
| Listing images syncs Docker on every call | `image_service.py:25` | Consider caching or background sync. |

### Recommendations

1. **Stabilize run status storage**: Switch `Run.status` to `Enum(RunStatus, native_enum=False)` or store `.value` consistently
2. **Background tasks**: Use a dedicated session per task (not request-scoped sessions)
3. **Cancellation**: Track subprocess handles (PID + run_id) for reliable termination
4. **SSE resilience**: Add heartbeat events and timeouts; cap per-subscriber queues
5. **Large file handling**: Stream logs and outputs; consider pagination for output listings
6. **Frontend data wiring**: Use run context to drive DAG and monitor panels; add lazy directory fetches

### Open Questions

- Is the backend expected to run on Python 3.11+? → **We use Python >=3.13**
- Should `tail=0` mean all logs or no logs? → **Recommendation: all logs**
- Do you want Docker image lists cached? → **Yes, cached**

---

## 3. Demo Plan

**Date:** 2026-01-18  
**Owner:** Codex  
**Status:** Draft

### Goal

Run a complete, end-to-end demo in the UI for a simplified coronavirus workflow using both Nextflow and WDL. The demo validates: project creation, file uploads, workflow registration, run execution, logs, and outputs.

### Assets

| Asset | Path |
|:---|:---|
| Demo workspace | `demo/workspace` |
- If backend runs from `backend/`, use `../demo/workspace` (or an absolute path).
- If backend runs from repo root, use `demo/workspace`.
| FASTQ reads | `demo/workspace/reads/sampleA_R1.fastq`, `demo/workspace/reads/sampleA_R2.fastq` |
| Reference | `demo/workspace/ref/reference.fasta` |
| Nextflow pipeline | `demo/corona-nf/main.nf` |
| WDL pipeline | `demo/corona-wdl/corona_demo.wdl` |
| WDL inputs | `demo/corona-wdl/inputs.json` |

### UI Runbook

**1) Create Project**
- Name: `Corona Demo`
- Workspace path: `demo/workspace` (repo root) or `../demo/workspace` (from `backend/`)
- Description: `UI smoke test for coronavirus demo`

**2) Upload data (if not already in workspace)**
- Use Workspace panel: upload FASTQ + reference if missing

**3) Register workflows**
- Nextflow: Source = Local, file = `demo/corona-nf/main.nf`, name `corona-nf`, engine `nextflow`
- WDL: Source = Local, file = `demo/corona-wdl/corona_demo.wdl`, name `corona-wdl`, engine `wdl`

**4) Run Nextflow pipeline**
- Workspace: `.`
- Params JSON:
  ```json
  {"reads":"reads/*_{R1,R2}.fastq","reference":"ref/reference.fasta","outdir":"results"}
  ```
- Inputs JSON: `{}`

**5) Run WDL pipeline**
- Workspace: `.`
- Inputs JSON:
  ```json
  {
    "corona_demo.sample_id":"sampleA",
    "corona_demo.read1":"reads/sampleA_R1.fastq",
    "corona_demo.read2":"reads/sampleA_R2.fastq",
    "corona_demo.reference":"ref/reference.fasta"
  }
  ```
- Params JSON: `{"outdir":"results"}`

**6) Verify results**
- Runs page shows run status transitions + logs
- Outputs show QC reports in `results/`
- Download outputs and confirm archives include QC files

### Expected Artifacts

- `demo/workspace/results/sampleA.qc.txt` (both engines)
- Run logs in `.bioinfoflow/{run_id}/run.log`

### Notes

- The pipelines are intentionally lightweight and do not require Docker images
- Use local files to avoid external dependencies during the demo
- If backend is run from `backend/`, use `../demo/workspace` or an absolute path
- If run from repo root, use `demo/workspace`
