# Docker Compose One-Liner Packaging

**Date**: 2026-04-09
**Status**: Draft

## Context

The project has reached a functional state with backend (FastAPI) and frontend (Next.js 16) working locally. The next step is packaging everything as a Docker Compose deployment so that:

1. A single `docker compose up` starts the entire platform
2. Users can deploy to real machines for testing with zero friction
3. The rebuild cycle is fast: change code → rebuild → redeploy

Currently, only the backend has a Dockerfile (`backend/Dockerfile`) and a backend-only `docker-compose.yml`. The frontend has no Docker setup. The shared Better Auth SQLite database (`better-auth.db`) between frontend and backend is the key architectural constraint.

## Architecture

Two-container setup with shared volumes:

```
┌──────────────────────────────────────────────────────────┐
│  docker compose up                                        │
│                                                           │
│  ┌──────────────┐    HTTP :8000    ┌──────────────────┐  │
│  │   frontend   │ ──────────────── │     backend      │  │
│  │  Next.js 16  │   (browser →     │    FastAPI +     │  │
│  │  port 3000   │    localhost)     │    Uvicorn       │  │
│  └──────┬───────┘                  └────────┬─────────┘  │
│         │                                    │            │
│    ┌────┴────┐                         ┌─────┴──────┐    │
│    │auth-data│ (shared better-auth.db) │  app-data  │    │
│    └────┬────┘                         │ bioinfoflow│    │
│         │                              │ .db, work- │    │
│         └──────── both mount ──────────│ flows, etc │    │
│                                        └─────┬──────┘    │
│                                              │           │
│                                   Docker socket mount    │
│                                   /var/run/docker.sock   │
└──────────────────────────────────────────────────────────┘
```

### Why two containers (not one or three)

- **Not one**: Frontend (Node.js) and backend (Python) have different runtimes, dependency chains, and build processes. A single container would require supervisord and make debugging harder.
- **Not three** (with reverse proxy): Adds complexity without value at this stage. Users access via `localhost:3000` (frontend) and `localhost:8000` (API). A reverse proxy can be added later for production with HTTPS/domain.

## Files to Create

### 1. `docker-compose.yml` (project root)

```yaml
services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "${BACKEND_PORT:-8000}:8000"
    env_file: .env
    environment:
      DATABASE_URL: sqlite+aiosqlite:////data/bioinfoflow.db
      WORKFLOW_REGISTRY_ROOT: /data/workflows
      NEXTFLOW_WORK_DIR: /data/workdirs/nextflow
      MINIWDL_WORK_DIR: /data/workdirs/miniwdl
      BETTER_AUTH_DB_PATH: /data/auth/better-auth.db
      DOCKER_SOCKET: unix:///var/run/docker.sock
    volumes:
      - auth-data:/data/auth
      - app-data:/data
      - /var/run/docker.sock:/var/run/docker.sock
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/system/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    restart: unless-stopped

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
      args:
        - NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL:-http://localhost:8000/api/v1}
        - NEXT_PUBLIC_AUTH_MODE=${AUTH_MODE:-personal}
        - NEXT_PUBLIC_AUTH_LOCAL_ENABLED=${AUTH_LOCAL_ENABLED:-true}
        - NEXT_PUBLIC_AUTH_SELF_SIGNUP_ENABLED=${AUTH_SELF_SIGNUP_ENABLED:-false}
    ports:
      - "${FRONTEND_PORT:-3000}:3000"
    env_file: .env
    environment:
      BETTER_AUTH_DB_PATH: /data/auth/better-auth.db
      BETTER_AUTH_URL: ${BETTER_AUTH_URL:-http://localhost:3000}
    volumes:
      - auth-data:/data/auth
    depends_on:
      backend:
        condition: service_healthy
    restart: unless-stopped

volumes:
  auth-data:
  app-data:
```

**Key points:**
- `env_file: .env` loads the shared env file for both services
- `environment:` block overrides container-specific paths (these should NOT be in the .env file)
- Build args inject `NEXT_PUBLIC_*` values at build time (Next.js bakes these into the JS bundle)
- Frontend depends on backend being healthy before starting
- Named volumes persist data across restarts

### 2. `backend/Dockerfile` (rewrite)

```dockerfile
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl default-jre-headless && \
    rm -rf /var/lib/apt/lists/*

# Install Nextflow
RUN curl -fsSL https://get.nextflow.io | bash && \
    mv nextflow /usr/local/bin/ && \
    chmod +x /usr/local/bin/nextflow

# Install uv
RUN pip install --no-cache-dir uv

# Install Python dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application code
COPY app app
COPY alembic alembic
COPY alembic.ini .
COPY scripts scripts

# Entrypoint runs migrations then starts server
COPY scripts/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Changes from current:**
- Removes `--reload` (production mode)
- Adds `--no-dev` to uv sync (skip test dependencies)
- Installs JRE + Nextflow (needed for workflow execution)
- Adds entrypoint script for migrations
- Doesn't copy `.env.example` as `.env` (env comes from docker-compose)

### 3. `backend/scripts/docker-entrypoint.sh` (new)

```bash
#!/bin/bash
set -e

