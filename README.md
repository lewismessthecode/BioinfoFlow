# Bioinfoflow

> A local-first AI workspace for running bioinformatics pipelines on your own machine or lab server.

Bioinfoflow turns the messy middle of computational biology into a product workflow: register a Nextflow or WDL pipeline, choose data from managed project storage, submit runs, watch the DAG and logs live, and ask an AI agent to help with the parts that normally become shell scripts and tribal knowledge.

It is built for teams that want modern product ergonomics for local and lab-server analysis today, with a path toward cloud execution later when the workflow or organization needs it.

## Product Preview

> Preview slot: replace this block with an MP4 or GIF before launch.
>
> Suggested path: `docs/assets/product-preview.mp4` or `docs/assets/product-preview.gif`.

## Why It Exists

Bioinformatics has three bad defaults:

- Cloud platforms are polished, but expensive, opinionated, and not always the right first stop for regulated or sensitive data.
- Raw CLI workflows are flexible, but every lab rebuilds the same wrapper scripts, run tracking, file conventions, and debugging habits.
- Traditional bioinformatics portals often inherit the gap between life science and software: confusing UI, dated UX, hard-to-learn screens, and workflows that feel designed around infrastructure instead of users.

Bioinfoflow starts as the local operating layer between those worlds. It keeps standard workflow engines, Docker, and your filesystem, then adds the product surface teams expect: projects, runs, scheduler, live DAGs, file picking, audit trails, CLI automation, and an agent that can reason across the workspace.

## What You Can Do

- Run existing **Nextflow** and **WDL/MiniWDL** workflows from one UI.
- Keep data local under a single `BIOINFOFLOW_HOME`.
- Manage projects, workflow registrations, run inputs, outputs, logs, and status.
- Monitor long-running jobs with live task updates, DAG visualization, and scheduler state.
- Use the `bif` CLI for scripting, JSON output, and remote/local automation.
- Run GPU-accelerated WGS analysis with NVIDIA Parabricks on your own workstation or lab server, including personal-genome workflows when your hardware supports it.
- Deploy to a trusted Linux workstation or lab GPU server without copying source code to it.

## Current Status

Bioinfoflow is ready for developer-preview use on trusted machines and lab servers. It is intentionally local-first and single-node today.

Use it now if you want to validate the workflow experience, run platform tests, and collect early users. Before exposing it broadly on the public internet, treat the Docker socket and authentication model as production hardening work.

Ship checklist: [`docs/SHIP_CHECKLIST.md`](docs/SHIP_CHECKLIST.md)

## Quick Start

Prerequisites:

- Docker Engine or Docker Desktop with Compose
- One AI provider key: Anthropic, OpenAI, Gemini, or DeepSeek

```bash
cp .env.example .env
```

Edit `.env` and set at least:

```env
BIOINFOFLOW_HOME=/absolute/path/to/bioinfoflow-data
ANTHROPIC_API_KEY=...
AUTH_BOOTSTRAP_OWNER_EMAIL=admin@example.com
AUTH_BOOTSTRAP_OWNER_PASSWORD=change-me
```

Examples:

```env
BIOINFOFLOW_HOME=/srv/bioinfoflow
BIOINFOFLOW_HOME=/Users/<you>/bioinfoflow-data
BIOINFOFLOW_HOME=/lustre/<user>/bioinfoflow
```

Create the data root and start the stack. For example, inside this repo you can use `data/`:

```bash
mkdir -p /Users/lewisliu/Dev/ACTIVE/bioinfoflow/data/{projects,sources,state}
docker compose up -d --build
```

Open:

- UI: <http://localhost:3000>
- API docs: <http://localhost:8000/api/v1/docs>

Sign in with `AUTH_BOOTSTRAP_OWNER_EMAIL` and `AUTH_BOOTSTRAP_OWNER_PASSWORD`.

Full setup and troubleshooting: [`RUNBOOK.md`](RUNBOOK.md)

## Core Concepts

### Where Your Files Go

Think of `BIOINFOFLOW_HOME` as Bioinfoflow's workspace folder. It is just a normal directory on your machine or server. The app stores its database, project files, uploaded inputs, references, and run outputs under that one folder.

For local development in this repo, a concrete layout looks like this:

```text
/Users/lewisliu/Dev/ACTIVE/bioinfoflow/data/
  projects/   # per-project files, manifests, run outputs
  sources/    # shared input data and references
  state/      # SQLite databases and runtime state
```

Set:

```env
BIOINFOFLOW_HOME=/Users/lewisliu/Dev/ACTIVE/bioinfoflow/data
```

On a Linux server, the same idea usually becomes:

```text
/srv/bioinfoflow/
  projects/
  sources/
  state/
```

Docker mounts that directory at the same absolute path inside the backend container. That means the host, backend, workflow runner, and task containers can all refer to the same FASTQ, BAM, VCF, reference, and output paths without translation.

### How The UI Organizes Files

The UI presents storage as three user-facing zones:

| Zone | Use it for |
| --- | --- |
| Project Data | Files under `data/projects/...`: project-private manifests, helper files, run outputs |
| Deliveries | Files under `data/sources/deliveries/...`: incoming FASTQ/BAM/VCF files from instruments or collaborators |
| Reference Library | Files under `data/sources/reference/...`: shared FASTA, indexes, BED/GTF, known-sites VCFs |

