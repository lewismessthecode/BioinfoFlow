<p align="center">
  <img src="frontend/public/brand-icon.png" width="80" alt="Bioinfoflow" />
</p>

<h1 align="center">BioinfoFlow</h1>

<p align="center">
  <em>An Agent-guided workspace for bioinformatics analysis.</em>
</p>

<p align="center">
  <a href="https://discord.gg/bBZB8bFnHB"><img src="https://img.shields.io/badge/discord-join-5865F2?logo=discord&logoColor=white" alt="Discord" /></a>
  <a href="docs/README.md"><img src="https://img.shields.io/badge/docs-view-3b82f6" alt="Docs" /></a>
  <a href="https://bioinfoflow.com"><img src="https://img.shields.io/badge/website-visit-111827" alt="Website" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-22c55e" alt="License: MIT" /></a>
</p>

<p align="center">
  <b>English</b> | <a href="README.zh-CN.md">简体中文</a>
</p>

---

Bioinformatics work rarely lives in one place. Workflow definitions, sample
sheets, reference data, containers, logs, outputs, and the notes that explain a
run often end up scattered across terminals and directories.

Bioinfoflow gives that work a stable home. It brings projects, workflow runs,
logs, DAGs, results, terminals, and operational context into one system spanning
managed local data, existing directories, and SSH-backed remote projects. The
platform runs on infrastructure you control, with the same backend available
through the web UI, `bif` CLI, and Agent.

The Agent is not a chat box bolted onto a dashboard. It shares the platform's
working context: project files, workflow definitions, run history, scheduler
state, tools, skills, and selected remote hosts. It can inspect, prepare, and
act within that context, while permission and approval gates keep consequential
operations under human control.

> [!TIP]
> Start locally with Docker:
>
> ```bash
> git clone https://github.com/lewismessthecode/BioinfoFlow.git
> cd BioinfoFlow
> cp .env.example .env
> # edit .env and change the bootstrap owner credentials
> docker compose up -d --build
> ```
>
> Then open <http://localhost:3000>.

<p align="center">
  <img src="assets/product-preview.gif" alt="Bioinfoflow — register a workflow, choose inputs, submit a run, and follow its DAG" width="100%" />
</p>

## What comes together

### Projects with a durable data boundary

Each project has a clear place for its files, workflow bindings, run history,
and outputs. Bioinfoflow can manage project storage under one
`BIOINFOFLOW_HOME`, use an existing local directory, or attach a remote project
to a saved SSH connection.

### Runs that remain inspectable

Register a workflow once, configure its inputs, and submit it from the web UI,
CLI, or Agent. A persistent scheduler manages whole-run concurrency, resources,
retries, timeouts, cleanup, and restart recovery. The run workspace keeps the
DAG, logs, events, inputs, audit trail, and collected results together.

Bioinfoflow currently executes workflows through Nextflow and WDL/MiniWDL
adapters. The engine is an implementation detail behind a shared project and run
model, not a separate user experience.

### An Agent that can work, not only answer

The Agent works with the same state as the rest of the platform: files,
workflows, runs, scheduler resources, images, skills, and selected remote
connections. It can move from understanding a request to inspecting evidence,
preparing configuration, calling tools, and submitting work. Read-oriented
steps can proceed directly; higher-impact actions remain subject to permission
and approval policy.

### Local and remote work, with explicit boundaries

The browser terminal, `bif` CLI, and Remote Connections cover interactive and
scripted operations without moving the platform's center of gravity into a
hosted service. Saved SSH profiles support connection tests, short probes,
remote project terminals, and bounded Agent tools.

Here, local-first describes ownership and control, not a requirement that every
file or machine be local. Bioinfoflow can keep its platform state close while
working with explicitly connected remote resources.

## Who it is for

Bioinfoflow is a good fit when you:

- develop or operate bioinformatics workflows on your own compute;
- want runs to be reproducible and understandable after the terminal session is gone;
- need a shared view of projects, inputs, logs, DAGs, and results;
- want an Agent that can reason over real system state and take useful action while leaving consequential decisions under human control.