echo "Running database migrations..."
uv run alembic upgrade head

echo "Starting Bioinfoflow backend..."
exec "$@"
```

### 4. `frontend/Dockerfile` (new)

```dockerfile
# Stage 1: Install dependencies
FROM node:22-slim AS deps
WORKDIR /app
RUN npm install -g bun
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

# Stage 2: Build
FROM node:22-slim AS builder
WORKDIR /app
RUN npm install -g bun

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build-time env vars (baked into JS bundle)
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
ARG NEXT_PUBLIC_AUTH_MODE=personal
ARG NEXT_PUBLIC_AUTH_LOCAL_ENABLED=true
ARG NEXT_PUBLIC_AUTH_SELF_SIGNUP_ENABLED=false

ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_AUTH_MODE=$NEXT_PUBLIC_AUTH_MODE
ENV NEXT_PUBLIC_AUTH_LOCAL_ENABLED=$NEXT_PUBLIC_AUTH_LOCAL_ENABLED
ENV NEXT_PUBLIC_AUTH_SELF_SIGNUP_ENABLED=$NEXT_PUBLIC_AUTH_SELF_SIGNUP_ENABLED

# Ensure better-sqlite3 native bindings match
RUN node scripts/ensure-better-sqlite3-node-abi.mjs

RUN bun run build

# Stage 3: Production
FROM node:22-slim AS runner
WORKDIR /app

ENV NODE_ENV=production

# Copy built output
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
COPY --from=builder /app/messages ./messages

# better-sqlite3 needs its native addon at runtime
COPY --from=builder /app/node_modules/better-sqlite3 ./node_modules/better-sqlite3
COPY --from=builder /app/node_modules/bindings ./node_modules/bindings
COPY --from=builder /app/node_modules/file-uri-to-path ./node_modules/file-uri-to-path

EXPOSE 3000

CMD ["node", "server.js"]
```

**Key considerations:**
- Multi-stage build minimizes image size
- `better-sqlite3` native addon needs to be built inside the container (Linux x86_64)
- Next.js `output: "standalone"` mode produces a self-contained server
- `NEXT_PUBLIC_*` vars must be available at build time (baked into client JS)
- Runtime vars like `BETTER_AUTH_DB_PATH` and `BETTER_AUTH_SECRET` are read at runtime

**Requires `next.config.mjs` change**: Add `output: "standalone"` for efficient Docker builds.

### 5. `.env.example` (project root — new)

```env
# ============================================================
# Bioinfoflow Docker Compose Configuration
# ============================================================
# Copy this file to .env and fill in your values:
#   cp .env.example .env
#
# Then start the platform:
#   docker compose up -d
# ============================================================

# ── Ports ──────────────────────────────────────────────────
FRONTEND_PORT=3000
BACKEND_PORT=8000

# ── Authentication ─────────────────────────────────────────
# Mode: "personal" (single user), "team" (multi-user), "dev" (no auth)
AUTH_MODE=personal

# First-time owner credentials (auto-created on first startup)
# Change these before first deployment!
AUTH_BOOTSTRAP_OWNER_EMAIL=admin@example.com
AUTH_BOOTSTRAP_OWNER_PASSWORD=changeme

# Secret for signing auth tokens (auto-generated if empty, but set for production)
BETTER_AUTH_SECRET=

# Self-signup: set to true to allow new users to register (team mode)
AUTH_SELF_SIGNUP_ENABLED=false

# ── AI Agent ───────────────────────────────────────────────
# At least one API key is required for the AI agent to work.
# The agent auto-selects the provider based on available keys.
ANTHROPIC_API_KEY=
# OPENAI_API_KEY=
# GEMINI_API_KEY=
# DEEPSEEK_API_KEY=

# Agent model override (optional)
# AGENT_MODEL=claude-sonnet-4-6

# ── Frontend → Backend URL ─────────────────────────────────
# This must be the URL where the browser can reach the backend.
# For local Docker: http://localhost:8000/api/v1
# For remote server: http://your-server-ip:8000/api/v1
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1

# Better Auth URL (where the frontend is accessible)
BETTER_AUTH_URL=http://localhost:3000

# ── CORS ───────────────────────────────────────────────────
CORS_ORIGINS=["http://localhost:3000"]

