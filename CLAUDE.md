# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workflow Rules
- When writing plans or documentation, always create actual files on disk — never output plan content only in chat/plan mode, e.g. `docs/plans/plan-cli-v1.md`.
- Always verify which branch/worktree you are on before making changes. Run `git branch --show-current` and `git worktree list` before applying fixes.
- After implementing changes, always run the test suite before reporting completion. Fix any failures before asking for review.

## Commands

### Backend (from `backend/`)
```bash
uv sync                                    # Install deps
uv run alembic upgrade head                # Apply migrations
uv run uvicorn app.main:app --reload --port 8000  # Dev server
uv run pytest                              # All tests
uv run pytest tests/test_api/test_runs.py -v      # Single file
uv run pytest tests/test_api/ -v -k "test_create" # Filter by name
uv run ruff check . && uv run ruff format .       # Lint + format
```

### Frontend (from `frontend/`)
```bash
bun install          # Install deps
bun run dev          # Dev server (port 3000)
bun run build        # Production build
bun run lint         # ESLint
bun run test         # Vitest unit + integration
bun run test:coverage  # V8 coverage (80% threshold)
bun run test:watch     # Re-run on file change (dev loop)
bun run lint:dead-code # knip — find unused exports
```

### CLI (from `backend/`)
```bash
uv run bif --version                           # Show CLI version
uv run bif --help                              # All commands (also -h)
uv run bif doctor                              # Health check
uv run bif project list                        # List projects
uv run bif -p proj run list                    # Scope to a project (-p / --project)
uv run bif --output json run show r-abc        # JSON envelope on stdout
uv run bif config use-project proj-123         # Set default project
uv run bif config set mode local               # Validated; rejects unknown values
uv run bif config unset project_id             # Remove a setting
uv run bif run cancel r-abc --force            # Confirm-by-default; -f skips
uv run bif agent send "analyze samples" -p proj  # Prints conversation ID + resume hint
uv run bif open run r-abc                      # Open a page in the browser ($BIOFLOW_WEB_URL)
```

**Transports.** `bif` supports three modes: `remote` (HTTP to a running server), `local` (in-process ASGI, no server needed), `auto` (tries remote, falls back to local). Set with `--mode` or `BIOFLOW_MODE`.

**Output contract.** `--output human` (default) renders Rich tables/panels on stdout. `--output json` (or `BIOFLOW_OUTPUT=json`) emits a `{success, data, error?, meta?}` envelope on **stdout**, and any error — including `ConnectionFailed` and `BadParameter` — as a parseable `{success:false, error:{code,message,...}}` envelope on **stderr**. Streaming commands (`run watch`, `events stream`, `run logs --follow`) emit NDJSON.

**Standard flags** (root): `-V/--version`, `-h/--help`, `-p/--project`, `-q/--quiet`, `-v/--verbose`, `--no-color` (also honors `NO_COLOR`), `--mode`, `--base-url`, `--output`. Resolution order for every overridable setting: CLI flag → env var (`BIOFLOW_*`) → `~/.config/bioinfoflow/cli.toml` → built-in default.

**Exit codes.** `0` ok · `1` general · `2` bad usage / spec / Click `BadParameter` · `3` backend/API error · `4` connection failure.

**Destructive commands** (`run cancel`, `run cleanup`, `run batch cancel`, `project delete`, `file rm`) prompt in human mode; pass `--force/-f` to skip in scripts.

## Environment

Full setup: `docs/operations/runbook.md`. Minimum: `cp backend/.env.example backend/.env` and set `ANTHROPIC_API_KEY`. Also needs Docker daemon, `NEXTFLOW_BIN`, `MINIWDL_BIN` for workflow execution.

**Not in `.env.example` yet:** `AGENT_RUNTIME_V2`, `AGENT_MAX_ROUNDS`, `AGENT_COMPACT_THRESHOLD`, all `SCHEDULER_*` vars, `RUN_SCHEDULER_MODE` — defaults in `app/config.py` work for local dev.

## Architecture

