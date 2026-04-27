# Bioinfoflow Ship Checklist

Use this before publishing the repo, cutting a release, or putting a demo server in front of real users.

## 1. Repository Readiness

- Confirm the working tree is clean except for intentional release changes:

```bash
git status --short --untracked-files=all
```

- Confirm no secrets are tracked:

```bash
git ls-files | rg '(^|/)\.env$|secret|token|key|credential' || true
```

- Confirm the public repo has a license:

```bash
test -f LICENSE
```

- Confirm the README quick start still matches `.env.example`, `docker-compose.yml`, and `RUNBOOK.md`.

## 2. Local Verification

Backend:

```bash
cd backend
uv sync
uv run ruff check .
uv run pytest
```

Frontend:

```bash
cd frontend
bun install
bun run lint
bun run test
bun run build
```

Workflow fixtures:

```bash
cd backend
uv run miniwdl check ../demo/parabricks-wgs-v470/wdl/wgs_fq_to_vcf.wdl
```

## 3. Docker Verification

Build and start the full stack:

```bash
docker compose up -d --build
docker compose ps
```

Check:

- UI opens at `http://localhost:3000`
- API docs open at `http://localhost:8000/api/v1/docs`
- Owner login works
- `GET /api/v1/system/health` returns a success envelope
- `GET /api/v1/scheduler/status` returns scheduler state

Stop when finished:

```bash
docker compose down
```

## 4. Remote Demo Server Readiness

On the server `.env`, set:

```env
BIOINFOFLOW_HOME=/srv/bioinfoflow
BETTER_AUTH_SECRET=<long-random-secret>
NEXT_PUBLIC_API_BASE_URL=http://YOUR_SERVER_IP:8000/api/v1
BETTER_AUTH_URL=http://YOUR_SERVER_IP:3000
CORS_ORIGINS=["http://YOUR_SERVER_IP:3000"]
TRUSTED_HOSTS=["localhost","127.0.0.1","YOUR_SERVER_IP"]
```

For GPU demos, verify:

```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

Deploy with one of:

```bash
NEXT_PUBLIC_API_BASE_URL=http://YOUR_SERVER_IP:8000/api/v1 ./deploy.sh sync --arch amd64 user@your-server
```

or:

```bash
IMAGE_TAG=v0.1.0 ./deploy.sh release
ssh user@your-server 'cd ~/bioinfoflow && docker compose -f docker-compose.prod.yml pull && docker compose -f docker-compose.prod.yml up -d'
```

## 5. Product Demo Path

Before inviting users, rehearse one clean demo:

1. Sign in as owner.
2. Create a project.
3. Register a small Nextflow or WDL workflow.
4. Submit a run with file inputs selected from the UI.
5. Watch DAG/log/status updates.
6. Open the output artifacts.
7. Run `bif doctor` from the CLI.

For GPU testing, register both Parabricks WGS fixtures and run them with real FASTQ/reference paths on the GPU server.

## 6. Go / No-Go Gate

Ship when:

- README quick start works from a fresh clone.
- Docker Compose starts backend and frontend.
- Owner login works.
- At least one Nextflow or WDL run completes.
- Remote `.env` uses the public server origin, not localhost.
- No tracked secrets exist.
- The demo server is on a trusted network or behind an access layer.

Do not ship publicly if:

- The Docker socket is exposed on an untrusted network.
- `BETTER_AUTH_SECRET` is empty on a shared server.
- The frontend image was built with `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1` for a remote deployment.
- You have not run a full Docker start from a clean `.env`.
