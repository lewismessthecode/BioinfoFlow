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

For local Docker, leave `BIOINFOFLOW_HOME` unset unless you want the data root outside this repo. Then set at least:

```env
AUTH_BOOTSTRAP_OWNER_EMAIL=admin@example.com
AUTH_BOOTSTRAP_OWNER_PASSWORD=change-me
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
BETTER_AUTH_URL=http://localhost:3000
```

After first sign-in, configure the agent under **Settings -> AI Providers**. Hosted providers only need an API key; Ollama, vLLM, OpenRouter, and generic OpenAI-compatible endpoints can be configured from the same page. Environment variables such as `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `VLLM_BASE_URL`, `VLLM_API_KEY`, and `VLLM_MODEL` are optional bootstrap defaults for fresh/headless deployments, and UI-saved configuration takes precedence.

For localhost Docker, `BETTER_AUTH_SECRET` may stay empty. Bioinfoflow creates a persistent local secret under `BIOINFOFLOW_HOME/state/auth` on first startup. For shared or remote deployments, generate one with `openssl rand -base64 32` and set `BETTER_AUTH_SECRET` explicitly.

Optional data-root override:

```env
BIOINFOFLOW_HOME=/absolute/path/to/bioinfoflow-data
```

For any shared or production deployment, also set:

```env
TRUSTED_HOSTS=["localhost","127.0.0.1","YOUR_SERVER_IP_OR_DOMAIN"]
```

## 2. Fastest Path: Docker

### Prerequisites

- Docker Desktop or Docker Engine with Compose
- An LLM provider key for agent use. You can provide it in **Settings -> AI Providers** after sign-in, or bootstrap one with environment variables such as `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`, or the `VLLM_*` variables.

### First run

```bash
cp .env.example .env
# edit .env: owner credentials; provider keys can be added in the UI
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
- If you leave `BIOINFOFLOW_HOME` unset, Docker Compose defaults to this repo's `data/` directory.
- The backend creates the required platform subdirectories on startup.
- GPU detection is automatic only after the host GPU has been exposed into the backend container. Bioinfoflow will not enable Docker GPU passthrough on its own.

### Optional GPU enablement

Keep the base stack CPU-safe by default. On a GPU host, opt in with the compose override:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

For published images:

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml pull
docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml up -d
```

What this does:

- requests `gpus: all` for the backend container
- exposes NVIDIA utility/compute capabilities so readiness checks can see `nvidia-smi`
- keeps CPU-only hosts working because the override is never loaded unless you ask for it

What it does not do:

- it does not manufacture GPU access if the host lacks the NVIDIA Container Toolkit
- it does not make GPU a required readiness item
- it does not change your workflow routing unless the host runtime is genuinely available

If the server has NVIDIA GPUs but the readiness drawer still says the backend cannot see them, verify:

- `nvidia-smi` works on the host
- Docker has the NVIDIA runtime / toolkit installed
- you started Compose with `-f docker-compose.gpu.yml`
- you rebuilt or restarted the backend container after enabling the override

### Fast localhost run with published images

Use this path when you want to try the latest `main` release without building images locally:

```bash
cp .env.example .env
# edit .env: owner credentials; provider keys can be added in the UI
cat >> .env <<'EOF'
IMAGE_REGISTRY=ghcr.io/lewismessthecode
IMAGE_TAG=latest
EOF
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

The images are published by `.github/workflows/container-release.yml` after `main` receives backend or frontend code changes. The stack uses:

- `ghcr.io/lewismessthecode/bioinfoflow-backend:<tag>`
- `ghcr.io/lewismessthecode/bioinfoflow-frontend:<tag>`

Available tags are `latest`, `main`, and `sha-<12-char-commit>`.

The published frontend image is built with `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1`, so it is intended for localhost. For a shared or remote server, set the public URL values in `.env` and run the source-build command instead:

```bash
docker compose up -d --build
```

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
uv run uvicorn app.main:app --reload --reload-dir app --port 8000
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
uv run bif --version                   # bif 0.1.0
uv run bif --help                      # also -h
uv run bif doctor                      # backend + scheduler + GPU + local tool checks
uv run bif config init                 # write ~/.config/bioinfoflow/cli.toml
uv run bif config use-project proj-1   # set default project (also $BIOFLOW_PROJECT)
uv run bif config set base_url http://localhost:8000/api/v1
uv run bif --output json project list  # machine-readable envelope on stdout
```

`bif` follows POSIX conventions: `-h/--help`, `-V/--version`, `-p/--project`, `-q/--quiet`. Settings resolve as CLI flag → env (`BIOFLOW_*`) → `~/.config/bioinfoflow/cli.toml` → default. Destructive commands (`run cancel`, `run cleanup`, `run batch cancel`, `project delete`, `file rm`) confirm interactively unless you pass `--force/-f`. Exit codes: `0` ok, `1` general, `2` usage, `3` backend, `4` connection.

## 4. Minimal Local Setup Checklist

For the smallest working local setup:

1. Copy `.env.example` to `.env`
2. Set owner credentials and, optionally, one LLM API key
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
cd backend && uv run uvicorn app.main:app --reload --reload-dir app --port 8000
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