- **`backend/`** — FastAPI + agent orchestration. Agent Runtime v2 (explicit async loop in `services/agent/runtime/`) is the default; v1 LangGraph StateGraph (`graph.py`) is the fallback. Core flow: User Input → Agent Service → Runtime Loop → Tools → SSE Events → Frontend. Runtime v2 modules: `loop`, `dispatch`, `llm_client`, `compact`, `todo`, `tasks`, `skills`, `subagent`, `session_state`, `system_prompt`, `background`, `messages`.
- **`backend/app/services/run_service.py`** — RunService is a facade that delegates to `RunSubmissionService` (wizard/table/unified run creation), `RunDagService` (DAG repair + mock variants), `RunLifecycleService` (state transitions), and `RunDispatchService` (engine dispatch). All callers import from `run_service.py` — never import the sub-services directly.
- **`backend/app/scheduler/`** — Persistent run scheduler with priority queue, retry policies, resource monitoring (CPU/mem/disk/GPU), and completion hooks. Modes: `persistent` (default), `legacy`, `local`. API: `/scheduler/status`, `/scheduler/resources`.
- **`backend/app/engine/`** — Workflow execution via adapter pattern. `EngineAdapter` interface with Nextflow and WDL adapters. `LocalBackend` for execution, `SchemaExtractor` for workflow parameter discovery.
- **`backend/app/cli/`** — `bif` CLI (Typer + Rich). Three transport modes (`RemoteTransport`, `LocalTransport`, `AutoTransport`). Commands for projects, workflows, runs (incl. `outputs`, `batch`), agent (incl. `approvals`), files, events, system, doctor, config. `errors.handle_errors` is the standard command decorator: it closes the API client, emits a JSON envelope on stderr in `--output json` mode, and re-raises Click `BadParameter`/`UsageError` so usage errors keep exit code 2.
- **`frontend/`** — Next.js 16 App Router, React 19, React Flow DAG visualization, Radix UI + Tailwind CSS 4. Auth via Better Auth. i18n via next-intl (en, zh-CN).
- **Communication:** REST for CRUD, SSE (`EventBus`) for long-running operations (agent, runs, image pulls), WebSocket for terminal sessions (`/terminal/sessions/{id}/ws`).
- **Database:** SQLite via async SQLAlchemy (`aiosqlite`). ORM models in `models/`, repositories in `repositories/`, schemas in `schemas/`, migrations via Alembic.
- **Config:** Backend `app/config.py` (Pydantic Settings, 40+ env vars). LLM providers: Anthropic (default), OpenAI, Gemini — auto-selected by available API keys. Frontend: `NEXT_PUBLIC_API_BASE_URL`.
- **Backend layers:** API routes (`api/v1/`) → Services (`services/`) → Repositories (`repositories/`) → Models (`models/`). Schemas in `schemas/`. Services must NOT use `session.execute()` directly — delegate to repository methods.

For detailed architecture, component listings, data models, and current file counts, read **`codemaps/`** (`architecture.md`, `backend.md`, `frontend.md`, `data.md`, `dependencies.md`).

## Engine Contracts

Three contracts govern workflow execution. Violating any of them produces silent or misleading failures. All have regression tests; do not weaken them without reading those tests and the comments inside the relevant files first.

**Path Contract (identity mount).** `BIOINFOFLOW_HOME == BIOINFOFLOW_HOME_HOST`, enforced at startup by `assert_identity_mount()` (`backend/app/path_layout.py:192`). Host path == container path everywhere — no translation layer in code. Per-run mounts (`runs/{run_id}/input` ro, `runs/{run_id}/results` rw) are **siblings, never nested under `project_root`** — Docker Swarm silently demotes a rw child whose parent is mounted ro. Locked by `test_configured_run_mounts_never_nests_targets`.

**Image Contract (UID alignment).** Every task container runs with `--user {backend_uid}:{backend_gid}` regardless of the image's `USER` directive. WDL: `[task_runtime] as_user = true` in the cfg generated by `_write_runner_cfg` (`backend/app/engine/adapters/wdl.py`). Bioinformatics images (e.g. `deaf:V2.0.9.9` ships `USER 1000`) cannot write to root-owned shared dirs otherwise.