Typical flow:

1. Copy raw sequencing files to `data/sources/deliveries/<batch-name>/`.
2. Copy reusable references to `data/sources/reference/<genome-name>/`.
3. Register or select a workflow.
4. Use the run wizard to pick files instead of typing container paths.
5. Submit and watch the run update live.

Example:

```bash
mkdir -p data/sources/deliveries/hg002
mkdir -p data/sources/reference/hg38

cp /path/to/HG002_R1.fastq.gz data/sources/deliveries/hg002/
cp /path/to/HG002_R2.fastq.gz data/sources/deliveries/hg002/
cp /path/to/hg38.fa* data/sources/reference/hg38/
```

Then choose those files from `Deliveries` and `Reference Library` in the run wizard.

## Included Parabricks WGS Workflows

For GPU-accelerated whole-genome analysis, this repo includes NVIDIA Parabricks WGS FASTQ-to-VCF workflows pinned to Parabricks v4.7.0:

- Nextflow: `demo/parabricks-wgs-v470/nextflow/main.nf`
- WDL: `demo/parabricks-wgs-v470/wdl/wgs_fq_to_vcf.wdl`

Both use:

```text
nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1
```

Input templates:

- `demo/parabricks-wgs-v470/nextflow/params.example.json`
- `demo/parabricks-wgs-v470/nextflow/samplesheet.example.csv`
- `demo/parabricks-wgs-v470/wdl/inputs.example.json`

Replace the FASTQ/reference paths with files visible on your GPU server, then register the workflows in Bioinfoflow to test registration, image handling, scheduling, GPU execution, and result collection.

## Remote Deployment

Deploy to a trusted Linux server without copying source code to the server. The existing `deploy.sh` supports two paths.

### First-Time Server Setup

```bash
./deploy.sh setup user@your-server
ssh user@your-server
cd ~/bioinfoflow
vim .env
```

Set server-specific values:

```env
BIOINFOFLOW_HOME=/srv/bioinfoflow
ANTHROPIC_API_KEY=...
AUTH_BOOTSTRAP_OWNER_EMAIL=admin@example.com
AUTH_BOOTSTRAP_OWNER_PASSWORD=<strong-password>
BETTER_AUTH_SECRET=<long-random-secret>

NEXT_PUBLIC_API_BASE_URL=http://YOUR_SERVER_IP:8000/api/v1
BETTER_AUTH_URL=http://YOUR_SERVER_IP:3000
CORS_ORIGINS=["http://YOUR_SERVER_IP:3000"]
TRUSTED_HOSTS=["localhost","127.0.0.1","YOUR_SERVER_IP"]
```

`NEXT_PUBLIC_API_BASE_URL` is baked into the frontend image at build time. If this points at `localhost`, remote browser sessions will fail.

### Offline Sync

Build locally, copy image tarballs over SSH, and start Compose on the server:

```bash
NEXT_PUBLIC_API_BASE_URL=http://YOUR_SERVER_IP:8000/api/v1 \
  ./deploy.sh sync --arch amd64 user@your-server
```

Use `--arch arm64` only for ARM Linux servers.

### GHCR Release

Publish images to GitHub Container Registry:

```bash
export GHCR_USER=your-github-user-or-org
export GHCR_TOKEN=your-github-token
echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin

IMAGE_TAG=v0.1.0 ./deploy.sh release
```

On the server:

```env
IMAGE_REGISTRY=ghcr.io/your-github-user-or-org
IMAGE_TAG=v0.1.0
```

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

## CLI

The `bif` CLI supports remote HTTP mode, local in-process mode, and auto fallback:

```bash
cd backend
uv sync
uv run bif --help
uv run bif doctor
uv run bif project list
uv run bif --output json run show r-abc
```

Full CLI documentation: [`docs/cli/README.md`](docs/cli/README.md)

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

## Architecture

- Backend: FastAPI, async SQLAlchemy, SQLite, Alembic, Typer CLI
- Frontend: Next.js 16, React 19, Radix UI, Tailwind CSS 4, React Flow
- Engines: Nextflow and WDL/MiniWDL adapters
- Scheduler: persistent queue with resource accounting, retries, timeouts, cleanup, and completion hooks
- Realtime: SSE for runs and agent events, WebSocket for terminal sessions
- Agent runtime: async tool dispatch loop with project/workflow context

More detail:

- Product overview: [`docs/product-overview.md`](docs/product-overview.md)
- Backend overview: [`docs/backend/overview.md`](docs/backend/overview.md)
- Frontend overview: [`docs/frontend/overview.md`](docs/frontend/overview.md)
- Workflow submission guide: [`docs/workflow-submission-guide.md`](docs/workflow-submission-guide.md)

## Security Notes

- Mounting `/var/run/docker.sock` gives the backend container access to the host Docker daemon. Deploy only on trusted machines and trusted networks.
- Use a strong `BETTER_AUTH_SECRET` for any shared server.
- Set `BETTER_AUTH_URL`, `CORS_ORIGINS`, and `TRUSTED_HOSTS` to the exact public origin/host before remote use.
- Keep `.env` private. Use `.env.example` as the shareable template.

## License

MIT. See [`LICENSE`](LICENSE).
