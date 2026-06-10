<p align="center">
  <img src="frontend/public/brand-icon.png" width="80" alt="Bioinfoflow" />
</p>

<h1 align="center">BioinfoFlow 👋</h1>

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

Bioinformatics tooling has been stuck in another era — clunky interfaces, tedious workflows, learning curves steep enough to turn away the people who need them most. Bioinfoflow's mission is simple: bring the elegance of modern software engineering to bioinformatics, and let an AI agent close the cultural gap between biologists and computer scientists.

Bioinfoflow turns a workstation or a lab server into a workspace your whole team can share. It sits above Nextflow and WDL: register pipelines once, gather project data under a single `BIOINFOFLOW_HOME`, hand runs off to a built-in scheduler, and watch DAGs, logs, resource pressure, and outputs from one product surface.

The bigger ambition: a single, coherent product layer above the compute — so computational biology stops being something only specialist teams can run. One sentence of natural language should be enough to launch a full analysis. With a 16 GB-class GPU, our goal is to put a Parabricks WGS run within reach of any desktop — no cloud required.

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

<!--
  Hero video: replace the <img> below with a GitHub-hosted MP4 for sharper rendering.
  Steps:
    1. Open a new issue or PR draft on this repo (no need to submit it)
    2. Drag-and-drop assets/product-preview.mp4 into the comment box and wait for the upload
    3. Copy the resulting https://github.com/user-attachments/assets/<uuid> URL
    4. Replace with: <video src="<that-url>" autoplay loop muted playsinline width="100%"></video>
-->
<p align="center">
  <img src="assets/product-preview.gif" alt="Bioinfoflow — register a workflow, pick inputs, submit a run, watch the live DAG" width="100%" />
</p>

---

## ⭐ Features

- 🧬 **Workflow Catalog** — Register once, run anywhere; demos for nf-core/rnaseq, Parabricks WGS, and more ship out of the box.
- 📁 **Unified Data Layout** — A single `BIOINFOFLOW_HOME` for project files, references, databases, uploads, and results.
- 🚦 **Run Workspace** — Configure, submit, watch the live DAG, follow logs, and inspect outputs — all on one page.
- ⚙️ **Persistent Scheduler** — A queue that doesn't lose work, resource gates that won't dispatch what won't fit, and automatic retries when something fails.
- 🤖 **AI Agent** — Register pipelines, prepare configs, inspect files, submit runs, and interpret results — all from chat.
- 💻 **Browser Terminal & `bif` CLI** — GUI when you want it, shell when you don't.
- 🔐 **Local Auth & Personalization** — Switch between personal and team modes, swap themes with a click.

<!--
  TODO (Plan 3): drop 2–3 feature screenshots here for visual density.
  Suggested shots:
    - Workflow catalog page (sidebar + workflow cards)
    - Run detail page (live DAG + logs side panel)
    - Agent chat (with an approval step in view)
  Spec: 1600px-wide PNGs, < 800KB each (run pngquant before committing).
  Layout: three across
    <p align="center">
      <img src="assets/feature-catalog.png"  width="32%" />
      <img src="assets/feature-run-dag.png"  width="32%" />
      <img src="assets/feature-agent.png"    width="32%" />
    </p>
-->

---

## 🚀 Quick Start

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

After sign-in, open **Settings -> AI Providers** and paste a key for OpenAI, Anthropic, Gemini, Grok, Groq, DeepSeek, OpenRouter, or configure Ollama/vLLM/OpenAI-compatible endpoints. For headless deployments you can still bootstrap providers in `.env`, for example `VLLM_BASE_URL`, `VLLM_API_KEY`, and `VLLM_MODEL`.

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

---

## 🛠 Development

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

## 💻 CLI

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

## 📚 Documentation

- [Docs Home](docs/README.md)
- [Docker Quick Start](docs/getting-started/docker.md)
- [nf-core/rnaseq Launch Demo](demo/nfcore-rnaseq/README.md)
- [Storage and Data Layout](docs/concepts/storage.md)
- [CLI Reference](docs/reference/cli.md)
- [Architecture](docs/architecture.md)
- [Security Notes](docs/security.md)
- [Runbook](RUNBOOK.md)

---

## 📜 License

Bioinfoflow is released under the [MIT License](LICENSE).
