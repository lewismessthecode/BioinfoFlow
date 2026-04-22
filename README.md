# Bioinfoflow

> Like Cursor, but for running bioinformatics pipelines. Locally.

<p align="center">
  <img src="docs/assets/demo.gif" alt="Bioinfoflow Demo" width="800">
  <br>
  <em>Agent-guided local pipeline orchestration in Bioinfoflow.</em>
</p>

Chat with an AI agent to build, configure, execute bioinformatics pipelines and shows you the results — all on your own machine. No cloud vendor lock-in. Your data stays local.

## Start Here

- Setup and troubleshooting: [`RUNBOOK.md`](RUNBOOK.md)
- Backend architecture: [`docs/backend/overview.md`](docs/backend/overview.md)
- Frontend architecture: [`docs/frontend/overview.md`](docs/frontend/overview.md)

## Try It

```bash
cp .env.example .env          # set your API key
docker compose up -d --build  # start everything
# → open http://localhost:3000
```

## What Just Happened

- A **FastAPI backend** spun up with workflow engines (Nextflow + WDL) and a persistent run scheduler
- An **AI agent** is ready to help you design, configure, and execute bioinformatics pipelines
- A **Next.js dashboard** lets you manage runs, visualize DAGs in real-time, and chat with the agent

---

## Quick Start (Docker)

