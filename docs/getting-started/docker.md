# Docker Quick Start

Learn how to start Bioinfoflow locally with Docker Compose, sign in as the
bootstrap owner, and choose the right settings for local or shared deployments.

## Prerequisites

- Docker Engine or Docker Desktop with Compose
- One AI provider key for agent use. You can paste it after sign-in under **Settings -> AI Providers**, or bootstrap it in `.env`.

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

AUTH_BOOTSTRAP_OWNER_EMAIL=admin@example.com
AUTH_BOOTSTRAP_OWNER_PASSWORD=change-me

# Optional for localhost Docker. If empty, Bioinfoflow creates a persistent
# local secret under BIOINFOFLOW_HOME/state/auth on first startup.
# Set this before running a shared or remote deployment.
# BETTER_AUTH_SECRET=...
```

Provider configuration is UI-first. Hosted providers only need an API key.
Ollama, vLLM, OpenRouter, and generic OpenAI-compatible endpoints can also be
configured from **Settings -> AI Providers**. In `AUTH_MODE=team`, provider keys
saved through the UI as stored credentials also require
`BIOINFOFLOW_CREDENTIAL_KEY`; environment bootstrap keys do not.

For headless bootstrap, set environment defaults such as:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`
- `DEEPSEEK_API_KEY`
- `OPENROUTER_API_KEY`
- `XAI_API_KEY` or `GROK_API_KEY`
- `GROQ_API_KEY`
- `OLLAMA_BASE_URL`
- `VLLM_BASE_URL`, `VLLM_API_KEY`, and `VLLM_MODEL`
- `OPENAI_COMPATIBLE_BASE_URL`, `OPENAI_COMPATIBLE_API_KEY`, and `OPENAI_COMPATIBLE_MODEL`

Start the stack:

```bash
docker compose up -d --build
```

Open:

- UI: `http://localhost:3000`
- API docs: `http://localhost:8000/api/v1/docs`

Sign in with the owner email and password from `.env`.

## Published Images

For localhost, you can skip the local image build and pull the latest images from GHCR:

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

The release workflow publishes:

- `ghcr.io/lewismessthecode/bioinfoflow-backend:<tag>`
- `ghcr.io/lewismessthecode/bioinfoflow-frontend:<tag>`

Use `latest`, `main`, or `sha-<12-char-commit>` as the tag. Images are republished from `main` only when backend or frontend code changes; docs-only changes do not create a new image.

The published frontend image is built for localhost with `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1`. For a shared or remote server, set the public URLs in `.env` and build from source instead:

```bash
docker compose up -d --build
```

## Optional Container Registry

Harbor and other private registries are optional. The local source build above,
Docker Hub names, full image references, and tarball imports from the Images
page continue to work without Harbor.

Use `IMAGE_REGISTRY` only for the Bioinfoflow backend/frontend images consumed by
`docker-compose.prod.yml`. If you mirror those images into Harbor, a typical
operator `.env` looks like:

```env
IMAGE_REGISTRY=10.227.4.56:80/pipeline-dev
IMAGE_TAG=latest
```

Compose then pulls:

- `10.227.4.56:80/pipeline-dev/bioinfoflow-backend:<tag>`
- `10.227.4.56:80/pipeline-dev/bioinfoflow-frontend:<tag>`

If `10.227.4.56:80` is an HTTP registry, configure Docker itself to trust the
insecure registry before pulling. For Docker Engine this is usually
`/etc/docker/daemon.json`; for Docker Desktop, use the Docker Desktop daemon
settings. Restart Docker after changing it.

```json
{
  "insecure-registries": ["10.227.4.56:80"]
}
```

For `IMAGE_REGISTRY`, authenticate the Docker environment used by Bioinfoflow
with your normal Docker credential process, such as `docker login`; do not put
app-image registry passwords in `.env`.

### Workflow Registry Settings

Workflow images use Bioinfoflow's app-level registry settings, not
`IMAGE_REGISTRY`. Open **Settings -> Container Registries** as an owner/admin and
add Harbor like this:

