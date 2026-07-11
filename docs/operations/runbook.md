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

- source-build Compose default when unset: `<repo>/data`
- published-image Compose default when unset: `/srv/bioinfoflow`
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
- Nextflow and MiniWDL executables; the backend image bundles them, while
  `NEXTFLOW_BIN` and `MINIWDL_BIN` override their paths
- one provider configuration for agent use: a hosted-provider credential or a local/compatible endpoint and model, configured in **Settings -> AI Providers** or bootstrapped with environment variables

For Remote Connections, password and pasted-private-key auth are stored
encrypted by Bioinfoflow and used by the backend directly. If you use advanced
SSH config aliases, backend key file paths, or `ssh-agent`, SSH access is
evaluated from the backend environment. Make sure the backend host or backend
container can see the relevant `~/.ssh/config`, key path, or `SSH_AUTH_SOCK`.
Stored provider, registry, and Remote Connection credentials use the same
encryption key. Team deployments must set a stable
`BIOINFOFLOW_CREDENTIAL_KEY`; personal deployments must preserve
`state/credentials/fernet.key` with database backups.

## Scheduler Defaults

- `SCHEDULER_MAX_CONCURRENCY=4`
- resource checks enabled by default

Bioinfoflow always starts the persistent database-backed scheduler. Docker
applies Alembic migrations automatically. Bare-metal deployments must run
`uv run alembic upgrade head`; an outdated schema prevents backend startup.

## Useful Health Checks

- `GET /api/v1/system/health`
- `GET /api/v1/scheduler/status`
- `GET /api/v1/scheduler/resources`
- `GET /api/v1/stats`

## Common Operational Failures

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

## Backup And Restore

Stop or quiesce the services before taking a filesystem copy. The safest backup
is the complete `BIOINFOFLOW_HOME`, which includes the platform SQLite database,
Better Auth database, generated credential key, workflow sources, projects, and
shared source data. Restore it at the same absolute path, then run Alembic
migrations before starting a bare-metal backend. Also back up every
external-local project root outside `BIOINFOFLOW_HOME` and restore it at its
recorded absolute path. Team deployments must preserve the configured
`BIOINFOFLOW_CREDENTIAL_KEY` securely outside the filesystem snapshot. If you
back up selected paths, include at minimum:

- `state/bioinfoflow.db`
- `state/auth/better-auth.db`
- `state/credentials/fernet.key` when it exists
- `state/workflows/`, `projects/`, and `sources/`