# ── Advanced (usually no need to change) ───────────────────
# APP_NAME=Bioinfoflow
# DEBUG=false
# RUN_SCHEDULER_MODE=persistent
# SCHEDULER_MAX_CONCURRENCY=4
```

### 6. `.dockerignore` files

**`backend/.dockerignore`:**
```
__pycache__
*.pyc
.git
.env
.env.local
*.db
data/
.ruff_cache
.pytest_cache
.venv
```

**`frontend/.dockerignore`:**
```
node_modules
.next
.git
.env
.env.local
*.db
out
coverage
```

## Files to Modify

### 7. `frontend/next.config.mjs`

Add `output: "standalone"` for Docker-friendly builds:
```js
output: "standalone",
```

### 8. `README.md` (project root)

Add a prominent Docker deployment section:

```markdown
## Quick Start (Docker)

### Prerequisites
- Docker and Docker Compose installed
- At least one AI API key (Anthropic, OpenAI, or Gemini)

### 1. Configure
```bash
cp .env.example .env
# Edit .env — set your API key and owner credentials
```

### 2. Launch
```bash
docker compose up -d
```

### 3. Access
- **UI**: http://localhost:3000
- **API**: http://localhost:8000/api/v1/docs

First login with the credentials you set in `.env` (`AUTH_BOOTSTRAP_OWNER_EMAIL` / `AUTH_BOOTSTRAP_OWNER_PASSWORD`).

### Auth Modes

| Mode | Use case | Config |
|------|----------|--------|
| `personal` | Single user, local machine | `AUTH_MODE=personal` (default) |
| `team` | Multi-user, shared server | `AUTH_MODE=team` + set `AUTH_SELF_SIGNUP_ENABLED=true` |
| `dev` | Development, no login needed | `AUTH_MODE=dev` |

### Remote Deployment

When deploying to a remote server, update these in `.env`:
```env
NEXT_PUBLIC_API_BASE_URL=http://YOUR_SERVER_IP:8000/api/v1
BETTER_AUTH_URL=http://YOUR_SERVER_IP:3000
CORS_ORIGINS=["http://YOUR_SERVER_IP:3000"]
```

### Rebuild & Redeploy
```bash
docker compose up -d --build
```

### Data Persistence
All data is stored in Docker volumes (`auth-data`, `app-data`). To reset:
```bash
docker compose down -v  # removes volumes
docker compose up -d --build
```
```

### 9. Remove old `backend/docker-compose.yml`

Delete the backend-only compose file since the root-level one replaces it.

## Onboarding Flow

1. User clones repo, runs `cp .env.example .env`
2. User sets `ANTHROPIC_API_KEY` (or another provider key)
3. User optionally changes `AUTH_BOOTSTRAP_OWNER_EMAIL` / `AUTH_BOOTSTRAP_OWNER_PASSWORD`
4. User runs `docker compose up -d`
5. Backend starts → runs alembic migrations → seeds demo workflows → starts scheduler
6. Frontend starts (after backend is healthy) → creates auth DB → bootstraps owner
7. User opens `http://localhost:3000`, logs in with bootstrap credentials
8. Clean database with demo workflows visible, ready to use

## Demo Workflows Decision

**Keep demo workflows.** They seed automatically on startup and give users something to explore. Users who can't run them simply ignore them — zero friction cost. Removing them would make the onboarding feel empty.

## Iterative Deployment Workflow

After code changes:
```bash
docker compose up -d --build    # Rebuild and restart
docker compose logs -f          # Watch logs
docker compose down             # Stop
docker compose down -v          # Full reset
```

This is the "one-liner" the user wants — `docker compose up -d --build` rebuilds from source and restarts.

## Verification Plan

1. `docker compose up --build` — both containers start without errors
2. `curl http://localhost:8000/api/v1/system/health` — backend responds
3. Open `http://localhost:3000` — frontend loads, shows login page
4. Login with bootstrap credentials — auth works through shared DB
5. Dashboard shows demo workflows — seed data present
6. `docker compose down && docker compose up -d` — data persists across restarts
7. `docker compose down -v && docker compose up -d --build` — clean reset works

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| `better-sqlite3` ABI mismatch in Docker | Node.js version pinned in Dockerfile; rebuild script runs during build |
| Next.js standalone output missing files | Copy `messages/`, `public/`, `.next/static` explicitly |
| CORS blocks frontend→backend | `CORS_ORIGINS` set in `.env`, defaults to `localhost:3000` |
| SQLite concurrent writes | Frontend writes auth DB, backend reads in read-only mode — no contention |
| `NEXT_PUBLIC_*` vars not available at runtime | Passed as build args → baked into JS bundle at build time |
| Nextflow binary large / slow to install | Cached in Docker layer; only re-downloaded on base image change |
