#!/bin/bash
set -euo pipefail

# ============================================================
# Bioinfoflow Deploy Script
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

IMAGE_TAG="${IMAGE_TAG:-latest}"
DEFAULT_ARCH="amd64"
ARCH="${DEFAULT_ARCH}"
declare -a REMAINING_ARGS=()
BACKEND_IMAGE="bioinfoflow-backend:${IMAGE_TAG}"
FRONTEND_IMAGE="bioinfoflow-frontend:${IMAGE_TAG}"

# ── Colors ─────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}▸${NC} $*"; }
ok()    { echo -e "${GREEN}✓${NC} $*"; }
warn()  { echo -e "${YELLOW}⚠${NC} $*"; }
fail()  { echo "Error: $*" >&2; exit 1; }

platform_for_arch() {
    case "$1" in
        amd64) echo "linux/amd64" ;;
        arm64) echo "linux/arm64" ;;
        *) fail "Unsupported arch '$1'. Use --arch amd64 or --arch arm64." ;;
    esac
}

require_buildx() {
    docker buildx version >/dev/null 2>&1 || fail "Docker Buildx is required. Install/enable Buildx and try again."
}

require_ghcr_user() {
    [[ -n "${GHCR_USER:-}" ]] || fail "Set GHCR_USER to your GitHub username or organization before using push/release."
}

frontend_build_args=()
frontend_build_args+=(--build-arg "NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL:-http://localhost:8000/api/v1}")
frontend_build_args+=(--build-arg "NEXT_PUBLIC_AUTH_MODE=${AUTH_MODE:-personal}")
frontend_build_args+=(--build-arg "NEXT_PUBLIC_AUTH_LOCAL_ENABLED=${AUTH_LOCAL_ENABLED:-true}")
frontend_build_args+=(--build-arg "NEXT_PUBLIC_AUTH_SELF_SIGNUP_ENABLED=${AUTH_SELF_SIGNUP_ENABLED:-false}")

print_help() {
    cat <<EOF
Bioinfoflow Deploy

Usage:
  $0 build   [--arch amd64|arm64]
  $0 push    [--arch amd64|arm64]
  $0 sync    [--arch amd64|arm64] user@server [remote_dir]
  $0 setup   user@server [remote_dir]
  $0 release

Commands:
  build     Build backend + frontend images locally for one Linux architecture.
            Uses Docker Buildx and loads the result into the local Docker image store.

  push      Build one architecture and push architecture-specific tags to GHCR.
            Example tags:
              ghcr.io/<GHCR_USER>/bioinfoflow-backend:${IMAGE_TAG}-amd64
              ghcr.io/<GHCR_USER>/bioinfoflow-frontend:${IMAGE_TAG}-amd64

  sync      Offline deployment flow.
            Builds one architecture locally, saves images to a tarball, copies them
            to the server, loads them remotely, and starts docker compose.

  setup     Copy docker-compose.prod.yml and .env.example to the server.

  release   Build and push a multi-architecture GHCR release for BOTH:
              linux/amd64
              linux/arm64
            This publishes canonical tags without an architecture suffix.

Architecture options:
  --arch amd64   Build for x86_64 Linux servers (default)
  --arch arm64   Build for ARM64 Linux servers

Examples:
  $0 build --arch amd64
  $0 sync --arch amd64 user@server
  $0 push --arch arm64
  GHCR_USER=your-github-user IMAGE_TAG=v1.0.0 $0 release

Environment variables:
  IMAGE_TAG=latest           Image tag to build/push (default: latest)
  GHCR_USER=<github-user>    Required for push/release
  NEXT_PUBLIC_API_BASE_URL   Frontend build arg override
  AUTH_MODE                  Frontend build arg override
  AUTH_LOCAL_ENABLED         Frontend build arg override
  AUTH_SELF_SIGNUP_ENABLED   Frontend build arg override

GHCR setup:
  1. Create a GitHub Personal Access Token (classic) with:
       - write:packages
       - read:packages
       - optional: delete:packages

  2. Log in locally before push/release:
       export GHCR_USER=<your-github-user-or-org>
       export GHCR_TOKEN=<your-github-token>
       echo "\$GHCR_TOKEN" | docker login ghcr.io -u "\$GHCR_USER" --password-stdin

  3. For private GHCR images, log in on the SERVER before pull-based deploys:
       echo "\$GHCR_TOKEN" | docker login ghcr.io -u "\$GHCR_USER" --password-stdin

  4. Recommended production pull workflow:
       IMAGE_REGISTRY=ghcr.io/<your-github-user>
       IMAGE_TAG=v1.0.0
       docker compose -f docker-compose.prod.yml pull
       docker compose -f docker-compose.prod.yml up -d

Notes:
  - Use explicit version tags (for example v1.0.0) instead of relying only on latest.
  - release always builds both amd64 and arm64 and does not accept --arch.
  - sync is best when the server should not receive source code or cannot pull from GHCR.
EOF
}

parse_global_args() {
    local command="$1"
    shift
    REMAINING_ARGS=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --arch)
                [[ "$command" != "release" ]] || fail "release does not accept --arch; it always publishes amd64 and arm64."
                [[ $# -ge 2 ]] || fail "Missing value for --arch"
                ARCH="$2"
                shift 2
                ;;
            --help|-h)
                print_help
                exit 0
                ;;
            --)
                shift
                break
                ;;
            *)
                break
                ;;
        esac
    done

    REMAINING_ARGS=("$@")
}

