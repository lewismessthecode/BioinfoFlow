# AGENTS.md

## Commands

### Backend (from `backend/`)
```bash
uv sync                                    # Install deps
uv run alembic upgrade head                # Apply migrations
uv run uvicorn app.main:app --reload --port 8000  # Dev server
uv run pytest                              # All tests
uv run pytest tests/test_api/test_runs.py -v      # Single file
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

## Environment

Full setup: `RUNBOOK.md`. Default: `cp .env.example .env` and set one provider key such as `ANTHROPIC_API_KEY`. `backend/.env` and `frontend/.env.local` are optional local overrides only. Also needs Docker daemon, `NEXTFLOW_BIN`, `MINIWDL_BIN` for workflow execution.

**Shared env defaults live in:** `.env.example`. Common backend-only override examples live in `backend/.env.example`.

## Architecture

- **`backend/`** — FastAPI + agent orchestration. Agent Runtime v2 (explicit async loop in `runtime/`) is the live path. Core flow: User Input → Agent Service → Runtime Loop → Tools → SSE Events → Frontend.
- **`backend/app/scheduler/`** — Persistent run scheduler with queue, retry, resource monitoring, and hooks. Modes: `persistent` (default), `legacy`, `local`. API: `/scheduler/status`, `/scheduler/resources`.
- **`frontend/`** — Next.js 16 App Router, React 19, React Flow DAG visualization, Radix UI + Tailwind CSS 4.
- **Database:** SQLite via async SQLAlchemy (`aiosqlite`). Tables: conversations, messages, runs, workflows, projects, agent_traces.
- **Config:** Backend `app/config.py` (env vars). LLM providers: Anthropic (default), OpenAI, Gemini — auto-selected by available API keys. Frontend: `NEXT_PUBLIC_API_BASE_URL`.

For detailed architecture, component listings, and data models, read **`codemaps/`** (`architecture.md`, `backend.md`, `frontend.md`, `data.md`).

## Testing

### Backend (`backend/tests/`)
- `pytest` + `pytest-asyncio`; `conftest.py` provides `async_client` (HTTPX) and `db_session` (per-test in-memory SQLite, overrides `get_db`).
- Key subdirs: `test_api/`, `test_agent/` (incl. `test_runtime/`), `test_scheduler/`, `test_services/`, `test_engine/`. 50+ test files total — run `uv run pytest` from `backend/`.

### Frontend (`frontend/tests/`)
- Vitest + Testing Library (jsdom). Unit (`tests/unit/`), integration (`tests/integration/`), smoke (`tests/smoke/`).
- `renderAppPage` (from `tests/app-test-utils.tsx`) returns `{ ...renderResult, appTestState }`.
- Coverage: 80% enforced via `@vitest/coverage-v8`.

## Conventions

- API responses: `{ success, data, error, meta }` envelope.
- Agent tools: `BaseTool` abstract class + `@register_tool` decorator. Risk levels: `read`, `act_low`, `act_high`.
- For complex features or significant refactors, write a plan doc in `docs/plans/`.

## Workflow

- **DB schema change:** edit models → `uv run alembic revision --autogenerate -m "desc"` → `uv run alembic upgrade head` (don't skip the revision step).
- **New agent tool:** subclass `BaseTool` + `@register_tool` decorator → register in `runtime/dispatch.py` tool map.
- **New scheduler hook:** add to `backend/app/scheduler/hooks.py` → test in `test_scheduler/test_hooks.py`.

## Gotchas

- Frontend tests: `renderAppPage` returns per-test state — never store `appTestState` in a shared variable across tests (causes flaky failures).
- Scheduler config: 10+ env vars (`SCHEDULER_*`) — check `backend/app/config.py` lines 67-76 for all options.
- Backend test DB: each test gets its own in-memory SQLite — no shared state, no cleanup needed.

## Compacting
When compacting, always preserve the full list of modified files and any test commands.
