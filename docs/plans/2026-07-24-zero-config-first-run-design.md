# Zero-Configuration First Run Design

## Problem

Bioinfoflow currently documents local setup as a sequence that still requires
users to understand and edit authentication credentials, URLs, and provider
keys before they can see a working application. A fresh backend checkout also
fails at `uv run alembic upgrade head` because SQLite cannot create a database
inside the missing `data/state/` directory.

These are first-run contract failures. A local quick start should work from
repository defaults, while shared and remote deployments should require the
operator to opt into their wider security boundary explicitly.

## First-Principles Constraints

1. A local first run must not require values the application can derive.
2. A missing third-party API key must disable model-backed actions, not prevent
   the application from starting; users can add a provider through the UI.
3. Passwordless development mode is acceptable only behind a localhost network
   boundary by default.
4. Shared and remote deployments must continue to require explicit auth,
   secrets, origins, hosts, and public URLs.
5. Database initialization owns creation of the filesystem path needed to open
   its SQLite database. It must not depend on the web server having started.
6. Existing explicit environment values remain authoritative.

## Considered Approaches

### 1. Interactive setup wizard

Generate `.env`, credentials, URLs, and directories through a new command. This
can guide remote deployment well, but adds a new stateful setup subsystem and a
new command users must discover. It does not make the familiar `docker compose
up` or `uv run alembic upgrade head` commands self-sufficient.

### 2. Generate local credentials automatically

Keep personal auth as the default and generate an owner password. This avoids
manual secret creation but creates a credential-discovery and recovery problem.
It also adds authentication ceremony to a loopback-only development instance.

### 3. Secure local defaults with explicit production opt-in (selected)

Default source development and source Compose to dev auth, bind local services
to `127.0.0.1`, make `.env` optional, and defer provider setup to the UI. Keep
explicit environment overrides and document personal/team configuration for
shared deployments. This is the smallest design because it removes required
state instead of generating more state.

## Design

### SQLite migration readiness

Add a focused database helper that recognizes file-backed SQLite URLs and
creates the database parent directory. Alembic calls it immediately before
creating its engine. Non-SQLite URLs, in-memory SQLite URLs, and SQLite URI
filenames are left untouched.

The regression test runs Alembic against a nonexistent temporary
`BIOINFOFLOW_HOME` and asserts that the migration succeeds and creates
`state/bioinfoflow.db`.

### Backend local defaults

With no environment file and no legacy auth override, backend settings resolve
to `AUTH_MODE=dev`. Explicit `AUTH_MODE=personal|team|dev` and legacy
`AUTH_ENABLED` continue to work. The documented Uvicorn development command
uses Uvicorn's loopback default.

### Frontend local defaults

When neither the modern nor legacy auth variables are present, frontend auth
configuration resolves to dev mode. Explicit values remain authoritative.
`bun run dev` injects `--hostname 127.0.0.1` unless the caller explicitly
provides a hostname, keeping passwordless development loopback-only. A direct
frontend image build also defaults its baked auth mode to dev; release builds
that explicitly request personal or dev mode remain unchanged.

### Source Docker Compose defaults

The source Compose stack:

- treats `.env` as an optional override file;
- supplies `AUTH_MODE=dev` to the backend and frontend by default;
- bakes `NEXT_PUBLIC_AUTH_MODE=dev` into the frontend by default;
- publishes frontend and backend ports on `127.0.0.1` only;
- retains explicit substitutions for custom ports, paths, URLs, auth modes,
  provider configuration, and other operator overrides.

`.env.example` becomes an optional customization template. Bootstrap owner
credentials are commented examples used only after switching to personal or
team mode. Provider keys are also optional because provider setup is UI-first.

### Remote and shared deployments

Documentation clearly separates zero-config localhost usage from shared or
remote deployment. Before widening a bind address or using a reverse proxy, an
operator must explicitly configure personal/team auth, owner credentials,
stable secrets, browser/API URLs, CORS origins, and trusted hosts.

No attempt is made to infer public deployment URLs or manufacture third-party
provider credentials.

## Verification

- Alembic fresh-home subprocess regression test.
- Backend auth-default unit tests, including explicit and legacy overrides.
- Frontend auth-default and development-host argument unit tests.
- Compose structure tests for optional `.env`, dev auth, and loopback ports.
- `docker compose config` without a repository `.env`.
- Backend pytest and Ruff checks.
- Frontend lint, tests, i18n lint, and dead-code lint where affected.
- Markdown diff check and `git diff --check`.
