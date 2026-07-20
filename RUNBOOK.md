# Bioinfoflow Runbook

This is the canonical runbook for local trials, source development, and shared
deployments.

## Localhost Installer (after the first tagged release)

The release installer is the shortest path from an empty machine to the Agent
workspace. It requires Docker Desktop or Docker Engine with Compose v2 and a
local Unix-socket Docker context.

This branch adds the installer and release packaging, but the repository does
not yet have a `v*` release containing those assets. Until that release exists,
use the [source-build path](#2-build-from-source-with-docker).

When a release includes `install.sh`, `docker-compose.local.yml`, and
`SHA256SUMS`, install it with:

```bash
curl -fsSL https://github.com/lewismessthecode/BioinfoFlow/releases/latest/download/install.sh | sh
```

Do not run the repository copy of `scripts/install.sh` directly: release
packaging embeds the matching version and publishes the checksums it verifies.

The installer pulls the matching `amd64` or `arm64` images, waits for both
services to become healthy, and opens `http://localhost:3000`. A fresh local
workspace opens in the Agent experience with a managed **Bioinfoflow Demo**
project, a registered WDL workflow, and small sample-sheet/FASTQ inputs. Connect
one model in the composer, then choose a short demo starter such as **Check and
run the demo workflow**. Tool approvals still appear before the Agent submits a
run.

The managed paths are deliberately separate:

- `~/.bioinfoflow/install` contains the installer, Compose file, release
  version, and generated environment file.
- `~/.bioinfoflow/data` contains Bioinfoflow state, demo assets, projects, and
  run data.

Lifecycle commands:

```bash
~/.bioinfoflow/install/install.sh --update
~/.bioinfoflow/install/install.sh --uninstall
~/.bioinfoflow/install/install.sh --purge
```

`--uninstall` removes the containers and managed control files but preserves
`~/.bioinfoflow/data`. `--purge` removes both control files and managed data.
Both commands first confirm that the managed Compose stack stopped through the
same normalized local Unix socket recorded at installation. If Docker, the
daemon, Compose, or that socket is unavailable—or `compose down` fails—the
command exits without removing control files or data. Restore the installation's
Docker context and retry.

If you already uninstalled and later decide to remove the preserved data, no
running managed stack remains, so you can fetch a published installer again and
pass `--purge` even when Docker is unavailable:

```bash
curl -fsSL https://github.com/lewismessthecode/BioinfoFlow/releases/latest/download/install.sh | sh -s -- --purge
```

The localhost stack binds the UI and API to `127.0.0.1` and intentionally runs
with authentication disabled. The API port is fixed at `8000` because the
published localhost frontend is built against that origin; installation stops
if port 8000 is occupied. It is for one trusted local machine, not a shared
server, reverse proxy, or port-forwarded deployment. It also mounts the local
Docker socket so the Agent and workflow runtime can launch containers. See
[Security Notes](docs/security.md) before changing that boundary.

If you only remember one rule, remember this:

> Edit the repo-root `.env`. That is the default config source for Docker and local development.

## 1. Environment Variables: One Rule, Not Three

### Default

Use exactly one file by default:

```bash
cp .env.example .env
```

Then edit `.env`.

### Optional overrides

These files are now optional escape hatches, not required setup steps:

- `backend/.env`
  Use only when one machine needs backend-only overrides such as local runner paths.
- `frontend/.env.local`
  Use only when one machine needs frontend-only overrides.

### Precedence

The effective order is:

1. Shell-exported environment variables
2. Package-local override file
   `backend/.env` for backend commands
   `frontend/.env.local` for frontend commands
3. Repo-root `.env`
4. Code defaults

### What most users should do

Do not create extra env files unless you have a specific reason.

For almost everyone, this is enough:

```bash
cp .env.example .env
```

For the local source-build Compose stack, leave `BIOINFOFLOW_HOME` unset unless
you want the data root outside this repo. Then set at least:

```env
AUTH_BOOTSTRAP_OWNER_EMAIL=admin@example.com
AUTH_BOOTSTRAP_OWNER_PASSWORD=change-me
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
BETTER_AUTH_URL=http://localhost:3000
```

After first sign-in, configure the agent under **Settings -> AI Providers**.
Hosted providers only need an API key; Ollama, vLLM, OpenRouter, and generic
OpenAI-compatible endpoints can be configured from the same page. Environment
variables such as `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`,
`DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`, `XAI_API_KEY`, `GROK_API_KEY`,
`GROQ_API_KEY`, `KIMI_API_KEY` for Kimi global, `KIMI_CN_API_KEY`,
`MOONSHOT_CN_API_KEY`, or legacy `MOONSHOT_API_KEY` for Kimi China,
`DASHSCOPE_API_KEY`, `QWEN_API_KEY`,
`MISTRAL_API_KEY`, `COHERE_API_KEY`, `TOGETHER_API_KEY`, `FIREWORKS_API_KEY`,
and `PERPLEXITY_API_KEY` are optional hosted-provider bootstrap defaults for
fresh/headless deployments. Advanced local and gateway defaults use variables
such as `OLLAMA_BASE_URL`, `VLLM_BASE_URL`,
`VLLM_API_KEY`, `VLLM_MODEL`, `OPENAI_COMPATIBLE_BASE_URL`,
`OPENAI_COMPATIBLE_API_KEY`, and `OPENAI_COMPATIBLE_MODEL`. UI-saved
configuration takes precedence. In `AUTH_MODE=team`,
provider keys saved through the UI as stored credentials also require
`BIOINFOFLOW_CREDENTIAL_KEY`; environment bootstrap keys do not.

Bootstrap owner credentials are processed whenever they remain configured: the
frontend ensures the email is an active owner and updates its password. After
verifying a long-lived shared deployment, remove the bootstrap password unless
automatic owner recovery is intentional.

For localhost Docker, `BETTER_AUTH_SECRET` may stay empty. Bioinfoflow creates a persistent local secret under `BIOINFOFLOW_HOME/state/auth` on first startup. For shared or remote deployments, generate one with `openssl rand -base64 32` and set `BETTER_AUTH_SECRET` explicitly.

Optional data-root override:

```env
BIOINFOFLOW_HOME=/absolute/path/to/bioinfoflow-data
```

For any shared or production deployment, also set:

```env
TRUSTED_HOSTS=["localhost","127.0.0.1","YOUR_SERVER_IP_OR_DOMAIN"]
```

## 2. Build From Source With Docker

### Prerequisites

- Docker Desktop or Docker Engine with Compose
- At least one AI provider. Hosted providers use an API key; Ollama, vLLM, and OpenAI-compatible services can use an endpoint and model without a key when the service permits it.

### First run

```bash
cp .env.example .env
# edit .env: owner credentials; provider keys can be added in the UI
docker compose up -d --build
```

Open:

- UI: `http://localhost:3000`
- API docs: `http://localhost:8000/api/v1/docs`

Sign in with:

- `AUTH_BOOTSTRAP_OWNER_EMAIL`
- `AUTH_BOOTSTRAP_OWNER_PASSWORD`

### Docker notes

- `NEXT_PUBLIC_API_BASE_URL` is baked into the frontend at build time.
- If you change any `NEXT_PUBLIC_*` value, rebuild:

```bash
docker compose up -d --build
```

- `BIOINFOFLOW_HOME` is identity-mounted into the same absolute path on host and in containers.
- If you leave `BIOINFOFLOW_HOME` unset, the source-build Compose stack defaults to this repo's `data/` directory; the published-image stack defaults to `/srv/bioinfoflow`.
- The backend creates the required platform subdirectories on startup.
- GPU detection is automatic only after the host GPU has been exposed into the backend container. Bioinfoflow will not enable Docker GPU passthrough on its own.

### Optional GPU enablement

Keep the base stack CPU-safe by default. On a GPU host, opt in with the compose override:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

For published images:

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml pull
docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml up -d
```

What this does:

- requests `gpus: all` for the backend container
- exposes NVIDIA utility/compute capabilities so readiness checks can see `nvidia-smi`
- keeps CPU-only hosts working because the override is never loaded unless you ask for it

What it does not do:

- it does not manufacture GPU access if the host lacks the NVIDIA Container Toolkit
- it does not make GPU a required readiness item
- it does not change your workflow routing unless the host runtime is genuinely available

If the server has NVIDIA GPUs but the readiness drawer still says the backend cannot see them, verify:

- `nvidia-smi` works on the host
- Docker has the NVIDIA runtime / toolkit installed
- you started Compose with `-f docker-compose.gpu.yml`
- you rebuilt or restarted the backend container after enabling the override

### Fast localhost run with published images

Use this path when you want to try the latest formal release without building images locally:

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

Formal images are published by `.github/workflows/release-please.yml` after a
Release Please PR is intentionally merged. Development images are published by
`.github/workflows/container-release.yml` after eligible changes reach `main`.
The stack uses:

- `ghcr.io/lewismessthecode/bioinfoflow-backend:<tag>`
- `ghcr.io/lewismessthecode/bioinfoflow-frontend:<tag>`

Formal tags are exact numeric versions such as `0.1.0`, minor aliases such as
`0.1`, major aliases such as `0`, and `latest`. Development tags are `main` and
`sha-<12-char-commit>`. Pin both services to the same exact numeric version for
reproducible deployments.

The published frontend image is fixed at build time to the localhost API URL,
personal auth mode, local email/password auth, and disabled self-signup. For a
shared or remote URL, team mode, or different public auth settings, configure
`.env` and run the source-build command instead:

```bash
docker compose up -d --build
```

### Optional container registry / Harbor

Harbor is optional. Bioinfoflow still works with source builds, Docker Hub image
names, full image names such as `ghcr.io/org/tool:tag` or `quay.io/org/tool:tag`,
and image tarball imports from the Images page.

Use `IMAGE_REGISTRY` only when you want `docker-compose.prod.yml` to pull the
Bioinfoflow backend/frontend images from a registry namespace you operate. For
example, after mirroring the two Bioinfoflow images into Harbor:

```env
IMAGE_REGISTRY=10.227.4.56:80/pipeline-dev
IMAGE_TAG=latest
```

That makes Compose pull:

- `10.227.4.56:80/pipeline-dev/bioinfoflow-backend:<tag>`
- `10.227.4.56:80/pipeline-dev/bioinfoflow-frontend:<tag>`

If Harbor is served over plain HTTP, configure Docker's insecure registries on
the host or Docker Desktop before starting Bioinfoflow. This is outside
Bioinfoflow configuration. For `IMAGE_REGISTRY`, use Docker's normal credential
store or `docker login`; do not put app-image registry passwords in `.env`.

```json
{
  "insecure-registries": ["10.227.4.56:80"]
}
```

#### Workflow container registry settings

Workflow container registries are configured in the app, not through
`IMAGE_REGISTRY`. In team mode, owners and admins can open **Settings ->
Container Registries** and add Harbor or another OCI registry:

- **Endpoint**: `http://10.227.4.56:80`
- **Namespace**: `pipeline-dev`
- **HTTP**: enabled when the endpoint is plain HTTP
- **Default**: enabled to make this the global workflow-image default
- **Credentials**: `Stored credentials`, `Environment variables`, or
  `No credentials`

For stored credentials, enter the actual Harbor user or robot account name, for
example `robot$pipeline-dev`, plus its password/token. Bioinfoflow encrypts
stored values and only shows hints after saving. In `AUTH_MODE=team`, stored
credentials require a stable `BIOINFOFLOW_CREDENTIAL_KEY` in `.env`:

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
load newly added `.env` variables. For environment credentials, enter the env
var names that the backend container can read, for example `BIO_REGISTRY_USER`
and `BIO_REGISTRY_PASSWORD`. Use **No credentials** when the Docker environment
is already authenticated or the registry is public. Use **Test** to confirm
credentials are available.

During workflow registration, the **Image Registry** selector is optional:

- **Automatic** uses the global default registry for unqualified static workflow
  images when one is configured. Explicit image hosts such as `quay.io/...` or
  `10.227.4.56:80/...` are not rewritten.
- Choosing a configured registry stores that workflow's registry choice and uses
  it for registration-time prefetch.
- If no registry is configured, Docker Hub/default Docker behavior remains in
  place.

In team mode, ordinary members cannot manage registries or explicitly select a
registry ID. They can still register workflows; automatic prefetch may use the
admin-configured global default as a shared platform capability.

AgentCore image pulls use the same platform policy. The `images.pull` tool can
pull a full image name directly, and automatic/default registry behavior remains
available for unqualified names. Passing an explicit `registry_id` is treated
like choosing a configured registry in the UI and is limited to owners/admins in
team mode.

The data model includes a project-level registry override for future policy, but
the current UI exposes a global default plus per-workflow selection.

For WDL, Bioinfoflow records static task `docker`/`container` images when the
workflow is registered and prefetches missing required images before MiniWDL
starts. When a configured registry applies, run compilation also uses a
run-local WDL copy with those static container literals rewritten to the same
resolved image names, so prefetch and execution agree. Dynamic container
expressions are skipped and resolved at runtime. For Nextflow, Bioinfoflow
enables Docker pull behavior when Docker is available and injects the configured
registry prefix as `docker.registry` for unqualified process images. You can also
write full Harbor image names directly in workflows:

```text
10.227.4.56:80/pipeline-dev/bwa:0.7.17
```

On the Images page, **Pull from registry** has its own optional registry
selector. **Automatic** pulls the image name exactly as entered; choosing a
configured registry rewrites unqualified names through that registry and supplies
its credentials. **From Tarball** is unchanged and never uses registry settings.

## 3. Local Development

### Prerequisites

- Python 3.13+
- `uv`
- Bun
- Docker daemon if you want Docker-backed workflow execution
- Nextflow installed if you want Nextflow runs
- MiniWDL installed if you want WDL runs

### Backend

The backend now auto-reads the repo-root `.env`.

```bash
cp .env.example .env
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --reload-dir app --port 8000
```

The backend reads `.env` at process startup. Its app-only reload watcher does
not watch the repo-root `.env`, so stop and restart Uvicorn after changing that
file. Otherwise the frontend and backend can run with different auth modes and
API requests will return `401 Unauthorized`.

If this machine has runner paths that should not live in the shared `.env`, create `backend/.env` and only put overrides there:

```env
NEXTFLOW_BIN=/absolute/path/to/nextflow
MINIWDL_BIN=/absolute/path/to/miniwdl
```

### Frontend

The frontend now auto-loads the repo-root `.env` too.

```bash
cd frontend
bun install
bun run dev
```

Restart the frontend after changing `.env`. Any `NEXT_PUBLIC_*` value is loaded
when the frontend starts or builds and will not update in an already running
process.

Open:

- UI: `http://localhost:3000`

If you truly need a frontend-only override, create `frontend/.env.local`.

### CLI

```bash
cd backend
uv run bif --version                   # bif 0.1.0
uv run bif --help                      # also -h
uv run bif doctor                      # backend + scheduler + GPU + local tool checks
uv run bif config init                 # write ~/.config/bioinfoflow/cli.toml
uv run bif config use-project proj-1   # set default project (also $BIOFLOW_PROJECT)
uv run bif config set base_url http://localhost:8000/api/v1
uv run bif --output json project list  # machine-readable envelope on stdout
```

`bif` follows POSIX conventions: `-h/--help`, `-V/--version`, `-p/--project`, `-q/--quiet`. Settings resolve as CLI flag → env (`BIOFLOW_*`) → `~/.config/bioinfoflow/cli.toml` → default. Destructive commands (`run cancel`, `run cleanup`, `run batch cancel`, `project delete`, `file rm`) confirm interactively unless you pass `--force/-f`. Exit codes: `0` ok, `1` general, `2` usage, `3` backend, `4` connection.

### Agent permissions and approvals

The Agent composer permission control changes approval policy for the selected
local or remote target. It does not grant operating-system privileges.

- **Request approval** asks before each non-read side effect.
- **Approve for me** allows reads and low-risk actions, and asks for elevated
  risk.
- **Full access** skips ordinary risk prompts, but catastrophic commands remain
  blocked, protected-resource writes still ask, and user questions or plan
  approval remain interactive.

Permission changes are live for the next tool authorization, even when a turn is
already active. If tools are already waiting, the confirmation offers:

- **Future operations only**: update the policy and leave existing approvals
  waiting. This is the default and the behavior for API clients that omit
  `pending_strategy`.
- **Approve waiting tools too**: atomically update the policy and approve
  eligible waiting tools. User questions and plan approval are excluded, and
  the response reports affected, excluded, and already-resolved counts.

Local and remote targets have different authority boundaries. An enabled local
OS sandbox can enforce filesystem and network limits independently of the
permission mode. SSH commands have the configured remote account's privileges;
the remote root is only a working directory and risk-analysis hint, not
confinement.

For API automation, session updates accept:

```json
{
  "permission_mode": "bypass",
  "pending_strategy": "future_only"
}
```

Use `approve_pending_tools` only when the caller intentionally wants to approve
the currently waiting eligible tool actions as part of the same update.

## 4. Minimal Local Setup Checklist

For the smallest working local setup:

1. Copy `.env.example` to `.env`
2. Set owner credentials and, optionally, one LLM API key
3. Run backend migrations
4. Start backend
5. Start frontend

Commands:

```bash
cp .env.example .env

cd backend
uv sync
uv run alembic upgrade head

cd ../frontend
bun install
```

Then in two terminals:

```bash
cd backend && uv run uvicorn app.main:app --reload --reload-dir app --port 8000
cd frontend && bun run dev
```

### Configure common AI providers

Use **Settings -> AI Providers** as the primary setup path. Hosted providers such
as OpenAI, Anthropic, Gemini, DeepSeek, xAI/Grok, Groq, OpenRouter, Kimi,
Kimi China, Qwen, Mistral, Cohere, Together AI, Fireworks AI, and Perplexity are
key-first: choose the provider, paste the API key, save, then refresh or
auto-discover models.

For local or gateway deployments, use the dedicated **Ollama** or **vLLM**
templates when possible. Use **OpenAI Compatible** for LM Studio, private
gateways, or providers not yet listed in the catalog. OpenAI-compatible endpoint
URLs normally include the API root that serves `/models` and
`/chat/completions`; manual model IDs are only a fallback when discovery is not
available.

Plain public `http://` provider endpoints are disabled by default because API
keys and prompts would travel without TLS. If a trusted test gateway only speaks
plain HTTP, enable **Allow insecure HTTP** for that provider explicitly.

### Validate an OpenAI-compatible Responses relay

In **Settings -> AI Providers**, configure **OpenAI Compatible** with the API
root URL (normally ending in `/v1`, not `/responses`), select **Responses**, add
the model ID, and save. Plain HTTP endpoints require the explicit **Allow
insecure HTTP** switch because API keys and prompts otherwise travel without
TLS. Save, model discovery, and the model-specific connection test are separate
actions.

In `AUTH_MODE=team`, server environment credentials and localhost/private or
internal provider endpoints are restricted to owner/admin roles because they
cross the backend host trust boundary. Team members can use stored credentials
with public provider endpoints. Personal and development modes keep local relay,
Ollama, and vLLM workflows available.

For a backend end-to-end smoke test, export the relay configuration without
placing the key value on the command line:

```bash
export BIOINFOFLOW_RELAY_BASE_URL=http://relay.example:8079/v1
export BIOINFOFLOW_RELAY_MODEL=gpt-5.4-mini
export BIOINFOFLOW_RELAY_ALLOW_INSECURE_HTTP=1  # omit for HTTPS
read -rsp "Relay API key: " BIOINFOFLOW_RELAY_API_KEY && echo
export BIOINFOFLOW_RELAY_API_KEY

cd backend
BIOINFOFLOW_LIVE_RELAY=1 uv run pytest \
  tests/integration/test_live_responses_relay.py -m live_relay -q \
  --show-capture=no
```

The smoke test uses the same encrypted credential, catalog selection,
AgentCore, LiteLLM Responses, transcript, and event-ledger path as a normal
agent turn. Some relays expose Responses while returning no capacity for Chat
Completions; choose the protocol the relay actually supports.

## 5. Common Friction Points

### Frontend cannot reach backend

Check:

- `.env` contains `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1`
- the backend is actually listening on port `8000`
- if you changed `NEXT_PUBLIC_*`, you restarted `bun run dev` or rebuilt Docker

### Login or callback origin errors

Check:

- `BETTER_AUTH_URL` matches the browser origin exactly
- `CORS_ORIGINS` includes the frontend URL
- `TRUSTED_HOSTS` includes the backend hostname or IP you are using

Typical local values:

```env
BETTER_AUTH_URL=http://localhost:3000
CORS_ORIGINS=["http://localhost:3000"]
TRUSTED_HOSTS=["localhost","127.0.0.1"]
```

### Schema drift or SQLite errors on backend startup

Run:

```bash
cd backend
uv run alembic current
uv run alembic upgrade head
```

### Run submission fails before queueing

Check:

- `NEXTFLOW_BIN` exists if you are running Nextflow workflows
- `MINIWDL_BIN` exists if you are running WDL workflows
- Docker daemon is available when the workflow path requires it

### Permission changed but approval cards remain

This is expected when the update used the default `future_only` strategy. The
new policy applies to tool authorizations that begin after the update; existing
waiting actions remain explicit audit decisions. Change the mode again and
choose **Approve waiting tools too**, or approve/reject each card independently.

If a newly proposed action still uses an older policy, inspect the session's
`permission_policy_version` and the action's `evaluated_policy_version` and
`permission_context_snapshot`. The action should record the version that was
current when it was evaluated. For SSH actions, also confirm that the selected
connection and remote identity in the snapshot match the intended host.

### Docker deployment works locally but not on a server

Most common cause:

- frontend was built with the wrong `NEXT_PUBLIC_API_BASE_URL`

Before remote builds, set:

```bash
export NEXT_PUBLIC_API_BASE_URL=http://YOUR_SERVER_IP:8000/api/v1
```

For access outside a trusted localhost environment, terminate TLS at a reverse
proxy, use matching `https://` values for public URLs and CORS, and do not expose
ports 3000 and 8000 directly to untrusted networks.

## 6. Useful Health Checks

- `http://localhost:8000/api/v1/docs`
- `http://localhost:8000/api/v1/openapi.json`
- `GET /api/v1/system/health`
- `GET /api/v1/scheduler/status`
- `GET /api/v1/scheduler/resources`

## 7. Backup And Restore

Before filesystem backups, stop or quiesce the services. Prefer backing up the
complete `BIOINFOFLOW_HOME`. A selective backup must include both SQLite
databases, `state/credentials/fernet.key` when present, workflow sources,
projects, and shared sources. Back up every external-local project root outside
`BIOINFOFLOW_HOME`, and preserve a team deployment's configured
`BIOINFOFLOW_CREDENTIAL_KEY` securely outside the filesystem snapshot. Restore
the platform root and external project roots at their recorded absolute paths,
then apply Alembic migrations before starting a bare-metal backend. See the
[operations supplement](docs/operations/runbook.md#backup-and-restore).

## 8. File Map

- `README.md`
  Product overview and high-level positioning
- `RUNBOOK.md`
  Canonical setup and troubleshooting guide
- `backend/README.md`
  Backend-focused notes
