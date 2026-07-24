# Zero-Configuration First Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make fresh local Docker Compose and source-development starts work without editing environment variables, while preserving explicit secure configuration for shared deployments.

**Architecture:** Put filesystem preparation at the SQLite connection boundary, align backend and frontend absent-configuration auth defaults to dev mode, and enforce the matching localhost network boundary in development launchers and Compose. Keep `.env` as an optional override surface rather than required generated state.

**Tech Stack:** Python 3.13, FastAPI settings, SQLAlchemy/Alembic, pytest, Next.js 16, TypeScript, Vitest, Docker Compose, Markdown.

---

### Task 1: Reproduce and fix fresh SQLite migration setup

**Files:**
- Modify: `backend/app/database.py`
- Modify: `backend/alembic/env.py`
- Create: `backend/tests/test_migrations/test_fresh_sqlite_setup.py`

- [ ] **Step 1: Write the failing subprocess regression test**

Create a test that sets `BIOINFOFLOW_HOME` to a nonexistent temporary path,
removes `DATABASE_URL`, runs `python -m alembic upgrade head` from `backend/`,
and expects exit code zero plus `<home>/state/bioinfoflow.db` to exist.

- [ ] **Step 2: Run the regression test and verify RED**

Run: `rtk uv run pytest tests/test_migrations/test_fresh_sqlite_setup.py -v`

Expected: FAIL with `sqlite3.OperationalError: unable to open database file`.

- [ ] **Step 3: Add the minimal database-path helper**

Add `ensure_sqlite_database_parent(database_url: str) -> None` in
`app/database.py`. Parse the URL with SQLAlchemy's `make_url`; return for
non-SQLite dialects, empty or `:memory:` databases, and `file:` URI databases;
otherwise create `Path(url.database).expanduser().resolve().parent` with
`parents=True, exist_ok=True`.

Call the helper from `alembic/env.py` before `async_engine_from_config`.

- [ ] **Step 4: Run the regression test and database tests to verify GREEN**

Run: `rtk uv run pytest tests/test_migrations/test_fresh_sqlite_setup.py tests/test_database_schema.py -v`

Expected: all tests pass.

