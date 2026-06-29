<p align="center">
  <img src="frontend/public/brand-icon.png" width="80" alt="Bioinfoflow" />
</p>

<h1 align="center">BioinfoFlow</h1>

<p align="center">
  <em>The local Agentic control plane for Nextflow &amp; WDL bioinformatics pipelines.</em>
</p>

<p align="center">
  <a href="https://discord.gg/bBZB8bFnHB"><img src="https://img.shields.io/badge/discord-join-5865F2?logo=discord&logoColor=white" alt="Discord" /></a>
  <a href="docs/README.md"><img src="https://img.shields.io/badge/docs-view-3b82f6" alt="Docs" /></a>
  <a href="https://bioinfoflow.com"><img src="https://img.shields.io/badge/website-visit-111827" alt="Website" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-22c55e" alt="License: MIT" /></a>
</p>

<p align="center">
  <b>English</b> | <a href="README.zh-CN.md">简体中文</a> | <a href="https://deepwiki.com/lewismessthecode/BioinfoFlow">Docs</a>
</p>

---

Bioinfoflow is a local-first control plane for bioinformatics workflows. It runs on a workstation or lab server, stores project data under one `BIOINFOFLOW_HOME`, and provides a shared web UI for registering pipelines, submitting runs, inspecting logs, and reviewing outputs.

Bioinfoflow sits above Nextflow and WDL/MiniWDL. It adds a persistent scheduler, workflow-aware storage layout, browser terminal, HTTP CLI, and an AgentCore runtime that can help prepare configs, inspect project files, operate selected SSH hosts, and launch workflow runs with approval gates for higher-impact actions.

> [!TIP]
> One-line install:
>
> ```bash
> git clone https://github.com/your-org/bioinfoflow && cd bioinfoflow
> cp .env.example .env   # set owner credentials; provider keys can be added in the UI
> docker compose up -d --build
> ```
>
> Then open <http://localhost:3000>.

<p align="center">
  <img src="assets/product-preview.gif" alt="Bioinfoflow — register a workflow, pick inputs, submit a run, watch the live DAG" width="100%" />
</p>

---

## Features

- **Workflow Catalog**: Register Nextflow and WDL workflows once, then submit runs from the UI, CLI, or AgentCore tools.
- **Unified Data Layout**: Use one `BIOINFOFLOW_HOME` for project data, references, shared databases, uploads, run inputs, and outputs.
- **Run Workspace**: Configure inputs, submit runs, watch the DAG, follow logs, and inspect outputs from one page.
- **Persistent Scheduler**: Queue runs with concurrency slots, resource checks, retry policy, timeout handling, cleanup, and restart recovery.
- **AgentCore Runtime**: Use chat to inspect files, manage projects and workflows, run approved platform actions, and operate selected SSH connections.
- **Remote Connections**: Save SSH profiles, test them through the backend, stream short probe commands, and expose selected hosts to AgentCore tools.
- **Browser Terminal and `bif` CLI**: Use the web UI for interactive work and the CLI for scripting against a running backend.
- **Local Auth and Team Roles**: Run in personal, team, or development auth modes with Better Auth-backed sessions.

---

## Quick Start

### Prerequisites

- Docker Engine or Docker Desktop with Compose
- One AI provider key for agent use. You can paste it after sign-in under **Settings -> AI Providers**, or bootstrap it in `.env`.

### Run with Docker

```bash
cp .env.example .env
```

Edit `.env` and set at least the owner credentials:

```env
AUTH_BOOTSTRAP_OWNER_EMAIL=admin@example.com
AUTH_BOOTSTRAP_OWNER_PASSWORD=change-me
```

After sign-in, open **Settings -> AI Providers** and paste a key for OpenAI, Anthropic, Gemini, Grok, Groq, DeepSeek, OpenRouter, or configure Ollama, vLLM, and OpenAI-compatible endpoints. For headless deployments you can bootstrap providers in `.env` with variables such as `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`, `XAI_API_KEY`, `GROK_API_KEY`, `GROQ_API_KEY`, `OLLAMA_BASE_URL`, `VLLM_BASE_URL`, `VLLM_API_KEY`, `VLLM_MODEL`, `OPENAI_COMPATIBLE_BASE_URL`, `OPENAI_COMPATIBLE_API_KEY`, and `OPENAI_COMPATIBLE_MODEL`.

Start the stack:

```bash
docker compose up -d --build
```

Then open:

- **UI** — <http://localhost:3000>
- **API docs** — <http://localhost:8000/api/v1/docs>

Sign in with the bootstrap owner credentials from `.env`.

For local Docker, leaving `BIOINFOFLOW_HOME` unset is the simplest path — Compose stores platform data under this repo's `data/` directory and mounts it at the same absolute path inside containers. For a shared or remote server, set `BETTER_AUTH_SECRET`, `NEXT_PUBLIC_API_BASE_URL`, `BETTER_AUTH_URL`, `CORS_ORIGINS`, and `TRUSTED_HOSTS` before building. See the [Docker Quick Start](docs/getting-started/docker.md) and [Runbook](RUNBOOK.md).

### Run with published images

For a faster localhost start without rebuilding images, use the GHCR release images:

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

Published images are refreshed from `main` when backend or frontend code changes. The published frontend image is built for localhost; for a remote server, set the public URLs in `.env` and use the source-build command above.

`IMAGE_REGISTRY` can point at any registry namespace that contains the
Bioinfoflow backend/frontend images, including Harbor, for example
`10.227.4.56:80/pipeline-dev`. Workflow container registries are configured in
**Settings -> Container Registries**, where owners/admins can add Harbor, mark a
global default, and store or reference credentials. Harbor is optional; workflow
containers can still use Docker Hub, full image names, or tarball imports. See
the [Docker Quick Start](docs/getting-started/docker.md#optional-container-registry)
for registry and insecure-HTTP Harbor notes.

---

## Development

Backend:

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --reload-dir app --port 8000
```

Frontend:

```bash
cd frontend
bun install
bun run dev
```

Checks:

```bash
cd backend  && uv run pytest && uv run ruff check .
cd frontend && bun run lint && bun run test
```

Backend and frontend both read the repo-root `.env` by default. Use `backend/.env` or `frontend/.env.local` only for machine-local overrides.

---

## CLI

`bif` is an HTTP client for a running Bioinfoflow backend:

```bash
cd backend
uv run bif doctor
uv run bif project list
uv run bif workflow list
uv run bif run list
uv run bif --output json run show <run-id>
```

Use `--base-url` or `BIOFLOW_API_URL` to point at a non-default backend. See the [CLI Reference](docs/reference/cli.md).

---

## Documentation

- [Docs Home](docs/README.md)
- [Docker Quick Start](docs/getting-started/docker.md)
- [Remote Connections](docs/guides/remote-connections.md)
- [nf-core/rnaseq Launch Demo](demo/nfcore-rnaseq/README.md)
- [Storage and Data Layout](docs/concepts/storage.md)
- [CLI Reference](docs/reference/cli.md)
- [Architecture](docs/architecture.md)
- [Security Notes](docs/security.md)
- [Runbook](RUNBOOK.md)

---

## License

Bioinfoflow is released under the [MIT License](LICENSE).
