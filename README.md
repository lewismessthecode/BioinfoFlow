# Bioinfoflow

> A local-first AI workspace for running bioinformatics pipelines on your own machine or lab server.

Bioinfoflow turns the messy middle of computational biology into a product workflow: register a Nextflow or WDL pipeline, choose data from managed project storage, submit runs, watch the DAG and logs live, and ask an AI agent to help with the parts that normally become shell scripts and tribal knowledge.

It is built for teams that want modern product ergonomics for local and lab-server analysis today, with a path toward cloud execution later when the workflow or organization needs it.

## Product Preview

<p align="center">
  <picture>
    <source srcset="assets/product-preview.webp" type="image/webp">
    <img src="assets/product-preview.gif" alt="Bioinfoflow - register a workflow, pick inputs, submit a run, and watch the live DAG" width="100%" decoding="async">
  </picture>
</p>

## What You Can Do

- Run existing Nextflow and WDL/MiniWDL workflows from one UI.
- Keep project data, shared inputs, references, run outputs, and state under one `BIOINFOFLOW_HOME`.
- Monitor long-running jobs with live task updates, DAG visualization, scheduler state, logs, and outputs.
- Use the `bif` CLI for scripting, JSON output, and remote/local automation.
- Run GPU-oriented workflows, including the included NVIDIA Parabricks WGS examples, on a trusted workstation or lab server.

## Quick Start

Prerequisites:

- Docker Engine or Docker Desktop with Compose
- One AI provider key, such as Anthropic, OpenAI, Gemini, or DeepSeek

Create your local environment file:

```bash
cp .env.example .env
```

Then edit `.env` and set:

```env
# Optional for local Docker.
# If unset, Docker Compose uses this repo's ./data directory.
# Set an absolute path only when you want the data root somewhere else.
# BIOINFOFLOW_HOME=/absolute/path/to/bioinfoflow-data

# Set at least one provider key.
ANTHROPIC_API_KEY=...
# OPENAI_API_KEY=...
# GEMINI_API_KEY=...
# DEEPSEEK_API_KEY=...

# First local owner account.
AUTH_BOOTSTRAP_OWNER_EMAIL=admin@example.com
AUTH_BOOTSTRAP_OWNER_PASSWORD=change-me

# Optional for localhost Docker. If empty, Bioinfoflow creates a persistent
# local secret under BIOINFOFLOW_HOME/state/auth on first startup.
# Set this before running a shared or remote deployment.
# BETTER_AUTH_SECRET=...
```

Then start Bioinfoflow:

```bash
docker compose up -d --build
```

Open:

- UI: <http://localhost:3000>
- API docs: <http://localhost:8000/api/v1/docs>

Sign in with `AUTH_BOOTSTRAP_OWNER_EMAIL` and `AUTH_BOOTSTRAP_OWNER_PASSWORD`.

Notes:

- For local Docker, leaving `BIOINFOFLOW_HOME` unset is the simplest path. Compose mounts this repo's `data/` directory at the same absolute path inside the containers.
- For localhost Docker, `BETTER_AUTH_SECRET` can stay empty. Bioinfoflow generates and reuses a local secret file on first startup.
- The backend creates the platform directories under `BIOINFOFLOW_HOME` on startup.
- If you set `BIOINFOFLOW_HOME`, use an absolute host path and keep the same path visible to containers.
- For a shared or remote server, generate a secret with `openssl rand -base64 32`, then set `BETTER_AUTH_SECRET`, `NEXT_PUBLIC_API_BASE_URL`, `BETTER_AUTH_URL`, `CORS_ORIGINS`, and `TRUSTED_HOSTS` before building.

More setup detail: [Docker Quick Start](docs/getting-started/docker.md) and [Runbook](RUNBOOK.md).

## Local Development

Backend:

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
bun install
bun run dev
```

Verification:

```bash
cd backend && uv run pytest
cd backend && uv run ruff check .
cd frontend && bun run lint
cd frontend && bun run test
```

The backend and frontend both read the repo-root `.env` by default. Use `backend/.env` or `frontend/.env.local` only for machine-local overrides.

## Bioinfoflow Docs

- [Docs Home](docs/README.md)
- [Docker Quick Start](docs/getting-started/docker.md)
- [Storage And Data Layout](docs/concepts/storage.md)
- [Parabricks WGS Workflows](docs/workflows/parabricks-wgs.md)
- [CLI Reference](docs/reference/cli.md)
- [Architecture](docs/reference/architecture.md)
- [Security Notes](docs/security.md)
