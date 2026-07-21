<p align="center">
  <img src="frontend/public/brand-icon.png" width="80" alt="Bioinfoflow" />
</p>

<h1 align="center">Bioinfoflow</h1>

<p align="center">
  <strong>A local Agent workspace for bioinformatics workflows.</strong>
</p>

<p align="center">
  Give the Agent a real project—not a pasted fragment of context. It can inspect
  files, prepare inputs, run Nextflow or WDL, follow logs and DAGs, and explain
  results on infrastructure you control.
</p>

<p align="center">
  <a href="https://discord.gg/bBZB8bFnHB"><img src="https://img.shields.io/badge/discord-join-5865F2?logo=discord&logoColor=white" alt="Join Discord" /></a>
  <a href="docs/README.md"><img src="https://img.shields.io/badge/docs-read-3b82f6" alt="Read the documentation" /></a>
  <a href="https://bioinfoflow.com"><img src="https://img.shields.io/badge/website-visit-111827" alt="Visit the website" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-22c55e" alt="MIT License" /></a>
</p>

<p align="center">
  <b>English</b> | <a href="README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  <img src="assets/product-preview.gif" alt="Bioinfoflow Agent inspecting a workflow, submitting a run, and following its DAG" width="100%" />
</p>

## Is Bioinfoflow for you?

Bioinfoflow is useful when the workflow command is not the hard part—the hard
part is keeping inputs, containers, parameters, logs, work directories, results,
and the explanation of what happened connected.

| A good fit if you… | Probably not needed if you… |
| --- | --- |
| Run or develop bioinformatics workflows on your own compute | Are satisfied with raw workflow-engine commands and filesystem conventions |
| Need failed runs to remain understandable after the terminal closes | Want a fully managed hosted analysis service |
| Want one view of project files, inputs, runs, DAGs, logs, and results | Need zero-administration multi-tenant hosting out of the box |
| Want an Agent that can inspect real state and take approval-gated action | Want an unrestricted autonomous Agent with no review boundary |

Bioinfoflow is designed first for individual researchers, bioinformaticians,
workflow developers, and small technical teams using workstations, lab servers,
or deliberately connected remote resources.

## Install and run the first analysis

Requirements: macOS or Linux, Docker Engine or Docker Desktop with Compose, and
an `amd64` or `arm64` machine.

The shortest path for a trusted local machine is the release installer:

```bash
curl -fsSL https://github.com/lewismessthecode/BioinfoFlow/releases/latest/download/install.sh | sh
```

It verifies the published release assets, pulls the matching architecture, and
opens <http://localhost:3000>. The localhost stack binds only to `127.0.0.1`,
stores persistent state under `~/.bioinfoflow/data`, and opens the Agent without
a Bioinfoflow login screen. Do not expose this no-auth localhost mode through a
reverse proxy, port forward, or public Docker host.

For updates, removal, version selection, checksum inspection, and source-build
alternatives, see the [Docker and installer guide](docs/getting-started/docker.md).

Build from source instead when developing Bioinfoflow or configuring a shared
or remote deployment:

```bash
git clone https://github.com/lewismessthecode/BioinfoFlow.git
cd BioinfoFlow
cp .env.example .env

# Before starting, change the bootstrap owner credentials:
# AUTH_BOOTSTRAP_OWNER_EMAIL, AUTH_BOOTSTRAP_OWNER_PASSWORD
${EDITOR:-vi} .env

docker compose up -d --build
```

For localhost-only use, `BETTER_AUTH_SECRET` may stay empty; Bioinfoflow
generates and persists a local secret. Set a stable value, for example from
`openssl rand -base64 32`, before shared or remote deployment. The source
Compose stack publishes its frontend and backend ports on host interfaces by
default, so change the owner credentials before startup and use it only on a
trusted machine and network.

Open <http://localhost:3000>. Source builds use the owner account configured in
`.env`; the localhost installer opens directly in development auth mode.

Your first useful run takes three steps:

1. Select **Connect a model** in the Agent composer and paste a provider API key.
2. Click **Check and run the demo workflow**.
3. Review the Agent's plan and approve the workflow submission.

The fresh workspace contains a `Bioinfoflow Demo` project, a registered
WDL workflow, a sample sheet, and two tiny FASTQ inputs. The Agent inspects those
real assets, prepares the run through Bioinfoflow's normal tools, pauses at the
run approval boundary, and can inspect or follow the resulting logs and outputs
after approval.

Provider setup is UI-first. OpenAI, Anthropic, and DeepSeek have a compact
composer path; Kimi, Kimi China, Gemini, OpenRouter, Ollama, vLLM, and
other compatible endpoints remain available in **Settings → AI Providers**.

