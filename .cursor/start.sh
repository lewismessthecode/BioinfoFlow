#!/usr/bin/env bash
# Per-boot runtime reconciliation for BioinfoFlow.
#
# Starts the Docker daemon (nested DinD) so the backend can launch workflow and
# agent-sandbox containers, then makes the socket usable by the non-root user
# that runs the backend. Idempotent: a healthy daemon is left untouched.
set -euo pipefail

if sudo docker info >/dev/null 2>&1; then
  echo "==> Docker daemon already running"
else
  echo "==> Starting Docker daemon (fuse-overlayfs storage driver)"
  sudo rm -f /var/run/docker.pid
  sudo nohup dockerd >/tmp/dockerd.log 2>&1 &
  for _ in $(seq 1 30); do
    if sudo docker info >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  if ! sudo docker info >/dev/null 2>&1; then
    echo "ERROR: Docker daemon did not become ready; see /tmp/dockerd.log" >&2
    exit 1
  fi
fi

# Allow the backend (running as the non-root user) to reach the daemon.
sudo chmod 666 /var/run/docker.sock || true
echo "==> start.sh complete"
