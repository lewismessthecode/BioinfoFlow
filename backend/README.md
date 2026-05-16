# Bioinfoflow Backend

## Local development

The canonical setup guide is [`../RUNBOOK.md`](../RUNBOOK.md).

The backend now reads the repo-root `.env` by default. Only create `backend/.env`
if you need backend-only overrides on one machine.

```bash
cd ..
cp .env.example .env
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --reload-dir app --port 8000
```

If startup fails with a schema message or SQLite errors like
`no such column: projects.is_default`, the local database is behind the code.
From `backend/`, run:

```bash
uv run alembic current
uv run alembic upgrade head
sqlite3 bioinfoflow.db "PRAGMA table_info(projects);"
```

The final command should show an `is_default` column on `projects`.

Open the API docs at `http://localhost:8000/api/v1/docs`.
If you access the backend through a non-local hostname or IP, add it to
`TRUSTED_HOSTS` first or requests will be rejected with `Invalid host header`.

## Environment configuration

Default:

- edit the repo-root `.env`

Optional backend-only override:

- create `backend/.env`

Key backend settings:

- `DATABASE_URL` (SQLite MVP by default; relative SQLite paths resolve against `backend/`)
- `BIOINFOFLOW_HOME` (single platform root; defaults to repo-local `data/`)
- `NEXTFLOW_BIN`, `MINIWDL_BIN`
- `DOCKER_SOCKET`
- `CORS_ORIGINS`
- `TRUSTED_HOSTS`
- `BETTER_AUTH_SECRET` (required for shared or production deployments)
- `AGENT_OBSERVABILITY` (enable tool/prompt logs)
- `LANGSMITH_TRACING` + `LANGSMITH_API_KEY` (optional tracing)

## Installing workflow runners

You must install Nextflow and MiniWDL on the host and point `NEXTFLOW_BIN` / `MINIWDL_BIN`
to the correct paths in the repo-root `.env` or, if you prefer a machine-local
override, in `backend/.env`.

### Nextflow

```bash
curl -s https://get.nextflow.io | bash
mkdir -p ~/.local/bin
mv nextflow ~/.local/bin/nextflow
```

Set the path in `.env` or `backend/.env`:

```bash
NEXTFLOW_BIN=$HOME/.local/bin/nextflow
```

### MiniWDL (via uv)

```bash
cd backend
uv add miniwdl
```

Then update `.env` or `backend/.env`:

```bash
MINIWDL_BIN=$HOME/.local/bin/miniwdl
```

If the `miniwdl` executable is not on your PATH, you can also point to it directly inside
the uv virtual environment. Example (adjust the python version if needed):

```bash
MINIWDL_BIN=backend/.venv/bin/miniwdl
```

## Docker Compose (local dev container)

```bash
docker compose up --build
```

The container exposes the API at `http://localhost:8000/api/v1/docs`.

Notes:
- Bioinfoflow uses a single home root. With Docker Compose, leaving `BIOINFOFLOW_HOME` unset mounts this repo's `data/` directory at the same absolute path inside the containers.
- Managed projects live under `projects/<project_id>/data` and `projects/<project_id>/runs`.
- Put project-private manifests or small helper files into `Project Data` via the in-app upload flow.
- Put upstream-delivered input files under `./data/sources/deliveries/...`.
- Put references and indexes under `./data/sources/reference/...`.
- The Docker socket is mounted to enable image inspection and pulls.
- Nextflow/MiniWDL binaries must be available inside the container if you plan to execute workflows.

### Input Placement Rules

Use these rules consistently:

- raw upstream inputs like `fq`, `bam`, `vcf`: put them in `Deliveries`
- project-private manifests like `sequence.list`: keep them in `Project Data`
- references and indexes: keep them in `Reference Library`

For example, on a Docker Compose host:

```bash
mkdir -p data/sources/deliveries/deaf20-run
cp /incoming/*.fastq.gz data/sources/deliveries/deaf20-run/
```

Then build or upload `sequence.list` from the UI into the current project's `Project Data`.

Manifest files may contain:

- `asset://deliveries/...`
- `asset://project/...`
- `asset://reference/...`

During run submission, Bioinfoflow materializes that manifest into `runs/<run_id>/submission/manifest.materialized/` and rewrites the entries to runtime paths automatically.

## Tests

```bash
uv run pytest
```