| Field | Value |
| --- | --- |
| Name | `Company Harbor` |
| Endpoint | `http://10.227.4.56:80` |
| Namespace | `pipeline-dev` |
| HTTP | On, because this example endpoint is plain HTTP |
| Default | On, if this should be the global workflow-image default |
| Credentials | Stored credentials, environment variables, or none |

Stored credentials are encrypted and redacted after saving. Use the actual
Harbor user or robot account name, for example `robot$pipeline-dev`, not the
namespace alone. In `AUTH_MODE=team`, stored credentials require a stable
`BIOINFOFLOW_CREDENTIAL_KEY` in `.env`:

```env
BIOINFOFLOW_CREDENTIAL_KEY=<paste the output of openssl rand -hex 32>
```

After adding or changing that value for Docker Compose, recreate the backend
container with the same Compose file set you used to start Bioinfoflow so the
new environment is loaded:

```bash
# Default source-build stack:
docker compose up -d --force-recreate backend

# Production image stack:
docker compose -f docker-compose.prod.yml up -d --force-recreate backend
```

`docker compose restart backend` restarts the existing container and does not
load newly added `.env` variables. Environment credentials are env var names
available to the backend container, such as `BIO_REGISTRY_USER` and
`BIO_REGISTRY_PASSWORD`. Use **No credentials** when the Docker environment is
already authenticated or the registry is public. Use **Test** after saving to
confirm the backend can read the credentials.

During workflow registration, **Image Registry -> Automatic** uses the configured
default for unqualified static workflow images when one exists. Explicit image
hosts, such as `quay.io/...` or `10.227.4.56:80/...`, are kept as written. You can
also choose a configured registry to persist that choice for the workflow.
In team mode, ordinary members cannot manage registries or explicitly select a
registry ID, but automatic prefetch can use the admin-configured default as a
shared platform capability. Project-level registry override is reserved in the
data model for future policy; the current UI exposes a global default and
per-workflow selection.

AgentCore follows the same rule: `images.pull` can pull full image names
directly, automatic/default behavior remains available for unqualified names, and
explicit `registry_id` use is limited to owners/admins in team mode.

For WDL, static task `docker`/`container` references are captured during workflow
registration and missing images are prefetched automatically before MiniWDL
starts. When a configured registry applies, run compilation uses a run-local WDL
copy with those static container literals rewritten to the same resolved image
names. Dynamic container expressions are skipped and resolved at runtime. For
Nextflow, Docker pull is enabled when Docker is available, and Bioinfoflow
injects the configured registry prefix as `docker.registry` for unqualified
process images. You can also use full Harbor image names in the workflow or
pipeline config:

```text
10.227.4.56:80/pipeline-dev/bwa:0.7.17
```

If no registry host is present, Docker keeps its normal default behavior, such as
pulling `ubuntu:22.04` or `biocontainers/fastqc:latest` from Docker Hub. On
the Images page, **Pull from registry -> Automatic** uses the image name exactly
as entered; choosing a configured registry rewrites unqualified image names and
uses its credentials. For offline or restricted sites, **From Tarball** imports a
preloaded `.tar` image and never uses registry settings.

## What Happens At Startup

If `BIOINFOFLOW_HOME` is unset, Compose uses `${PWD}/data`, where `${PWD}` is the repo root for normal local startup.

Compose passes these important values to the backend:

- `BIOINFOFLOW_HOME=${BIOINFOFLOW_HOME:-${PWD}/data}`
- `BIOINFOFLOW_HOME_HOST=${BIOINFOFLOW_HOME:-${PWD}/data}`
- `DATABASE_URL=sqlite+aiosqlite:///${BIOINFOFLOW_HOME:-${PWD}/data}/state/bioinfoflow.db`
- `BETTER_AUTH_DB_PATH=${BIOINFOFLOW_HOME:-${PWD}/data}/state/auth/better-auth.db`

The backend enforces the identity-mount path contract: when `BIOINFOFLOW_HOME_HOST` is set, it must resolve to the same absolute path as `BIOINFOFLOW_HOME`.

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