### Prerequisites
- [Docker](https://docs.docker.com/get-docker/) and Docker Compose installed
- At least one AI API key (Anthropic, OpenAI, or Gemini)

### 1. Configure
```bash
cp .env.example .env
# Edit .env — set your API key and owner credentials
mkdir -p data/state data/projects data/sources/deliveries data/sources/reference
```

### 2. Launch
```bash
docker compose up -d
```

### 3. Access
- **UI**: http://localhost:3000
- **API Docs**: http://localhost:8000/api/v1/docs

Log in with the credentials you set in `.env` (`AUTH_BOOTSTRAP_OWNER_EMAIL` / `AUTH_BOOTSTRAP_OWNER_PASSWORD`).

### Storage Layout

Docker Compose mounts host folders into canonical in-container locations so end users never need to type container paths:

- `./data/projects` → `/data/projects`
- `./data/sources/deliveries` → `/data/sources/deliveries`
- `./data/sources/reference` → `/data/sources/reference`

Typical flow:

- Create a project in the UI. Bioinfoflow provisions its managed root automatically.
- Upload project-private manifests or small helper files into `Project Data` from the UI.
- Copy upstream FASTQ/BAM/VCF deliveries into `./data/sources/deliveries`.
- Place team-wide references and indexes in `./data/sources/reference`.
- Choose inputs from `Deliveries` or `Reference Library` inside the run wizard instead of browsing other project folders.

### How To Pass Inputs

This is the intended user model after the storage redesign:

- `Project Data`: project-private small files, manifests, helper TSV/CSV/list files, and run outputs.
- `Deliveries`: upstream-delivered raw data such as `fq`, `bam`, `vcf`.
- `Reference Library`: reference FASTA, indexes, BED/GTF, and other reusable references.

Normal users should not guess or type the real project directory path. In the UI they only work with:

- `Project Data`
- `Deliveries`
- `Reference Library`

#### If you already have FASTQ/BAM/VCF on the server

Copy them into the Deliveries folder on the host:

```bash
mkdir -p data/sources/deliveries/run42
cp /path/from/upstream/*.fastq.gz data/sources/deliveries/run42/
```

Then in the run wizard:

- open the file browser
- switch to `Deliveries`
- choose the files from there

#### If your workflow needs a manifest such as `sequence.list`

Use `Project Data` for the manifest file itself.

Recommended flow:

1. Put raw `fq/bam/vcf` files in `Deliveries`
2. Create `sequence.list` in `Project Data`
3. Point the manifest entries at `asset://deliveries/...` files, or use paths relative to the manifest file itself such as `fq/sample_R1.fastq.gz`
4. In the run wizard, use the `sequence_list` file picker to select that manifest file
5. Submit the run

At submission time Bioinfoflow rewrites the manifest into runtime-visible absolute paths automatically. Users do not need to write `/data/...` paths by hand.

#### Manifest-backed WDL example

Suppose the host has:

```text
data/sources/deliveries/deaf20-run/
  S1_R1.fastq.gz
  S1_R2.fastq.gz
```

In a WDL run wizard that expects a `sequence_list` manifest:

- keep `sequence_list` as a file input
- select a `sequence.list` file from `Project Data`
- the file can contain lines such as:

```text
sample_a	asset://deliveries/deaf20-run/S1_R1.fastq.gz
sample_b	asset://deliveries/deaf20-run/S1_R2.fastq.gz
```

- submit

The saved manifest lives in the current project's private storage, while the large upstream data stays in `Deliveries`.

### Local Dev vs Docker Compose

The storage model is the same in both modes. Only the physical base path differs:

- local dev backend: defaults to repo-relative paths such as `./data/projects` and `./data/sources/deliveries`
- Docker Compose: mounts those host directories into `/data/projects`, `/data/sources/deliveries`, and `/data/sources/reference` inside the container

Because the backend resolves asset references server-side, the user-facing UX stays the same in both modes.

### Auth Modes

| Mode | Use case | Config |
|------|----------|--------|
| `personal` | Single user, local machine | `AUTH_MODE=personal` (default) |
| `team` | Multi-user, shared server | `AUTH_MODE=team`, set `AUTH_SELF_SIGNUP_ENABLED=true` |
| `dev` | Development, no login needed | `AUTH_MODE=dev` |

### Remote Deployment

Deploy to a remote Linux server **without putting source code on it**. The `deploy.sh` script supports two release styles:

1. **Offline sync** — build locally, copy Docker images to the server, and start them there.
2. **GHCR release** — publish images to GitHub Container Registry, then have servers pull them.

#### Architecture note

If you build on a MacBook, the target Linux server architecture matters:

- `amd64` = standard x86_64 Linux cloud servers (most common)
- `arm64` = ARM Linux servers

The deploy script defaults to `--arch amd64` for single-architecture commands. Use `--arch arm64` only when the target server is ARM.

#### First time server setup

```bash
# 1. Copy compose file + env template to the server
./deploy.sh setup user@your-server

# 2. SSH in and configure .env (API keys, server URLs, auth)
ssh user@your-server
cd ~/bioinfoflow
vim .env
```

Update these values in `.env` (replace `YOUR_SERVER_IP` and ports as needed):

```env
# AI provider (at least one required)
ANTHROPIC_API_KEY=sk-ant-...

# Auth credentials for the first admin user
AUTH_BOOTSTRAP_OWNER_EMAIL=admin@example.com
AUTH_BOOTSTRAP_OWNER_PASSWORD=<strong-password>
BETTER_AUTH_SECRET=<long-random-secret>

# URLs — must point to the server's public IP/domain
NEXT_PUBLIC_API_BASE_URL=http://YOUR_SERVER_IP:8000/api/v1
BETTER_AUTH_URL=http://YOUR_SERVER_IP:FRONTEND_PORT
CORS_ORIGINS=["http://YOUR_SERVER_IP:FRONTEND_PORT"]
CORS_ORIGIN_REGEX=^https?://(localhost|127\.0\.0\.1|YOUR_SERVER_IP)(:\d+)?$
TRUSTED_HOSTS=["localhost","127.0.0.1","YOUR_SERVER_IP"]

# Better Auth validates request origins against BETTER_AUTH_URL.
# This must exactly match the browser origin (scheme + host + port),
# or login will fail with: Invalid origin
# TRUSTED_HOSTS must include the backend hostnames/IPs the browser or proxy uses,
# or the backend will reject the request with "Invalid host header".

# Ports (defaults: backend=8000, frontend=3000)
FRONTEND_PORT=3000
BACKEND_PORT=8000
```

> **Common pitfall:** `NEXT_PUBLIC_API_BASE_URL` is baked into the frontend JS at **build time**. If the frontend was built with `localhost`, the user's browser will try to call `localhost:8000` — which doesn't exist on their machine. You must set this env var **before building** (see below). `CORS_ORIGINS` must also include the frontend's public URL, otherwise the browser blocks all API requests.

#### Offline deployment (build on Mac, transfer to server)

```bash
# Set the server's public API URL for the frontend build
export NEXT_PUBLIC_API_BASE_URL=http://YOUR_SERVER_IP:8000/api/v1

# Deploy to a regular x86_64 Linux server
./deploy.sh sync --arch amd64 user@your-server

# Deploy to an ARM64 Linux server
./deploy.sh sync --arch arm64 user@your-server
```

This builds images locally with Docker Buildx, compresses them, transfers them via SCP, loads them on the server, and starts the services. No source code is copied — only Docker images.

**After code changes, just repeat** (keep `NEXT_PUBLIC_API_BASE_URL` set):
```bash
NEXT_PUBLIC_API_BASE_URL=http://YOUR_SERVER_IP:8000/api/v1 ./deploy.sh sync --arch amd64 user@your-server
```

#### GHCR setup (GitHub Container Registry)

Create a GitHub Personal Access Token (classic) with at least:

- `write:packages`
- `read:packages`
- optional: `delete:packages`

Log in locally before push/release:

```bash
export GHCR_USER=your-github-user-or-org
export GHCR_TOKEN=your-github-token

echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin
```

If the GHCR package stays private, log in on the server too before `docker compose pull`.

#### Single-architecture GHCR push

```bash
GHCR_USER=your-github-user IMAGE_TAG=v0.1.0 ./deploy.sh push --arch amd64
```

This pushes architecture-specific tags such as:

- `ghcr.io/<GHCR_USER>/bioinfoflow-backend:v0.1.0-amd64`
- `ghcr.io/<GHCR_USER>/bioinfoflow-frontend:v0.1.0-amd64`

If you deploy those single-architecture GHCR images with `docker compose pull`, set the matching suffix on the server too:

```env
IMAGE_REGISTRY=ghcr.io/your-github-user
IMAGE_TAG=v0.1.0-amd64
```

#### Multi-architecture GHCR release (recommended)

```bash
GHCR_USER=your-github-user IMAGE_TAG=v0.1.0 ./deploy.sh release
```

This publishes one tag for each image that contains both `linux/amd64` and `linux/arm64` variants. That is the most convenient cross-architecture release workflow.

On the server:

```bash
# .env on server
IMAGE_REGISTRY=ghcr.io/your-github-user
IMAGE_TAG=v0.1.0

# Pull and start
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

> **Note:** `NEXT_PUBLIC_*` values are baked into the frontend image at build time. Changing them requires a rebuild on the Mac side. Prefer explicit version tags like `v0.1.0` instead of relying only on `latest`.

### Rebuild & Redeploy
```bash
# Local development:
docker compose up -d --build

# Remote server:
./deploy.sh sync user@your-server
```

### Data Persistence
All data is stored in Docker volumes (`auth-data`, `app-data`). To fully reset:
```bash
docker compose down -v   # removes volumes and all data
docker compose up -d --build
```

### Security Note
The Docker socket (`/var/run/docker.sock`) is mounted into the backend container for workflow execution. This gives the container access to the host's Docker daemon. Only deploy on trusted networks.

---

## Local Development

### Prerequisites
- Python 3.13+ (backend uses `uv` and async SQLAlchemy)
- Bun (frontend, Next.js)
- Docker (optional, for workflow execution)

### Backend
```bash
cp .env.example .env
# Edit .env — set BIOINFOFLOW_HOME to an existing directory, then set your API key
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

Docs: `http://localhost:8000/api/v1/docs`

### Frontend
```bash
cd frontend
bun install
bun run dev
```

UI: `http://localhost:3000`

### CLI
```bash
cd backend
uv sync
uv run bif --help
```

The `bif` CLI works in three modes: `remote` (HTTP to running server), `local` (in-process, no server needed), or `auto` (try remote, fall back to local). Supports `--output json` for machine-parseable output (NDJSON for streaming commands).

```bash
bif project list                          # Rich table output
bif --output json run show r-abc          # JSON envelope
bif agent send "analyze samples" --project proj  # Single-shot agent message
bif run watch r-abc --project proj               # Real-time SSE streaming
bif doctor                                # Health check
```

Full CLI documentation: [`docs/cli/README.md`](docs/cli/README.md)

### Frontend ↔ Backend integration
The frontend now auto-loads the repo-root `.env`, so no extra frontend env file is required for the normal local setup.

Default local values in the root `.env`:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
BETTER_AUTH_URL=http://localhost:3000
```

Backend CORS defaults to `http://localhost:3000` (see `.env.example`).

---

## Docker (full stack)

See [Quick Start (Docker)](#quick-start-docker) above. The `docker-compose.yml` at the project root runs both backend and frontend.

```bash
docker compose up -d --build    # Build and start
docker compose logs -f          # Watch logs
docker compose down             # Stop
docker compose down -v          # Stop and remove all data
```

## Tests

Backend:
```bash
cd backend
uv run pytest
```

Frontend:
```bash
cd frontend
bun run lint
bun run test
```

## Deployment

See [Quick Start (Docker)](#quick-start-docker) for the recommended Docker Compose deployment. For custom setups:

### Backend
- Build from `backend/Dockerfile` and configure via environment variables.
- The entrypoint automatically runs database migrations before starting the server.

### Frontend
- Build from `frontend/Dockerfile` with `NEXT_PUBLIC_*` build args pointing to your backend.
- Set `BETTER_AUTH_DB_PATH` and `BETTER_AUTH_URL` at runtime.

## Repository Layout

| Directory | Description |
|-----------|-------------|
| `backend/` | FastAPI server, agent orchestration, workflow execution, scheduler |
| `backend/app/cli/` | `bif` CLI tool (terminal + agent access) |
| `frontend/` | Next.js 16 App Router UI |
| `docs/` | Architecture notes, API reference, plans |
| `codemaps/` | Generated architecture maps |