build_single_arch_images() {
    local platform
    platform="$(platform_for_arch "$ARCH")"

    require_buildx

    info "Building images for ${platform} (arch=${ARCH})..."
    docker buildx build --platform "$platform" -t "$BACKEND_IMAGE" -f backend/Dockerfile --load backend
    docker buildx build --platform "$platform" -t "$FRONTEND_IMAGE" -f frontend/Dockerfile "${frontend_build_args[@]}" --load frontend
    ok "Built (${ARCH}): ${BACKEND_IMAGE}, ${FRONTEND_IMAGE}"
}

cmd_build() {
    build_single_arch_images
}

cmd_push() {
    require_ghcr_user
    build_single_arch_images

    local registry="ghcr.io/${GHCR_USER}"
    local remote_backend="${registry}/bioinfoflow-backend:${IMAGE_TAG}-${ARCH}"
    local remote_frontend="${registry}/bioinfoflow-frontend:${IMAGE_TAG}-${ARCH}"

    info "Tagging for GHCR..."
    docker tag "$BACKEND_IMAGE" "$remote_backend"
    docker tag "$FRONTEND_IMAGE" "$remote_frontend"

    info "Pushing single-arch images to ${registry}..."
    docker push "$remote_backend"
    docker push "$remote_frontend"

    ok "Pushed: ${remote_backend}"
    ok "Pushed: ${remote_frontend}"
}

cmd_release() {
    require_ghcr_user
    require_buildx

    local registry="ghcr.io/${GHCR_USER}"
    local release_backend="${registry}/bioinfoflow-backend:${IMAGE_TAG}"
    local release_frontend="${registry}/bioinfoflow-frontend:${IMAGE_TAG}"
    local platforms="linux/amd64,linux/arm64"

    info "Building and pushing multi-arch release (${platforms})..."
    docker buildx build --platform "$platforms" -t "$release_backend" -f backend/Dockerfile backend --push
    docker buildx build --platform "$platforms" -t "$release_frontend" -f frontend/Dockerfile "${frontend_build_args[@]}" frontend --push

    ok "Released: ${release_backend}"
    ok "Released: ${release_frontend}"

    echo ""
    info "On the server, add to .env:"
    echo "  IMAGE_REGISTRY=${registry}"
    echo "  IMAGE_TAG=${IMAGE_TAG}"
    echo ""
    info "Then run:"
    echo "  docker compose -f docker-compose.prod.yml pull"
    echo "  docker compose -f docker-compose.prod.yml up -d"
}

cmd_sync() {
    local server="${1:?Usage: deploy.sh sync [--arch amd64|arm64] user@server [remote_dir]}"
    local remote_dir="${2:-~/bioinfoflow}"
    local archive="/tmp/bioinfoflow-images.tar.gz"

    build_single_arch_images

    info "Saving images to ${archive}..."
    docker save "$BACKEND_IMAGE" "$FRONTEND_IMAGE" | gzip > "$archive"
    local size
    size=$(du -h "$archive" | cut -f1)
    ok "Saved: ${archive} (${size})"

    info "Transferring to ${server}:${remote_dir}..."
    ssh "$server" "mkdir -p ${remote_dir}"
    scp "$archive" "${server}:${remote_dir}/bioinfoflow-images.tar.gz"
    scp docker-compose.prod.yml "${server}:${remote_dir}/docker-compose.prod.yml"

    info "Loading images on server..."
    ssh "$server" "cd ${remote_dir} && docker load < bioinfoflow-images.tar.gz"

    info "Starting services on server..."
    ssh "$server" "cd ${remote_dir} && docker compose -f docker-compose.prod.yml up -d"

    ok "Deployed to ${server}"
    echo ""
    warn "Make sure ${remote_dir}/.env exists on the server."
    warn "If first time, run: ./deploy.sh setup ${server}"
}

cmd_setup() {
    local server="${1:?Usage: deploy.sh setup user@server [remote_dir]}"
    local remote_dir="${2:-~/bioinfoflow}"

    info "Setting up ${server}:${remote_dir}..."
    ssh "$server" "mkdir -p ${remote_dir}"

    scp docker-compose.prod.yml "${server}:${remote_dir}/docker-compose.prod.yml"
    scp .env.example "${server}:${remote_dir}/.env"

    ok "Copied compose + .env to ${server}:${remote_dir}"
    echo ""
    warn "Edit ${remote_dir}/.env on the server before starting:"
    echo "  ssh ${server}"
    echo "  cd ${remote_dir}"
    echo "  vim .env   # Set API keys, URLs, auth credentials"
    echo ""
    info "Then deploy with:"
    echo "  ./deploy.sh sync --arch amd64 ${server}"
}

command="${1:-help}"
if [[ "$command" == "help" || "$command" == "--help" || "$command" == "-h" ]]; then
    print_help
    exit 0
fi
shift || true
parse_global_args "$command" "$@"
if [[ ${#REMAINING_ARGS[@]} -gt 0 ]]; then
    set -- "${REMAINING_ARGS[@]}"
else
    set --
fi

case "$command" in
    build)   cmd_build "$@" ;;
    push)    cmd_push "$@" ;;
    sync)    cmd_sync "$@" ;;
    setup)   cmd_setup "$@" ;;
    release) cmd_release "$@" ;;
    *)
        print_help
        exit 1
        ;;
esac
