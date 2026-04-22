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

## Path Contract v3

Identity mount invariant:

- `BIOINFOFLOW_HOME_HOST == BIOINFOFLOW_HOME`

Examples:

- local Docker default: `/srv/bioinfoflow`
- HPC: `/lustre/<user>/bpiper`
- cloud: `/mnt/efs/bpiper`
- macOS local dev: `/Users/<you>/bpiper-data`

Docker Compose bind-mounts:

```yaml
- ${BIOINFOFLOW_HOME}:${BIOINFOFLOW_HOME}
```

That keeps the same absolute path visible on the host and inside containers.

## Required Operational Inputs

- Docker daemon
- `NEXTFLOW_BIN` for Nextflow execution
- `MINIWDL_BIN` for WDL execution
- one provider credential such as `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or `GEMINI_API_KEY`

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