It is designed first for individual researchers, bioinformatics developers, and
small teams operating their own workstations, lab servers, and SSH-accessible
compute. It is not a hosted data analysis service, and it does not require
research data to leave infrastructure you control.

## Quick start

### Requirements

- Docker Engine or Docker Desktop with Compose
- An AI provider only if you want to use the Agent: a hosted API key or a
  configured Ollama, vLLM, or OpenAI-compatible endpoint

### Start from source

```bash
git clone https://github.com/lewismessthecode/BioinfoFlow.git
cd BioinfoFlow
cp .env.example .env
```

Set the bootstrap owner credentials in `.env`:

```env
AUTH_BOOTSTRAP_OWNER_EMAIL=admin@example.com
AUTH_BOOTSTRAP_OWNER_PASSWORD=change-me
```

Start the application:

```bash
docker compose up -d --build
```

Open:

- Web UI: <http://localhost:3000>
- API documentation: <http://localhost:8000/api/v1/docs>

For local source builds, the default data root is this repository's `data/`
directory. Provider setup is available after sign-in under **Settings → AI
Providers**. See the [Docker guide](docs/getting-started/docker.md) for published
images, GPU access, private registries, and remote deployments; see the
[runbook](RUNBOOK.md) for configuration precedence and troubleshooting.

<details>
<summary>Start with published images instead</summary>

The published frontend image is intended for a localhost, personal-mode trial.

```bash
cp .env.example .env
cat >> .env <<'EOF'
IMAGE_REGISTRY=ghcr.io/lewismessthecode
IMAGE_TAG=latest
EOF
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

Build from source when you need remote public URLs, team mode, or different
authentication settings.

</details>

## How it works

```text
Web UI / bif CLI / Agent
        ↓
FastAPI services and persistent state
        ↓
Scheduler and workflow-engine adapters
        ↓
Containers, logs, events, and results on your infrastructure
```

- The frontend is a Next.js application for projects, workflows, runs, images,
  connections, scheduling, settings, terminals, and Agent sessions.
- The FastAPI backend owns business logic, durable state, storage paths,
  scheduling, execution, events, and tools.
- Workflow-engine adapters translate the shared run model into engine-specific
  execution and result collection.
- `BIOINFOFLOW_HOME` provides the common platform root for state, managed
  projects, workflow sources, shared inputs, caches, and outputs.

For implementation boundaries, see the [architecture overview](docs/architecture.md)
and [architecture reference](docs/reference/architecture.md).

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

Use `--base-url` or `BIOFLOW_API_URL` to select another backend. The full command
surface is documented in the [CLI reference](docs/reference/cli.md).

## Development

```bash
# Backend
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --reload-dir app --port 8000

# Frontend, in another terminal
cd frontend
bun install
bun run dev
```

Run backend checks with `uv run pytest && uv run ruff check .` and frontend
checks with `bun run lint && bun run test`.

## Operational boundaries

- Bioinfoflow is designed for trusted machines and networks. Docker deployments
  mount the Docker socket, which gives the backend host-level container control.
- Workflow paths use an identity-mount model: the host, backend, workflow
  runner, and task containers must see relevant data at consistent absolute
  paths.
- Remote Connections are for inspection, diagnostics, Agent tools, and
  interactive terminals. Workflow runs are still dispatched through the local
  scheduler and engine adapters, not over SSH.
- Shared or internet-facing deployments require explicit secrets, trusted
  origins, TLS termination, backups, and normal infrastructure hardening.

Read the [security notes](docs/security.md), [storage model](docs/concepts/storage.md),
and [operations runbook](docs/operations/runbook.md) before deploying beyond a
local trusted environment.

## Documentation

- [Documentation home](docs/README.md)
- [Docker quick start](docs/getting-started/docker.md)
- [Runbook](RUNBOOK.md)
- [Architecture](docs/architecture.md)
- [Storage and data layout](docs/concepts/storage.md)
- [Remote Connections](docs/guides/remote-connections.md)
- [nf-core/rnaseq example](demo/nfcore-rnaseq/README.md)

## License

Bioinfoflow is released under the [MIT License](LICENSE).
