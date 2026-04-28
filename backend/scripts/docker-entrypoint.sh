#!/bin/bash
set -e

redact_url() {
  local value="${1:-}"
  if [[ "$value" == *"://"* && "$value" == *"@"* ]]; then
    local scheme="${value%%://*}"
    local rest="${value#*://}"
    local host="${rest#*@}"
    local credentials="${rest%@*}"
    local user="${credentials%%:*}"
    echo "${scheme}://${user}:***@${host}"
    return
  fi
  echo "$value"
}

# ── Startup context ───────────────────────────────────────────
echo "Bioinfoflow backend container startup"
echo "  BIOINFOFLOW_HOME=${BIOINFOFLOW_HOME:-/srv/bioinfoflow}"
echo "  BIOINFOFLOW_HOME_HOST=${BIOINFOFLOW_HOME_HOST:-}"
echo "  DATABASE_URL=$(redact_url "${DATABASE_URL:-sqlite+aiosqlite:///\${BIOINFOFLOW_HOME}/state/bioinfoflow.db}")"
echo "  BETTER_AUTH_DB_PATH=${BETTER_AUTH_DB_PATH:-\${BIOINFOFLOW_HOME}/state/auth/better-auth.db}"
echo "  DOCKER_SOCKET=${DOCKER_SOCKET:-unix:///var/run/docker.sock}"
echo "  NEXTFLOW_BIN=${NEXTFLOW_BIN:-/usr/local/bin/nextflow}"
echo "  MINIWDL_BIN=${MINIWDL_BIN:-/usr/local/bin/miniwdl}"

# ── Ensure data directories exist ─────────────────────────────
mkdir -p \
  "${BIOINFOFLOW_HOME:-/srv/bioinfoflow}/state/auth" \
  "${BIOINFOFLOW_HOME:-/srv/bioinfoflow}/state/workflows" \
  "${BIOINFOFLOW_HOME:-/srv/bioinfoflow}/projects" \
  "${BIOINFOFLOW_HOME:-/srv/bioinfoflow}/state/engine/cache/nextflow" \
  "${BIOINFOFLOW_HOME:-/srv/bioinfoflow}/state/engine/cache/miniwdl"

# ── Run database migrations ───────────────────────────────────
echo "Running database migrations..."
/app/.venv/bin/alembic upgrade head

# ── Start server ──────────────────────────────────────────────
echo "Starting Bioinfoflow backend..."
exec "$@"
