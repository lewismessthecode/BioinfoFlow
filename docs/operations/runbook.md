# Operations Runbook Supplement

The canonical user-facing runbook is [`/RUNBOOK.md`](../../RUNBOOK.md).

This page keeps the operations-specific context that is useful once the base
setup already works.

## Environment Source Of Truth

Default rule:

- use the repo-root `.env`

Optional overrides:

- `backend/.env` for backend-only machine-local overrides
- `frontend/.env.local` for frontend-only machine-local overrides

Precedence:

1. shell env
2. package-local override
3. repo-root `.env`
4. code defaults

## Identity-Mount Path Contract

Identity mount invariant:

- `BIOINFOFLOW_HOME_HOST == BIOINFOFLOW_HOME`

Examples:

- local Docker default when unset: `<repo>/data`
- Linux server: `/srv/bioinfoflow`
- HPC: `/lustre/<user>/bioinfoflow`
- cloud: `/mnt/efs/bioinfoflow`
- macOS local dev: `/Users/<you>/bioinfoflow-data`

Docker Compose bind-mounts:

```yaml
- ${BIOINFOFLOW_HOME:-${PWD}/data}:${BIOINFOFLOW_HOME:-${PWD}/data}
```

That keeps the same absolute path visible on the host and inside containers.

## Required Operational Inputs

- Docker daemon
- `NEXTFLOW_BIN` for Nextflow execution
- `MINIWDL_BIN` for WDL execution
- one provider credential for agent use, configured in **Settings -> AI Providers** or bootstrapped with env vars such as `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, or `VLLM_BASE_URL` + `VLLM_MODEL`

For Remote Connections, password and pasted-private-key auth are stored
encrypted by Bioinfoflow and used by the backend directly. If you use advanced
SSH config aliases, backend key file paths, or `ssh-agent`, SSH access is
evaluated from the backend environment. Make sure the backend host or backend
container can see the relevant `~/.ssh/config`, key path, or `SSH_AUTH_SOCK`.

## Scheduler Defaults

- `RUN_SCHEDULER_MODE=persistent`
- `SCHEDULER_MAX_CONCURRENCY=4`
- resource checks enabled by default

Operational expectation:

- apply Alembic migrations before backend startup if you want the persistent scheduler path

## Useful Health Checks

- `GET /api/v1/system/health`
- `GET /api/v1/scheduler/status`
- `GET /api/v1/scheduler/resources`
- `GET /api/v1/stats`

## Common Operational Failures

### Scheduler falls back unexpectedly

Check:

- migrations are applied
- `RUN_SCHEDULER_MODE=persistent`
- backend logs for scheduler fallback warnings

### Backend starts but schema is behind

Run:

```bash
cd backend
uv run alembic current
uv run alembic upgrade head
```

### Frontend build points to the wrong backend

`NEXT_PUBLIC_API_BASE_URL` is build-time configuration.

For Docker or remote image builds, rebuild after changing it:

```bash
docker compose up -d --build
```

### Remote connection tests fail from the UI

Check the backend environment, not the browser machine:

- password or pasted private key auth uses the backend's built-in SSH client and
  encrypted stored credentials
- Advanced SSH config aliases require `~/.ssh/config` for the backend user
- Advanced backend key paths must be visible inside the backend container
- Advanced backend ssh-agent auth requires `SSH_AUTH_SOCK` to be mounted and set
- Advanced backend SSH methods require system `ssh` and a target host that
  accepts non-interactive `BatchMode=yes` SSH commands
