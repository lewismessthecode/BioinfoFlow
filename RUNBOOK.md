# Bioinfoflow Runbook

This is the canonical runbook for v0.1.0.

If you only remember one rule, remember this:

> Edit the repo-root `.env`. That is the default config source for Docker and local development.

## 1. Environment Variables: One Rule, Not Three

### Default

Use exactly one file by default:

```bash
cp .env.example .env
```

Then edit `.env`.

### Optional overrides

These files are now optional escape hatches, not required setup steps:

- `backend/.env`
  Use only when one machine needs backend-only overrides such as local runner paths.
- `frontend/.env.local`
  Use only when one machine needs frontend-only overrides.

### Precedence

The effective order is:

1. Shell-exported environment variables
2. Package-local override file
   `backend/.env` for backend commands
   `frontend/.env.local` for frontend commands
3. Repo-root `.env`
4. Code defaults

### What most users should do

Do not create extra env files unless you have a specific reason.

For almost everyone, this is enough:

```bash
cp .env.example .env
```

Then set at least:

```env
ANTHROPIC_API_KEY=...
AUTH_BOOTSTRAP_OWNER_EMAIL=admin@example.com
AUTH_BOOTSTRAP_OWNER_PASSWORD=change-me
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
BETTER_AUTH_URL=http://localhost:3000
```

For any shared or production deployment, also set:

```env
BETTER_AUTH_SECRET=<long-random-secret>
TRUSTED_HOSTS=["localhost","127.0.0.1","YOUR_SERVER_IP_OR_DOMAIN"]
```

## 2. Fastest Path: Docker

### Prerequisites

- Docker Desktop or Docker Engine with Compose
- At least one LLM provider key:
  - `ANTHROPIC_API_KEY`
  - or `OPENAI_API_KEY`
  - or `GEMINI_API_KEY`

### First run

```bash
cp .env.example .env
mkdir -p data/state data/projects data/sources/deliveries data/sources/reference
docker compose up -d --build
```

Open:

- UI: `http://localhost:3000`
- API docs: `http://localhost:8000/api/v1/docs`

Sign in with:

- `AUTH_BOOTSTRAP_OWNER_EMAIL`
- `AUTH_BOOTSTRAP_OWNER_PASSWORD`

### Docker notes

- `NEXT_PUBLIC_API_BASE_URL` is baked into the frontend at build time.
- If you change any `NEXT_PUBLIC_*` value, rebuild:

```bash
docker compose up -d --build
```

- `BIOINFOFLOW_HOME` is identity-mounted into the same absolute path on host and in containers.
- If you do nothing, Docker defaults to `/srv/bioinfoflow`.

## 3. Local Development

### Prerequisites

- Python 3.13+
- `uv`
- Bun
- Docker daemon if you want Docker-backed workflow execution
- Nextflow installed if you want Nextflow runs
- MiniWDL installed if you want WDL runs

### Backend

The backend now auto-reads the repo-root `.env`.

```bash
cp .env.example .env
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

If this machine has runner paths that should not live in the shared `.env`, create `backend/.env` and only put overrides there:

```env
NEXTFLOW_BIN=/absolute/path/to/nextflow
MINIWDL_BIN=/absolute/path/to/miniwdl
```

### Frontend

The frontend now auto-loads the repo-root `.env` too.

```bash
cd frontend
bun install
bun run dev
```

Open:

- UI: `http://localhost:3000`

If you truly need a frontend-only override, create `frontend/.env.local`.

### CLI

```bash
cd backend
uv run bif --help
```

## 4. Minimal Local Setup Checklist

For the smallest working local setup:

1. Copy `.env.example` to `.env`
2. Set one LLM API key
3. Run backend migrations
4. Start backend
5. Start frontend

Commands:

```bash
cp .env.example .env

cd backend
uv sync
uv run alembic upgrade head

cd ../frontend
bun install
```

Then in two terminals:

```bash
cd backend && uv run uvicorn app.main:app --reload --port 8000
cd frontend && bun run dev
```

## 5. Common Friction Points

### Frontend cannot reach backend

Check:

- `.env` contains `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1`
- the backend is actually listening on port `8000`
- if you changed `NEXT_PUBLIC_*`, you restarted `bun run dev` or rebuilt Docker

### Login or callback origin errors

Check:

- `BETTER_AUTH_URL` matches the browser origin exactly
- `CORS_ORIGINS` includes the frontend URL
- `TRUSTED_HOSTS` includes the backend hostname or IP you are using

Typical local values:

```env
BETTER_AUTH_URL=http://localhost:3000
CORS_ORIGINS=["http://localhost:3000"]
TRUSTED_HOSTS=["localhost","127.0.0.1"]
```

### Schema drift or SQLite errors on backend startup

Run:

```bash
cd backend
uv run alembic current
uv run alembic upgrade head
```

### Run submission fails before queueing

Check:

- `NEXTFLOW_BIN` exists if you are running Nextflow workflows
- `MINIWDL_BIN` exists if you are running WDL workflows
- Docker daemon is available when the workflow path requires it

### Docker deployment works locally but not on a server

Most common cause:

- frontend was built with the wrong `NEXT_PUBLIC_API_BASE_URL`

Before remote builds, set:

```bash
export NEXT_PUBLIC_API_BASE_URL=http://YOUR_SERVER_IP:8000/api/v1
```

## 6. Useful Health Checks

- `http://localhost:8000/api/v1/docs`
- `http://localhost:8000/api/v1/openapi.json`
- `GET /api/v1/system/health`
- `GET /api/v1/scheduler/status`
- `GET /api/v1/scheduler/resources`

## 7. File Map

- `README.md`
  Product overview and high-level positioning
- `RUNBOOK.md`
  Canonical setup and troubleshooting guide
- `backend/README.md`
  Backend-focused notes