## The Agent works through the platform

The Agent is not a chat box beside a workflow dashboard. It uses the same
projects, workflow registrations, run history, scheduler state, files, images,
skills, and selected remote connections as the rest of Bioinfoflow.

```text
Your analysis request
        ↓
Inspect project files, workflow, inputs, and previous runs
        ↓
Explain the plan and prepare configuration
        ↓
Call Bioinfoflow tools within the selected project and permission scope
        ↓
Pause for approval before consequential operations
        ↓
Inspect or follow events, logs, DAG state, and outputs
        ↓
Explain the result or diagnose the failure
```

Read-oriented work can proceed directly. Operations such as submitting or
cancelling a run remain subject to the active permission policy and explicit
approval. Agent sessions, tool actions, events, artifacts, and accepted memory
remain inspectable instead of disappearing into an unstructured chat transcript.

## What stays together

### Projects, wherever their data lives

A project can use Bioinfoflow-managed storage, an existing local directory, or
an SSH-backed remote project. Files, workflow bindings, conversations, run
history, and outputs stay attached to that project boundary.

### Runs that can be revisited

Bioinfoflow registers a workflow once and runs it from the web UI, `bif` CLI, or
Agent. Its persistent scheduler manages concurrency, resources, retries,
timeouts, cleanup, and restart recovery. Each run keeps its inputs, events, DAG,
logs, audit trail, and collected results together.

Nextflow and WDL/MiniWDL sit behind the same project and run model, so changing
engines does not require changing the surrounding workspace.

### Local control with deliberate remote access

The platform runs on infrastructure you control. Browser terminals, the `bif`
CLI, and saved SSH connections cover interactive and scripted work without
turning Bioinfoflow into a hosted data service. Remote commands remain bounded
by the selected connection, SSH identity, and Agent permission policy.

## Trust boundaries

- The localhost installer listens only on `127.0.0.1` and does not require a
  hosted Bioinfoflow account or separate database setup.
- Research data does not need to leave infrastructure you control. If you use a
  hosted model, the prompts and context sent to that provider follow the
  provider's data policy.
- No model provider is required for manual workflow use. The Agent requires a
  configured hosted or local compatible model.
- Workflow execution mounts the Docker socket into the backend. This gives
  Bioinfoflow host-level container control, so use it only on a machine and
  network you trust.
- Public, remote, or team deployments require authentication, stable secrets,
  TLS, trusted origins, backups, and normal infrastructure hardening. The
  localhost installer intentionally does not configure those deployments.

Read the [security notes](docs/security.md), [storage model](docs/concepts/storage.md),
and [operations runbook](docs/operations/runbook.md) before exposing Bioinfoflow
beyond one local user.

## Other ways to run Bioinfoflow

### Configure the source deployment

The source installation above is also the path for development, authenticated
personal or team deployments, custom public URLs, and frontend configuration
changes. For team or remote use, also set a stable
`BIOINFOFLOW_CREDENTIAL_KEY`, configure the real browser origin and trusted
origins, terminate TLS, and review the security guidance before exposing ports.
AI providers can be configured after sign-in.

See the [Docker guide](docs/getting-started/docker.md) for published images,
custom data roots, GPU access, and deployment choices. Configuration precedence
and troubleshooting live in the [runbook](RUNBOOK.md).

### CLI

`bif` is an HTTP client for a running backend:

```bash
cd backend
uv run bif doctor
uv run bif project list
uv run bif workflow list
uv run bif run list
uv run bif --output json run show <run-id>
```

Use `--base-url` or `BIOFLOW_API_URL` to select another backend. See the
[CLI reference](docs/reference/cli.md) for the full command surface.

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

The backend reads the repository-root `.env` when its process starts. Restart
the backend after changing it. Restart or rebuild the frontend after changing
any `NEXT_PUBLIC_*` value because those values are baked into the frontend.

Run backend checks with `uv run pytest && uv run ruff check .`. Run frontend
checks with `bun run lint && bun run test`.

## Documentation

- [Documentation home](docs/README.md)
- [Docker and installer guide](docs/getting-started/docker.md)
- [Runbook](RUNBOOK.md)
- [Architecture overview](docs/architecture.md)
- [Storage and data layout](docs/concepts/storage.md)
- [Remote Connections](docs/guides/remote-connections.md)
- [nf-core/rnaseq example](demo/nfcore-rnaseq/README.md)

## License

Bioinfoflow is released under the [MIT License](LICENSE).
