# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workflow Rules
- When writing plans or documentation, always create actual files on disk — never output plan content only in chat/plan mode, e.g. `docs/plans/plan-cli-v1.md`.
- Always verify which branch/worktree you are on before making changes. Run `git branch --show-current` and `git worktree list` before applying fixes.
- After implementing changes, always run the test suite before reporting completion. Fix any failures before asking for review.
- Use Conventional Commits for all git commit messages and PR titles: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`. Format: `<type>: <imperative summary>`.
- Treat the PR title as the canonical squash-merge commit message. When creating or updating a PR, always normalize the title to the Conventional Commits format unless the user explicitly asks otherwise.
- Avoid vague git/PR titles such as `update`, `misc fixes`, `wip`, or `tweak`; choose the most specific valid type and a concise summary of the user-visible change.

## Commands

### Backend (from `backend/`)
```bash
uv sync                                    # Install deps
uv run alembic upgrade head                # Apply migrations
uv run uvicorn app.main:app --reload --reload-dir app --port 8000  # Dev server
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
uv run bif config set base_url http://localhost:8000/api/v1
uv run bif config unset project_id             # Remove a setting
uv run bif run cancel r-abc --force            # Confirm-by-default; -f skips
uv run bif agent send "analyze samples" -p proj  # Prints conversation ID + resume hint
uv run bif open run r-abc                      # Open a page in the browser ($BIOFLOW_WEB_URL)
```

## Environment

Full setup: `RUNBOOK.md` and `docs/operations/runbook.md`. Minimum: copy the repo-root `.env.example` to `.env`, set one provider key, and set owner credentials. Workflow execution also needs Docker daemon access plus `NEXTFLOW_BIN` or `MINIWDL_BIN` depending on the engine.

Scheduler and agent runtime defaults live in `app/config.py`; only add overrides to `.env` when local behavior really needs to differ.

## Testing

### Backend (`backend/tests/`)
- `pytest` + `pytest-asyncio`; `conftest.py` provides `async_client` (HTTPX) and `db_session` (per-test in-memory SQLite, overrides `get_db`).
- Key subdirs: `test_api/`, `test_agent/` (incl. `test_runtime/`), `test_scheduler/`, `test_services/`, `test_engine/`. Run `uv run pytest` from `backend/`.

### Frontend (`frontend/tests/`)
- Vitest + Testing Library (jsdom). Unit (`tests/unit/`), integration (`tests/integration/`), smoke (`tests/smoke/`).
- `renderAppPage` (from `tests/app-test-utils.tsx`) returns `{ ...renderResult, appTestState }`.
- Coverage: 80% enforced via `@vitest/coverage-v8`.

## Conventions

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

- The explicit async Agent Runtime is the active path — if you see `graph.py` code, that's the older compatibility fallback, not the default path.
- Frontend tests: `renderAppPage` returns per-test state — never store `appTestState` in a shared variable across tests (causes flaky failures).
- Scheduler config: 10+ env vars (`SCHEDULER_*`) — check `backend/app/config.py` lines 67-76 for all options.
- Backend test DB: each test gets its own in-memory SQLite — no shared state, no cleanup needed.
- `bif` is an HTTP-only client; start the backend or use `--base-url` / `BIOFLOW_API_URL` for non-default API targets.
- **CLI `handle_errors` and Click exceptions.** The decorator's catch-all `except Exception` would swallow `typer.BadParameter` / `click.UsageError` and downgrade them to `[UNEXPECTED]` exit-1. They are explicitly re-raised so Click can render the standard usage error with exit code 2 — keep this branch when adding new exception handling.
- Services must delegate DB queries to repositories — never use `session.execute()` directly in service code. This was enforced in the 2026-04-04 prune.
- Frontend uses Better Auth (v1.4.17) for authentication — config in `frontend/lib/auth.ts` and `auth-config.ts`.
- **Swarm nested bind mounts.** A `rw` child mount under a `ro` parent is silently demoted to `ro`. Always declare per-run mounts as siblings (`runs/{run_id}/input` + `runs/{run_id}/results`); never re-introduce a `project_root` mount alongside them.
- **miniwdl `glob()` is local-only.** Patterns must be relative to the task work dir (`/mnt/miniwdl_task_container/work`); absolute patterns like `glob("${outdir}/*.zip")` raise `EvalError: glob() pattern must be relative to task working directory`. If a script renames the declared output, restore the canonical name in the same command block (e.g. `cp ${outdir}/*_Result.zip ${outdir}/Result.zip`).
- **WDL `command { ... }` parens-in-comments.** Bash-style comments containing parentheses inside `command { }` blocks break WDL's brace-matching with cryptic "Expected one of: CNAME, RBRACE, ..." parse errors. Keep command-block comments paren-free, or switch to the `command <<< ... >>>` heredoc form (which uses `~{var}` interpolation).

## Maintenance

- **Codemap refresh:** Update `codemaps/*.md` statistics when file counts drift by >10%. The generated dates in comment headers track staleness.
- **Dead code detection:** `bun run lint:dead-code` (frontend, via knip). Backend relies on manual review during pruning.

## Compacting
When compacting, always preserve the full list of modified files and any test commands.

<!-- rtk-instructions v2 -->
# RTK (Rust Token Killer) - Token-Optimized Commands

## Golden Rule

**Always prefix commands with `rtk`**. If RTK has a dedicated filter, it uses it. If not, it passes through unchanged. This means RTK is always safe to use.

**Important**: Even in command chains with `&&`, use `rtk`:
```bash
# ❌ Wrong
git add . && git commit -m "msg" && git push

# ✅ Correct
rtk git add . && rtk git commit -m "msg" && rtk git push
```

<!-- /rtk-instructions -->
