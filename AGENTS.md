# AGENTS.md

This file is the working guide for coding agents in Bioinfoflow. Keep it short,
actionable, and specific to this repo.

## First Steps

- Always run `rtk git branch --show-current` and `rtk git worktree list` before
  editing. This worktree may be detached.
- When preparing a commit or PR from a worktree, sync the remote default branch
  first so recently merged sibling worktrees do not surprise you with conflicts.
- In a worktree, treat "repo root" as the current worktree root, not the original
  checkout.
- Inspect the relevant code before changing it. Prefer `rtk rg` and
  `rtk rg --files` for search.
- Preserve user or generated changes. Do not revert unrelated dirty files.
- For significant features, refactors, or architectural decisions, write the
  plan to `docs/plans/` instead of keeping it only in chat.
- Before reporting completion, run verification commands that match the files
  changed and mention any commands that could not be run.

## RTK Rule

Prefix every shell command with `rtk`, even inside command chains:

```bash
rtk git status --short
rtk git add AGENTS.md && rtk git commit -m "docs: update agent guide"
```

If RTK has a compact filter, it uses it. Otherwise it passes the command through.

## Project Shape

- Bioinfoflow is a local agentic control plane for Nextflow and WDL pipelines.
- Backend: FastAPI, SQLAlchemy async, Alembic, Typer CLI, scheduler/runtime code.
- Frontend: Next.js 16, React 19, next-intl, Better Auth, Vitest, ESLint.
- Workflow execution depends on Docker, Nextflow, MiniWDL, and an identity-mounted
  `BIOINFOFLOW_HOME`.
- Canonical setup and troubleshooting live in `RUNBOOK.md`.

## Repo Map

- `backend/app/api/`: HTTP endpoints.
- `backend/app/services/`: business logic. Use repositories for DB access.
- `backend/app/repositories/`: database access boundaries.
- `backend/app/models/` and `backend/alembic/`: schema and migrations.
- `backend/app/scheduler/`, `backend/app/runtime/`, `backend/app/engine/`:
  run scheduling and workflow execution.
- `backend/app/cli/`: `bif` CLI commands.
- `frontend/app/(app)/`: protected app routes.
- `frontend/app/auth/`: public auth routes.
- `frontend/messages/`: locale files.
- `demo/`: runnable workflow demos.
- `docs/`: architecture, user docs, plans, and references.

## Common Commands

Repo setup / Docker, from repo root:

```bash
rtk cp .env.example .env
rtk docker compose up -d --build
rtk docker compose logs -f backend frontend
```

Backend, from `backend/`:

```bash
rtk uv sync
rtk uv run alembic upgrade head
rtk uv run uvicorn app.main:app --reload --reload-dir app --port 8000
rtk uv run pytest
rtk uv run ruff check .
rtk uv run ruff format .
rtk uv run bif --version
rtk uv run bif doctor
```

Frontend, from `frontend/`:

```bash
rtk bun install
rtk bun run dev
rtk bun run build
rtk bun run lint
rtk bun run lint:i18n
rtk bun run lint:dead-code
rtk bun run test
rtk bun run test:coverage
```

## Verification Matrix

- Backend change: `rtk uv run pytest` and `rtk uv run ruff check .` from
  `backend/`. Narrow test runs are fine while iterating; run broader checks
  before completion when the blast radius is unclear.
- Frontend change: `rtk bun run lint` and `rtk bun run test` from `frontend/`.
- New or changed UI copy: update both `frontend/messages/en.json` and
  `frontend/messages/zh-CN.json`, then run `rtk bun run lint:i18n`.
- Dead-code-sensitive frontend refactors: run `rtk bun run lint:dead-code`.
- DB schema change: create and apply an Alembic migration, then run backend tests.
- Docs-only change: inspect the changed Markdown and run a lightweight check such
  as `rtk git diff --check`.

## Backend Conventions

- Services should call repository methods instead of introducing direct
  `session.execute()` business logic.
- Prefer service-specific modules over growing catch-all files. Keep
  `run_service.py` as a delegating facade.
- New CLI commands live under `backend/app/cli/commands/` and are registered from
  `backend/app/cli/main.py`.
- New agent tools implement the `AgentTool` Protocol from
  `backend/app/services/agent_core/tools/specs.py`, live under the matching
  `tools/` subpackage, and are imported/registered in
  `backend/app/services/agent_core/tools/__init__.py`.
- New scheduler hooks go in `backend/app/scheduler/hooks.py` with tests under
  `backend/tests/test_scheduler/`.
- `handle_errors` must continue re-raising Click exceptions so usage errors exit
  with code 2.

## Frontend Conventions

- Put protected routes under `frontend/app/(app)/`; keep auth pages under
  `frontend/app/auth/`.
- Any user-facing string must be present in both locale files.
- `renderAppPage` returns per-test state; never share `appTestState` across tests.
- `NEXT_PUBLIC_*` values are baked at build time. Restart `bun run dev` or rebuild
  after changing them.

## Environment Model

- Repo-root `.env` is the default source for Docker and local development.
- `backend/.env` and `frontend/.env.local` are optional machine-local overrides.
- Precedence: shell env > package-local override > repo-root `.env` > code
  defaults.
- For local Docker, `BIOINFOFLOW_HOME` may be omitted and defaults under `data/`.
  Set it only when the platform data root must live outside the repo.
- Minimum useful setup: one provider key (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
  `GEMINI_API_KEY`, or `DEEPSEEK_API_KEY`) and auth bootstrap owner credentials.
- Better Auth uses `BETTER_AUTH_URL`, `BETTER_AUTH_SECRET`, and the shared auth DB
  path. `AUTH_MODE` supports `personal`, `team`, and `dev`.
- `BETTER_AUTH_URL`, `TRUSTED_HOSTS`, and `CORS_ORIGINS` must match the actual
  browser origin/deployment host.
- For browser UI checks in a fresh worktree, update that worktree's repo-root
  `.env` to use `AUTH_MODE=dev` before starting backend/frontend services. This
  keeps protected app routes such as `/agent` from redirecting to `/auth` during
  local visual verification. Restart the dev servers after changing `.env`.

## Workflow Gotchas

- The path model is an identity mount: `BIOINFOFLOW_HOME` should resolve to the
  same absolute path on host, backend container, workflow runner, and task
  containers.
- Keep `allow_path_translation` off except for emergency debugging of a broken
  identity-mount deployment.
- Keep per-run mount targets as siblings, not nested under a read-only parent
  mount.
- miniwdl `glob()` patterns must stay relative to the task working directory.
- `bif` is an HTTP-only client for a running backend. Use `--base-url` or
  `BIOFLOW_API_URL` to select the API target.
- Backend tests use isolated temporary SQLite databases through
  `backend/tests/conftest.py`; repository-only tests may still use in-memory
  SQLite.

## Git and PRs

- Use Conventional Commits for commits and PR titles:
  `<type>: <imperative summary>`.
- Valid types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`.
- Avoid vague titles such as `update`, `misc fixes`, `wip`, or `tweak`.
- Before opening or updating a PR, sync the remote main branch into your branch:
  `rtk git fetch origin --prune && rtk git rebase origin/main` (or merge
  `origin/main` if the branch should avoid rebasing).
- Treat the PR title as the canonical squash-merge commit message. Normalize it
  unless the user explicitly asks otherwise.

## Compacting

When compacting, preserve:

- The full list of modified files.
- Verification commands already run and their results.
- Commands still worth running next.
