#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap for BioinfoFlow.
#
# Prepares the checked-out repository for local development:
#   - system packages for nested Docker and the agent local sandbox
#   - Nextflow, uv, and bun toolchains
#   - backend Python deps (uv, Python 3.13) + DB migrations
#   - agent sandbox worker Node deps
#   - frontend deps (bun)
#
# The base image already provides git, curl, Java 21, gcc/g++/make, Node 22, and
# passwordless sudo. The Docker daemon itself is started per boot by start.sh.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export DEBIAN_FRONTEND=noninteractive

echo "==> System packages (Docker, fuse-overlayfs, bubblewrap)"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
fi
# fuse-overlayfs lets Docker run nested inside the Cloud Agent VM (overlay-on-overlay).
# bubblewrap backs the agent's local command sandbox.
# The base image's apt/dpkg state emits a harmless "No file name for fuse3"
# metadata error, so verify the binaries directly instead of trusting apt's exit code.
sudo apt-get update -qq || true
sudo apt-get install -y -qq fuse-overlayfs bubblewrap || true
for bin in fuse-overlayfs bwrap; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "ERROR: required binary '$bin' is not available after apt install" >&2
    exit 1
  fi
done

echo "==> Docker daemon config (nested-container storage driver)"
sudo mkdir -p /etc/docker
if [ ! -f /etc/docker/daemon.json ]; then
  printf '%s\n' '{"features": {"containerd-snapshotter": false}, "storage-driver": "fuse-overlayfs"}' \
    | sudo tee /etc/docker/daemon.json >/dev/null
fi
sudo usermod -aG docker "$USER" || true

echo "==> Nextflow"
if ! command -v nextflow >/dev/null 2>&1 && [ ! -x /usr/local/bin/nextflow ]; then
  ( cd /tmp && curl -fsSL https://get.nextflow.io | bash )
  sudo mv /tmp/nextflow /usr/local/bin/nextflow
  sudo chmod +x /usr/local/bin/nextflow
fi

echo "==> uv (Python toolchain)"
if [ ! -x "$HOME/.local/bin/uv" ] && ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

echo "==> bun (frontend toolchain)"
if [ ! -x "$HOME/.bun/bin/bun" ] && ! command -v bun >/dev/null 2>&1; then
  curl -fsSL https://bun.sh/install | bash
fi
export PATH="$HOME/.bun/bin:$PATH"

echo "==> Backend deps + database migrations"
cd "$REPO_ROOT/backend"
uv sync --python 3.13
uv run alembic upgrade head

echo "==> Agent local-sandbox worker deps"
cd "$REPO_ROOT/backend/sandbox_worker"
npm ci

echo "==> Frontend deps"
cd "$REPO_ROOT/frontend"
bun install

echo "==> install.sh complete"
