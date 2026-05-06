# Docker Quick Start

This page describes the Docker Compose startup path implemented by `docker-compose.yml`, `backend/app/config.py`, `backend/app/main.py`, `backend/app/path_layout.py`, `backend/scripts/docker-entrypoint.sh`, and `frontend/lib/auth.ts`.

## Prerequisites

- Docker Engine or Docker Desktop with Compose
- One AI provider key, such as `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, or `DEEPSEEK_API_KEY`

## First Run

From the repo root:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Optional for local Docker.
# If unset, Docker Compose uses this repo's ./data directory.
# BIOINFOFLOW_HOME=/absolute/path/to/bioinfoflow-data

ANTHROPIC_API_KEY=...
# OPENAI_API_KEY=...
# GEMINI_API_KEY=...
# DEEPSEEK_API_KEY=...

AUTH_BOOTSTRAP_OWNER_EMAIL=admin@example.com
AUTH_BOOTSTRAP_OWNER_PASSWORD=change-me

# Optional for localhost Docker. If empty, Bioinfoflow creates a persistent
# local secret under BIOINFOFLOW_HOME/state/auth on first startup.
# Set this before running a shared or remote deployment.
# BETTER_AUTH_SECRET=...
```

Start the stack:

```bash
docker compose up -d --build
```

Open:

- UI: `http://localhost:3000`
- API docs: `http://localhost:8000/api/v1/docs`

Sign in with the owner email and password from `.env`.

## What Happens At Startup

If `BIOINFOFLOW_HOME` is unset, Compose uses `${PWD}/data`, where `${PWD}` is the repo root for normal local startup.

Compose passes these important values to the backend:

- `BIOINFOFLOW_HOME=${BIOINFOFLOW_HOME:-${PWD}/data}`
- `BIOINFOFLOW_HOME_HOST=${BIOINFOFLOW_HOME:-${PWD}/data}`
- `DATABASE_URL=sqlite+aiosqlite:///${BIOINFOFLOW_HOME:-${PWD}/data}/state/bioinfoflow.db`
- `BETTER_AUTH_DB_PATH=${BIOINFOFLOW_HOME:-${PWD}/data}/state/auth/better-auth.db`

The backend enforces Path Contract v3: when `BIOINFOFLOW_HOME_HOST` is set, it must resolve to the same absolute path as `BIOINFOFLOW_HOME`.

The backend creates platform directories on startup through `ensure_platform_layout()`:

```text
BIOINFOFLOW_HOME/
  state/
    auth/
    workflows/
    engine/cache/nextflow/
    engine/cache/miniwdl/
  projects/
  sources/
    deliveries/
    reference/
    database/
```

The backend container entrypoint also creates the core state, workflow, project, and engine-cache directories before migrations run. The frontend auth layer creates the Better Auth database parent directory before opening the SQLite database.

For the standard local quick start, you do not need to run `mkdir` before `docker compose up`.

## Choosing `BIOINFOFLOW_HOME`

Leave `BIOINFOFLOW_HOME` unset for the repo-local default:

```text
<repo>/data
```

Set it only when you want platform data somewhere else:

```env
BIOINFOFLOW_HOME=/Users/<you>/bioinfoflow-data
BIOINFOFLOW_HOME=/srv/bioinfoflow
BIOINFOFLOW_HOME=/lustre/<you>/bioinfoflow
```

Use an absolute path. Docker Compose bind-mounts that path to the same path inside the containers:

```yaml
- ${BIOINFOFLOW_HOME:-${PWD}/data}:${BIOINFOFLOW_HOME:-${PWD}/data}
```

That identity mount lets the backend, workflow runner, and task containers use the same absolute FASTQ, BAM, VCF, reference, and output paths without host/container translation.

## Local Versus Shared Servers

Local defaults in `.env.example` are already set for:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
BETTER_AUTH_URL=http://localhost:3000
CORS_ORIGINS=["http://localhost:3000"]
AUTH_MODE=personal
```

For a shared or remote server, set these before building:

```env
NEXT_PUBLIC_API_BASE_URL=http://YOUR_SERVER:8000/api/v1
BETTER_AUTH_URL=http://YOUR_SERVER:3000
CORS_ORIGINS=["http://YOUR_SERVER:3000"]
TRUSTED_HOSTS=["localhost","127.0.0.1","YOUR_SERVER"]
```

`NEXT_PUBLIC_*` values are baked into the frontend image at build time. After changing them, rebuild:

```bash
docker compose up -d --build
```

## Working With Input Files

You only need to create subdirectories manually when you want to place data there yourself. For example:

```bash
mkdir -p data/sources/deliveries/hg002
mkdir -p data/sources/reference/hg38

cp /path/to/HG002_R1.fastq.gz data/sources/deliveries/hg002/
cp /path/to/HG002_R2.fastq.gz data/sources/deliveries/hg002/
cp /path/to/hg38.fa* data/sources/reference/hg38/
```

Then choose those files from Deliveries and Reference Library in the run wizard.

## Logs And Health Checks

```bash
docker compose logs -f backend frontend
```

Useful URLs:

- `http://localhost:8000/api/v1/system/health`
- `http://localhost:8000/api/v1/scheduler/status`
- `http://localhost:8000/api/v1/docs`