### Task 2: Make absent backend configuration a local dev configuration

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/tests/test_auth/test_config_defaults.py`

- [ ] **Step 1: Change the existing default-auth test to require dev mode**

With `AUTH_MODE` and `AUTH_ENABLED` removed and `_env_file=None`, assert
`resolved_auth_mode == "dev"` and `auth_enabled_effective is False`. Retain
tests showing `AUTH_ENABLED=true` maps to personal and explicit modes win.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `rtk uv run pytest tests/test_auth/test_config_defaults.py -v`

Expected: the no-environment default assertion fails because it is personal.

- [ ] **Step 3: Implement the minimal backend default**

Change the legacy `auth_enabled` default to false so the existing
`resolved_auth_mode` compatibility path resolves absent configuration to dev.
Do not change explicit mode precedence.

- [ ] **Step 4: Run focused config tests and verify GREEN**

Run: `rtk uv run pytest tests/test_auth/test_config_defaults.py tests/test_config_env_loading.py -v`

Expected: all tests pass.

### Task 3: Align frontend auth and loopback development defaults

**Files:**
- Modify: `frontend/lib/auth-config.ts`
- Modify: `frontend/scripts/with-root-env.mjs`
- Modify: `frontend/tests/unit/auth-config.test.ts`
- Modify: `frontend/tests/unit/middleware.test.ts`
- Modify: `frontend/tests/unit/scripts/with-root-env.test.ts`

- [ ] **Step 1: Write failing frontend default tests**

Assert that no auth variables resolve server and client configuration to dev
mode. Add tests for a small exported argument helper that appends
`--hostname 127.0.0.1` for `dev` only when neither `--hostname` nor `-H` is
present, and preserves an explicit hostname.

- [ ] **Step 2: Run focused Vitest tests and verify RED**

Run: `rtk bun run test -- tests/unit/auth-config.test.ts tests/unit/scripts/with-root-env.test.ts`

Expected: default auth remains personal and the argument helper is missing.

- [ ] **Step 3: Implement the minimal frontend defaults**

Change the fallback passed to `parseBoolean` in `resolveAuthMode` from true to
false. Add `withLocalDevDefaults(command, args)` and use its returned arguments
for both startup reporting and the spawned Next.js process.

- [ ] **Step 4: Run focused Vitest tests and verify GREEN**

Run: `rtk bun run test -- tests/unit/auth-config.test.ts tests/unit/scripts/with-root-env.test.ts`

Expected: all focused tests pass.

### Task 4: Make source Compose zero-configuration and loopback-only

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `frontend/Dockerfile`
- Create: `backend/tests/test_local_first_run.py`

- [ ] **Step 1: Write failing Compose contract tests**

Parse `docker-compose.yml` and assert both `env_file` entries use
`path: .env` with `required: false`, both published ports begin with
`127.0.0.1:`, backend and frontend runtime environments default
`AUTH_MODE` to dev, and the frontend build arg defaults
`NEXT_PUBLIC_AUTH_MODE` to dev.
Also assert that a direct frontend image build defaults its auth build argument
to dev when no explicit argument is supplied.

- [ ] **Step 2: Run the contract test and verify RED**

Run: `rtk uv run pytest tests/test_local_first_run.py -v`

Expected: assertions fail against required `.env`, public binds, and personal
auth defaults.

- [ ] **Step 3: Implement the minimal Compose and template changes**

Use Compose's optional long-form `env_file`, add explicit dev auth fallbacks,
and bind ports to loopback. Rewrite `.env.example` setup comments so copying is
optional, set its local customization default to dev, and comment bootstrap
credentials and provider keys that are not required for first start.

- [ ] **Step 4: Verify Compose and focused tests**

Run: `rtk docker compose config`

Expected: exit zero with no repository `.env`, loopback port bindings, and dev
auth in the rendered configuration.

Run: `rtk uv run pytest tests/test_local_first_run.py tests/test_voice_deployment.py -v`

Expected: all tests pass.

### Task 5: Document one-command local starts and explicit remote security

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `RUNBOOK.md`
- Modify: `backend/README.md`
- Modify: `docs/getting-started/docker.md`

- [ ] **Step 1: Update local Docker instructions**

Document `docker compose up -d --build` immediately after clone, with `.env`
copying shown only as an optional customization step.

- [ ] **Step 2: Update source development instructions**

Document backend migration/Uvicorn and frontend `bun run dev` commands as
working without `.env`, explain UI-first provider setup, and state that local
defaults are loopback-only dev auth.

- [ ] **Step 3: Preserve the explicit shared-deployment checklist**

List the required personal/team auth mode, owner credentials, stable auth and
credential secrets, public frontend/backend URLs, CORS origins, trusted hosts,
and widened bind/reverse-proxy configuration.

- [ ] **Step 4: Check documentation formatting**

Run: `rtk git diff --check`

Expected: exit zero.

### Task 6: Full verification, review, and publication

**Files:**
- Review every changed file listed above.

- [ ] **Step 1: Run backend verification**

Run from `backend/`: `rtk uv run pytest` and `rtk uv run ruff check .`.

Expected: all tests pass and Ruff reports no errors.

- [ ] **Step 2: Run frontend verification**

Run from `frontend/`: `rtk bun run lint`, `rtk bun run test`,
`rtk bun run lint:i18n`, and `rtk bun run lint:dead-code`.

Expected: all commands exit zero.

- [ ] **Step 3: Review the diff against this plan**

Inspect `git diff --check`, `git status --short`, and the complete diff. Request
a focused code review against `origin/main`, address every critical or important
finding, and rerun affected verification.

- [ ] **Step 4: Commit, push, and open the PR**

Use Conventional Commit and PR title `fix: remove local first-run configuration friction`.
Push `codex/zero-config-first-run` and open a ready-for-review PR describing the
root cause, security boundary, user impact, and verification evidence.
