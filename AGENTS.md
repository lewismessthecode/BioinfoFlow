# AGENTS.md

## Workflow Rules

- Before making changes, verify the current branch/worktree with `git branch --show-current` and `git worktree list`.
- When writing plans or documentation, create the file on disk instead of leaving the content only in chat.
- Before reporting completion, run the relevant verification commands for the files you changed.

## Commands

### Repo setup / Docker (from repo root)
```bash
cp .env.example .env
docker compose up -d --build
docker compose logs -f backend frontend
```

### Backend (from `backend/`)
```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
uv run pytest
uv run pytest tests/test_api/test_runs.py -v
uv run pytest tests/test_api/ -v -k "test_create"
uv run ruff check .
uv run ruff format .
uv run bif --version                    # CLI version (also -V)
uv run bif --help                       # also -h
uv run bif doctor                       # backend + scheduler + GPU + local tool checks
uv run bif project list
uv run bif config use-project proj-123  # default project (also -p / $BIOFLOW_PROJECT)
uv run bif --output json run show r-abc # JSON envelope on stdout, errors on stderr
uv run bif run cancel r-abc --force     # destructive verbs prompt unless -f
```

### Frontend (from `frontend/`)
```bash
bun install
bun run dev
bun run build
bun run start
bun run lint
bun run lint:i18n
bun run lint:dead-code
bun run test
bun run test:coverage
bun run test:watch
```

## Environment

- Canonical setup and troubleshooting live in `RUNBOOK.md`.
- The repo-root `.env` is the default source of truth for both Docker and local development.
- `backend/.env` and `frontend/.env.local` are optional machine-local overrides only.
- Effective precedence is: shell env > package-local override > repo-root `.env` > code defaults.
- Minimum useful setup: set `BIOINFOFLOW_HOME`, one provider key (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or `GEMINI_API_KEY`), and owner credentials for auth bootstrap.
- Better Auth uses `BETTER_AUTH_URL`, `BETTER_AUTH_SECRET`, and the shared auth DB path. `AUTH_MODE` supports `personal`, `team`, and `dev`.
- `NEXT_PUBLIC_*` values are baked into the frontend at build time. After changing them, restart `bun run dev` or rebuild Docker/frontend.
- Backend config is in `backend/app/config.py`; it auto-reads repo-root `.env` first, then optional `backend/.env`.
- Frontend dev/build scripts also load the repo-root `.env`; keep frontend-only overrides in `frontend/.env.local` only when truly needed.
- Workflow execution may require Docker, `NEXTFLOW_BIN`, and `MINIWDL_BIN` depending on the workflow engine.
- Path Contract v3 is the current model: `BIOINFOFLOW_HOME` should be identity-mounted so host and containers see the same absolute path.

## Architecture

- **`backend/`** — FastAPI app with service/repository layers, SQLite via async SQLAlchemy, Alembic migrations, and a Typer-based CLI (`bif`).
- **Agent Runtime v2** lives in `backend/app/services/agent/runtime/` and is the default runtime path. Core flow is: user input -> agent service -> async runtime loop -> tool dispatch -> SSE events -> frontend.
- **Run pipeline** uses a thin `RunService` facade that delegates to submission, DAG, lifecycle, archive, and dispatch services. Do not add new business logic to the facade if a dedicated service already exists.
- **`backend/app/scheduler/`** contains the persistent scheduler: queue, slot accounting, resource monitoring, retry/timeout logic, cleanup, and completion hooks. Main endpoints are `/scheduler/status`, `/scheduler/resources`, and `/scheduler/slots`.
- **`backend/app/engine/`** holds the workflow engine abstraction for Nextflow and WDL, including local/container execution backends and mount/path handling.
- **`backend/app/cli/`** provides the `bif` CLI with `remote`, `local`, and `auto` transports. Prefer `--output json` when a machine-readable envelope is useful — it emits `{success, data, error?, meta?}` on stdout and a matching error envelope on stderr (parseable by automation). Standard flags: `-V/--version`, `-h/--help`, `-p/--project`, `-q/--quiet`, `-v/--verbose`, `--no-color`. Destructive verbs (`run cancel`, `run cleanup`, `run batch cancel`, `project delete`, `file rm`) prompt by default; pass `--force/-f` in scripts. Exit codes: `0` ok, `1` general, `2` usage, `3` backend, `4` connection.
- **`backend/app/auth/` + frontend auth routes** implement Better Auth for `personal`, `team`, and `dev` modes.
- **`frontend/`** — Next.js 16 App Router, React 19, next-intl, Better Auth, React Flow, Radix UI, and Tailwind CSS 4.
- Frontend data flow is REST for regular API calls, SSE for long-running events, and WebSocket for terminal sessions.
- Detailed project maps live in `codemaps/` (`architecture.md`, `backend.md`, `frontend.md`, `data.md`, `dependencies.md`).