**Runtime Contract (engine integration).**
- WDL is invoked via `python -m app.engine._miniwdl_entry run ...`, **not** the raw `miniwdl` binary. The entry module pre-registers `BioinfoflowSwarmContainer` in miniwdl's `_backends` dict, bypassing flaky `importlib.metadata` entry-point discovery.
- `BioinfoflowSwarmContainer.host_path` extends miniwdl's work-dir-only output validation to accept paths under platform-declared rw mounts — so production WDLs declaring `File foo = "${outdir}/x"` work. Paths outside those mounts still go through miniwdl's stock check (the `/etc/passwd`-style escape guard stays).
- WDL adapter parses miniwdl's universal `wdl.w:WORKFLOW.t:call-TASK ...` log lines into `EngineEventType.TASK_UPDATE` events that drive the live DAG. Authoritative signals only: `task setup` → submitted, `docker task running` → running, `NOTICE done` → completed (NOT `docker task exit :: state: "complete"` — false-positive when post-task validation later fails), `ERROR ... failed` → failed.

## Testing

### Backend (`backend/tests/`)
- `pytest` + `pytest-asyncio`; `conftest.py` provides `async_client` (HTTPX) and `db_session` (per-test in-memory SQLite, overrides `get_db`).
- Key subdirs: `test_api/`, `test_agent/` (incl. `test_runtime/`), `test_scheduler/`, `test_services/`, `test_engine/`. Run `uv run pytest` from `backend/`.

### Frontend (`frontend/tests/`)
- Vitest + Testing Library (jsdom). Unit (`tests/unit/`), integration (`tests/integration/`), smoke (`tests/smoke/`).
- `renderAppPage` (from `tests/app-test-utils.tsx`) returns `{ ...renderResult, appTestState }`.
- Coverage: 80% enforced via `@vitest/coverage-v8`.

## Conventions

- API responses: `{ success, data, error, meta }` envelope.
- Agent tools: `BaseTool` abstract class + `@register_tool` decorator. Risk levels: `read`, `act_low`, `act_high`. `act_high` triggers the approval workflow.
- Frontend routing: `app/(app)/` is the protected layout (dashboard, workflows, runs, agent, scheduler, images). Auth pages under `app/auth/`.
- For complex features or significant refactors, write a plan doc in `docs/plans/`.

## Workflow

