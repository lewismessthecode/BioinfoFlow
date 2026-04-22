#!/bin/bash
set -e

# ── Ensure data directories exist ─────────────────────────────
mkdir -p /data/auth /data/workflows /data/workspaces /data/workdirs/nextflow /data/workdirs/miniwdl

# ── Run database migrations ───────────────────────────────────
echo "Running database migrations..."
/app/.venv/bin/alembic upgrade head

# ── Start server ──────────────────────────────────────────────
echo "Starting Bioinfoflow backend..."
exec "$@"