## Testing

### Backend (`backend/tests/`)
- `pytest` + `pytest-asyncio`.
- `conftest.py` provides `async_client` and a per-test in-memory SQLite session override.
- Important suites include `test_api/`, `test_agent/`, `test_scheduler/`, `test_services/`, `test_engine/`, and repository coverage.
- Run from `backend/` with `uv run pytest`.

### Frontend (`frontend/tests/`)
- Vitest + Testing Library (`jsdom`).
- Test groupings include `tests/unit/`, `tests/integration/`, and `tests/smoke/`.
- `renderAppPage` from `tests/app-test-utils.tsx` returns `{ ...renderResult, appTestState }`.
- Coverage is enforced via `@vitest/coverage-v8` with an 80% threshold.

## Conventions

- API responses use the `{ success, data, error, meta }` envelope.
- Agent tools use the `BaseTool` abstract class plus `@register_tool`; risk levels are `read`, `act_low`, and `act_high`.
- New UI strings must be added to both `frontend/messages/en.json` and `frontend/messages/zh-CN.json` in the same change.
- Services should go through repository methods for DB access; avoid introducing direct `session.execute()` calls in service-layer business logic.
- `frontend/app/(app)/` is the protected application layout; auth pages live under `frontend/app/auth/`.
- Prefer service-specific modules over growing catch-all files; `run_service.py` should stay a delegating facade.
- For complex features or significant refactors, write a plan doc in `docs/plans/`.

## Workflow

- **DB schema change:** update models -> `uv run alembic revision --autogenerate -m "desc"` -> `uv run alembic upgrade head`.
- **New agent tool:** subclass `BaseTool` + `@register_tool` -> register it in the runtime dispatch map.
- **New scheduler hook:** add it in `backend/app/scheduler/hooks.py` and cover it in `backend/tests/test_scheduler/`.
- **New CLI command:** add it under `backend/app/cli/commands/` and register it from `backend/app/cli/main.py`.
- **New frontend route:** add it under `frontend/app/(app)/` unless it is intentionally public/auth-related.
- **New UI copy:** update both locale files, then run `bun run lint:i18n`.
- **New plan/doc:** save it under the repo path it belongs to (`docs/plans/`, feature docs, runbooks, etc.), not just in chat.
- **Frontend env change:** if you touched `NEXT_PUBLIC_*`, restart dev or rebuild before assuming the change is live.

## Gotchas

- `CLAUDE.md` contains useful workflow and engine notes, but parts of its env/setup section are stale; prefer `RUNBOOK.md`, `.env.example`, and `backend/app/config.py` when they disagree.
- `renderAppPage` returns per-test state; never share `appTestState` across tests.
- Backend tests use isolated in-memory SQLite databases per test, so there is no shared DB state to rely on.
- `BETTER_AUTH_URL` must match the browser origin exactly or auth callbacks will fail.
- `TRUSTED_HOSTS` and `CORS_ORIGINS` must match the actual deployment host/origin when exposing the app remotely.
- `NEXT_PUBLIC_API_BASE_URL` is build-time config, not runtime config.
- `bif` is an HTTP-only client for a running backend; use `--base-url` or `BIOFLOW_API_URL` to select the API target.
- `handle_errors` decorator re-raises `click.exceptions.ClickException` (covers `BadParameter`/`UsageError`) so Click renders proper usage errors with exit code 2 — never extend the catch-all `except Exception` branch to swallow them.
- Path Contract v3 assumes identical host/container paths under `BIOINFOFLOW_HOME`; avoid reintroducing host/container path translation unless you are intentionally working on that subsystem.
- Keep per-run mount targets as siblings, not nested under a read-only parent mount, or container writes may silently break.
- miniwdl `glob()` patterns must stay relative to the task working directory; avoid absolute output globs in WDLs.

## Compacting

When compacting, always preserve the full list of modified files and any test commands.