- **DB schema change:** edit models → `uv run alembic revision --autogenerate -m "desc"` → `uv run alembic upgrade head` (don't skip the revision step).
- **New agent tool:** subclass `BaseTool` + `@register_tool` decorator → register in `runtime/dispatch.py` tool map.
- **New scheduler hook:** add to `backend/app/scheduler/hooks.py` → test in `test_scheduler/test_hooks.py`.
- **New CLI command:** add module in `backend/app/cli/commands/` → register in `cli/main.py`. Wrap each command with `@handle_errors`, fetch state via `cli_ctx, r = unpack_ctx(ctx)`, and use `r.success(...)`/`r.detail(...)`/`r.table(...)`/`r.emit_data(...)` for output (never write JSON inline). Destructive verbs gate on `--force/-f` and `cli_ctx.output_mode == "human"` before calling `typer.confirm(..., abort=True)`. Add a smoke test under `backend/tests/test_cli/` and assert exit codes precisely (`== 2` for usage errors, not just `!= 0`).
- **New frontend route:** add directory under `frontend/app/(app)/` with `page.tsx` → add sidebar link in `components/bioinfoflow/sidebar/`.
- **New WDL demo:** add WDL under `demo/{name}/` → ensure each declared `output { File X = "..." }` path actually exists at the literal path after the task command runs (use `cp` after any `rename.pl`-style scripts; do **not** try miniwdl's `glob()` for absolute paths) → validate parse with `cd backend && uv run python -c "import WDL; WDL.load('../demo/{name}/{file}.wdl')"`.

## Gotchas

- `agent_runtime_v2` defaults to `True` — if you see `graph.py` code, that's the v1 fallback, not the active path.
- Frontend tests: `renderAppPage` returns per-test state — never store `appTestState` in a shared variable across tests (causes flaky failures).
- Scheduler config: 10+ env vars (`SCHEDULER_*`) — check `backend/app/config.py` lines 67-76 for all options.
- Backend test DB: each test gets its own in-memory SQLite — no shared state, no cleanup needed.
- CLI `LocalTransport` enters the full FastAPI lifespan (DB init, scheduler) — useful for testing but heavier than `RemoteTransport`.
- **CLI `handle_errors` and Click exceptions.** The decorator's catch-all `except Exception` would swallow `typer.BadParameter` / `click.UsageError` and downgrade them to `[UNEXPECTED]` exit-1. They are explicitly re-raised so Click can render the standard usage error with exit code 2 — keep this branch when adding new exception handling.
- Services must delegate DB queries to repositories — never use `session.execute()` directly in service code. This was enforced in the 2026-04-04 prune.
- Frontend uses Better Auth (v1.4.17) for authentication — config in `frontend/lib/auth.ts` and `auth-config.ts`.
- **Swarm nested bind mounts.** A `rw` child mount under a `ro` parent is silently demoted to `ro`. Always declare per-run mounts as siblings (`runs/{run_id}/input` + `runs/{run_id}/results`); never re-introduce a `project_root` mount alongside them.
- **miniwdl `glob()` is local-only.** Patterns must be relative to the task work dir (`/mnt/miniwdl_task_container/work`); absolute patterns like `glob("${outdir}/*.zip")` raise `EvalError: glob() pattern must be relative to task working directory`. If a script renames the declared output, restore the canonical name in the same command block (e.g. `cp ${outdir}/*_Result.zip ${outdir}/Result.zip`).
- **WDL `command { ... }` parens-in-comments.** Bash-style comments containing parentheses inside `command { }` blocks break WDL's brace-matching with cryptic "Expected one of: CNAME, RBRACE, ..." parse errors. Keep command-block comments paren-free, or switch to the `command <<< ... >>>` heredoc form (which uses `~{var}` interpolation).

## Maintenance

- **Pruning cadence:** Run `/codebase-pruning` every 2 weeks or after major features. Reports go to `docs/reviews/prune-{date}.md`.
- **Codemap refresh:** Update `codemaps/*.md` statistics when file counts drift by >10%. The generated dates in comment headers track staleness.
- **Dead code detection:** `bun run lint:dead-code` (frontend, via knip). Backend relies on manual review during pruning.

## Frontend Development Rules

1. **i18n sync is mandatory.** Every new UI string must be added to BOTH `messages/en.json` AND `messages/zh-CN.json` in the same commit. Verify the key lands in the correct namespace — never add keys to the wrong section.
2. **Invoke design skills** (`/frontend-design`, `/web-design-guidelines`, `/vercel-react-best-practices`...) when creating or modifying visual components. Do not design UI elements without skill guidance.
3. **Reuse before creating.** Before writing a new component, search for existing components with similar functionality on the same page. Extract shared pieces (e.g. `WorkflowPills`) instead of duplicating styling across siblings.
4. **First-principles simplicity.** Think from actual user scenarios and native tool conventions. Avoid over-engineering — if an existing component covers the need, use it. 奥卡姆剃刀: 如无必要，勿增实体。
5. **Responsive and contained.** New elements must fit within the viewport without scrolling or overflow. Use flex-fill (`flex-1 min-h-0`) instead of fixed pixel heights inside dialogs/panels. Always test at `sm:max-w-4xl` dialog size.
6. **Visual hierarchy matters.** Establish clear text hierarchy: primary name (bold, larger), secondary metadata (colored pill badges), tertiary info (muted, smaller). Don't flatten everything to the same font size/weight.

## Design Context

See `.impeccable.md` for full details. Key principles:

- **Brand:** Smart, Minimal, Powerful. References: Linear, Vercel.
- **Users:** Mixed technical levels — PIs wanting simplicity to postdocs wanting full control.
- **Aesthetic:** Refined Scientific Minimalism. Dark mode is the primary design target.
- **Principles:**
  1. Progressive disclosure over feature walls.
  2. Information hierarchy is non-negotiable (primary > secondary > tertiary).
  3. Motion with purpose (150ms fast / 250ms normal / 400ms ceremonial). Respect `prefers-reduced-motion`.
  4. Density when needed, breathing room when not.
  5. Dark mode is home — design dark-first, then adapt for light.
- **Accessibility:** WCAG 2.1 AA. Focus rings, keyboard nav, reduced-motion, semantic color never alone.

## Compacting
When compacting, always preserve the full list of modified files and any test commands.
