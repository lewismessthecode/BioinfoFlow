#!/bin/sh
set -eu

PROGRAM=bioinfoflow-installer
EMBEDDED_VERSION=__BIOINFOFLOW_VERSION__
DEFAULT_REGISTRY=ghcr.io/lewismessthecode
DEFAULT_RELEASE_BASE=https://github.com/lewismessthecode/BioinfoFlow/releases/download
DEFAULT_LATEST_RELEASE_URL=https://api.github.com/repos/lewismessthecode/BioinfoFlow/releases/latest

DRY_RUN=0
NO_OPEN=0
ACTION=install
REQUESTED_VERSION=${BIOINFOFLOW_VERSION:-}
if [ -n "$REQUESTED_VERSION" ]; then VERSION_EXPLICIT=1; else VERSION_EXPLICIT=0; fi

usage() {
  cat <<'EOF'
Usage: install.sh [--dry-run] [--version [TAG]] [--update] [--uninstall] [--purge] [--no-open]

Install or repair the localhost Bioinfoflow release. Set BIOINFOFLOW_VERSION or
pass --version TAG to select a release. --uninstall preserves data; --purge
removes it explicitly. The installer never requests or stores provider API keys.
EOF
}

die() {
  printf '%s: %s\n' "$PROGRAM" "$*" >&2
  exit 1
}

die_with_hint() {
  message=$1
  hint=$2
  printf '%s: %s\n' "$PROGRAM" "$message" >&2
  printf 'Recovery: %s\n' "$hint" >&2
  exit 1
}

say() {
  printf '%s\n' "$*"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --no-open) NO_OPEN=1 ;;
    --update) ACTION=update ;;
    --uninstall) ACTION=uninstall ;;
    --purge) ACTION=purge ;;
    --version)
      if [ "$#" -gt 1 ] && [ "${2#-}" = "$2" ]; then
        REQUESTED_VERSION=$2
        VERSION_EXPLICIT=1
        shift
      else
        if [ -n "$REQUESTED_VERSION" ]; then
          printf '%s\n' "$REQUESTED_VERSION"
        else
          case "$EMBEDDED_VERSION" in
            __*__) printf '%s\n' latest ;;
            *) printf '%s\n' "$EMBEDDED_VERSION" ;;
          esac
        fi
        exit 0
      fi
      ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown option: $1" ;;
  esac
  shift
done

if [ -z "$REQUESTED_VERSION" ]; then
  case "$EMBEDDED_VERSION" in
    __*__) REQUESTED_VERSION=latest ;;
    *) REQUESTED_VERSION=$EMBEDDED_VERSION ;;
  esac
fi

case "$HOME" in /*) ;; *) die_with_hint "HOME must be an absolute path" "Set HOME to your absolute user home directory and retry." ;; esac
[ "$HOME" != / ] || die_with_hint "refusing to manage installer files directly under /" "Run as a regular user with HOME set to that user's home directory."
MANAGED_ROOT="$HOME/.bioinfoflow"
INSTALL_DIR="$MANAGED_ROOT/install"
DATA_DIR="$MANAGED_ROOT/data"
[ -z "${BIOINFOFLOW_INSTALL_DIR:-}" ] || [ "$BIOINFOFLOW_INSTALL_DIR" = "$INSTALL_DIR" ] || die_with_hint "BIOINFOFLOW_INSTALL_DIR must be the managed control path $INSTALL_DIR" "Unset BIOINFOFLOW_INSTALL_DIR; the localhost installer manages this path automatically."
[ -z "${BIOINFOFLOW_HOME:-}" ] || [ "$BIOINFOFLOW_HOME" = "$DATA_DIR" ] || die_with_hint "BIOINFOFLOW_HOME must be the managed data path $DATA_DIR" "Unset BIOINFOFLOW_HOME; the localhost installer manages this path automatically."
COMPOSE_FILE="$INSTALL_DIR/docker-compose.local.yml"
ENV_FILE="$INSTALL_DIR/.env"
VERSION_FILE="$INSTALL_DIR/VERSION"
INSTALLED_INSTALLER="$INSTALL_DIR/install.sh"
DATA_MARKER="$DATA_DIR/.managed-by-bioinfoflow"
RELEASE_BASE=${BIOINFOFLOW_RELEASE_BASE_URL:-$DEFAULT_RELEASE_BASE}
LATEST_RELEASE_URL=${BIOINFOFLOW_LATEST_RELEASE_URL:-$DEFAULT_LATEST_RELEASE_URL}
FRONTEND_PORT=${FRONTEND_PORT:-3000}
if [ -n "${BACKEND_PORT:-}" ] && [ "$BACKEND_PORT" != 8000 ]; then
  die_with_hint "backend port is fixed at 8000 for the localhost frontend" "Stop the process using port 8000, unset BACKEND_PORT, and retry."
fi
BACKEND_PORT=8000
IMAGE_REGISTRY=${IMAGE_REGISTRY:-$DEFAULT_REGISTRY}
HEALTH_ATTEMPTS=${BIOINFOFLOW_HEALTH_ATTEMPTS:-60}
HEALTH_INTERVAL=${BIOINFOFLOW_HEALTH_INTERVAL:-2}

[ ! -L "$MANAGED_ROOT" ] || die_with_hint "managed root must not be a symlink: $MANAGED_ROOT" "Remove the symlink and retry; Bioinfoflow only manages real directories under HOME."
[ ! -L "$INSTALL_DIR" ] || die_with_hint "install directory must not be a symlink: $INSTALL_DIR" "Remove the symlink and retry; control files must stay under the managed root."
[ ! -L "$DATA_DIR" ] || die_with_hint "data directory must not be a symlink: $DATA_DIR" "Remove the symlink and retry; data must stay under the managed root."

compose_with() {
  selected_env=$1
  selected_compose=$2
  shift 2
  docker compose --project-name bioinfoflow --env-file "$selected_env" -f "$selected_compose" "$@"
}

compose() {
  compose_with "$ENV_FILE" "$COMPOSE_FILE" "$@"
}

normalize_absolute_path() {
  path_to_normalize=$1
  case "$path_to_normalize" in /*) ;; *) return 1 ;; esac
  normalized_path=
  saved_ifs=$IFS
  IFS=/
  set -f
  # Splitting only on '/' is intentional so normalization does not require the
  # path to exist and preserves spaces or colons in socket paths.
  # shellcheck disable=SC2086
  set -- $path_to_normalize
  set +f
  IFS=$saved_ifs
  for path_component in "$@"; do
    case "$path_component" in
      ''|.) ;;
      ..) normalized_path=${normalized_path%/*} ;;
      *) normalized_path="$normalized_path/$path_component" ;;
    esac
  done
  [ -n "$normalized_path" ] || normalized_path=/
  printf '%s\n' "$normalized_path"
}

stop_installed_or_fail() {
  if [ ! -e "$INSTALL_DIR" ]; then
    return 0
  fi
  if [ ! -f "$COMPOSE_FILE" ] || [ ! -f "$ENV_FILE" ]; then
    die_with_hint "managed control files are incomplete; cannot confirm the installed stack is stopped" "Preserve $INSTALL_DIR, restore its Compose and environment files, then retry."
  fi
  command -v docker >/dev/null 2>&1 || die_with_hint "Docker is unavailable; cannot confirm the installed stack is stopped" "Start or install Docker, then retry. Control files and data were preserved."
  docker compose version >/dev/null 2>&1 || die_with_hint "Docker Compose v2 is unavailable; cannot confirm the installed stack is stopped" "Install Docker Compose v2, then retry. Control files and data were preserved."
  docker info >/dev/null 2>&1 || die_with_hint "Docker daemon is unavailable; cannot confirm the installed stack is stopped" "Start Docker, then retry. Control files and data were preserved."
  cleanup_context=$(docker context show 2>/dev/null || true)
  cleanup_endpoint=${DOCKER_HOST:-}
  if [ -z "$cleanup_endpoint" ] && [ -n "$cleanup_context" ]; then
    cleanup_endpoint=$(docker context inspect "$cleanup_context" --format '{{.Endpoints.docker.Host}}' 2>/dev/null || true)
  fi
  case "$cleanup_endpoint" in
    unix:///*) ;;
    *) die_with_hint "the effective Docker context is not a local Unix socket; cannot confirm the installed stack is stopped" "Select the local Docker context, then retry. Control files and data were preserved." ;;
  esac
  installed_socket_path=
  while IFS= read -r installed_env_line || [ -n "$installed_env_line" ]; do
    case "$installed_env_line" in
      DOCKER_SOCKET_PATH=*) installed_socket_path=${installed_env_line#DOCKER_SOCKET_PATH=} ;;
    esac
  done < "$ENV_FILE"
  [ -n "$installed_socket_path" ] || die_with_hint "managed environment does not record the installed Docker socket; cannot confirm the installed stack is stopped" "Preserve $INSTALL_DIR, restore its generated environment file, then retry."
  normalized_installed_socket=$(normalize_absolute_path "$installed_socket_path") || die_with_hint "installed Docker socket path is not absolute; cannot confirm the installed stack is stopped" "Preserve $INSTALL_DIR, restore its generated environment file, then retry."
  cleanup_socket_path=${cleanup_endpoint#unix://}
  normalized_cleanup_socket=$(normalize_absolute_path "$cleanup_socket_path") || die_with_hint "effective Docker socket path is not absolute; cannot confirm the installed stack is stopped" "Select the installation's local Docker context, then retry. Control files and data were preserved."
  [ "$normalized_cleanup_socket" = "$normalized_installed_socket" ] || die_with_hint "effective Docker socket $normalized_cleanup_socket does not match the installed Docker socket $normalized_installed_socket" "Select the Docker context used to install Bioinfoflow, then retry. Control files and data were preserved."
  installed_uid=
  installed_gid=
  while IFS= read -r installed_env_line || [ -n "$installed_env_line" ]; do
    case "$installed_env_line" in
      BIOINFOFLOW_INSTALL_UID=*) installed_uid=${installed_env_line#BIOINFOFLOW_INSTALL_UID=} ;;
      BIOINFOFLOW_INSTALL_GID=*) installed_gid=${installed_env_line#BIOINFOFLOW_INSTALL_GID=} ;;
    esac
  done < "$ENV_FILE"
  case "$installed_uid" in ''|*[!0-9]*) die_with_hint "managed environment does not record a valid installer user ID; cannot return data ownership" "Preserve $INSTALL_DIR, restore its generated environment file, then retry." ;; esac
  case "$installed_gid" in ''|*[!0-9]*) die_with_hint "managed environment does not record a valid installer group ID; cannot return data ownership" "Preserve $INSTALL_DIR, restore its generated environment file, then retry." ;; esac
  compose stop >/dev/null 2>&1 || die_with_hint "Docker Compose could not stop the installed project before ownership handoff" "Resolve the Compose error and retry. Control files and data were preserved."
  compose run --rm --no-deps --entrypoint /bin/chown backend -R "$installed_uid:$installed_gid" "$DATA_DIR" >/dev/null 2>&1 || die_with_hint "Docker could not return managed data ownership to the installing user" "Preserve $INSTALL_DIR and $DATA_DIR, resolve the container error, then retry."
  compose down --remove-orphans >/dev/null 2>&1 || die_with_hint "Docker Compose could not stop the installed project" "Resolve the Compose error and retry. Control files and data were preserved."
}

if [ "$ACTION" = uninstall ] || [ "$ACTION" = purge ]; then
  if [ "$DRY_RUN" -eq 1 ]; then
    say "Would remove the Bioinfoflow launcher from $INSTALL_DIR"
    [ "$ACTION" = purge ] && say "Would also remove managed data from $DATA_DIR"
    exit 0
  fi
  stop_installed_or_fail
  if [ "$ACTION" = purge ]; then
    if [ -e "$DATA_DIR" ] && [ ! -f "$DATA_MARKER" ]; then
      die_with_hint "refusing to purge unmarked data directory $DATA_DIR" "Move or back up that directory, then remove it manually if deletion is intended."
    fi
    rm -rf "$INSTALL_DIR"
    [ ! -e "$DATA_DIR" ] || rm -rf "$DATA_DIR"
    rmdir "$MANAGED_ROOT" 2>/dev/null || true
    say "Bioinfoflow and its data were purged."
  else
    rm -rf "$INSTALL_DIR"
    rmdir "$MANAGED_ROOT" 2>/dev/null || true
    say "Bioinfoflow was uninstalled. Data was preserved at $DATA_DIR."
  fi
  exit 0
fi

command -v docker >/dev/null 2>&1 || die_with_hint "Docker is required" "Install Docker Desktop or Docker Engine, then rerun this installer."
docker compose version >/dev/null 2>&1 || die_with_hint "Docker Compose v2 is required" "Install Docker Desktop or the Docker Compose v2 plugin, then rerun this installer."
docker info >/dev/null 2>&1 || die_with_hint "Docker daemon is not running" "Start Docker Desktop, or run 'sudo systemctl start docker' on Linux, then retry."
DOCKER_CONTEXT=$(docker context show 2>/dev/null || printf default)
DOCKER_ENDPOINT=${DOCKER_HOST:-}
if [ -z "$DOCKER_ENDPOINT" ]; then
  DOCKER_ENDPOINT=$(docker context inspect "$DOCKER_CONTEXT" --format '{{.Endpoints.docker.Host}}' 2>/dev/null || true)
fi
case "$DOCKER_ENDPOINT" in
  unix:///*) DOCKER_SOCKET_PATH=${DOCKER_ENDPOINT#unix://} ;;
  *) die_with_hint "Docker must use a local Unix socket; effective endpoint is '${DOCKER_ENDPOINT:-unknown}'" "Run 'unset DOCKER_HOST' and 'docker context use default', then retry." ;;
esac
case "$DOCKER_SOCKET_PATH" in /*) ;; *) die_with_hint "Docker Unix socket path must be absolute: $DOCKER_SOCKET_PATH" "Run 'unset DOCKER_HOST' and select a local Docker context." ;; esac

ARCH=$(uname -m)
case "$ARCH" in
  x86_64|amd64) PLATFORM_ARCH=amd64 ;;
  arm64|aarch64) PLATFORM_ARCH=arm64 ;;
  *) die_with_hint "Unsupported architecture: $ARCH" "Use an amd64 or arm64 host, the architectures published by Bioinfoflow." ;;
esac

show_diagnostics() {
  diagnostic_env=$1
  diagnostic_compose=$2
  say "Container status:" >&2
  compose_with "$diagnostic_env" "$diagnostic_compose" ps >&2 || true
  say "Recent logs:" >&2
  compose_with "$diagnostic_env" "$diagnostic_compose" logs --tail 100 >&2 || true
  say "Recovery commands:" >&2
  printf '  docker compose --project-name bioinfoflow --env-file %s -f %s ps\n' "$diagnostic_env" "$diagnostic_compose" >&2
  printf '  docker compose --project-name bioinfoflow --env-file %s -f %s logs --tail 100\n' "$diagnostic_env" "$diagnostic_compose" >&2
  printf '  docker compose --project-name bioinfoflow --env-file %s -f %s pull\n' "$diagnostic_env" "$diagnostic_compose" >&2
  printf '  docker compose --project-name bioinfoflow --env-file %s -f %s up -d --remove-orphans\n' "$diagnostic_env" "$diagnostic_compose" >&2
}

if [ ! -f "$COMPOSE_FILE" ] && command -v lsof >/dev/null 2>&1; then
  if lsof -nP -iTCP:"$FRONTEND_PORT" -sTCP:LISTEN >/dev/null 2>&1; then die_with_hint "frontend port $FRONTEND_PORT is already in use" "Stop the process using it, or retry with FRONTEND_PORT set to a free port."; fi
  if lsof -nP -iTCP:"$BACKEND_PORT" -sTCP:LISTEN >/dev/null 2>&1; then die_with_hint "backend port $BACKEND_PORT is already in use" "Stop the process using port 8000, then retry."; fi
fi

if [ "$DRY_RUN" -eq 1 ]; then
  say "Would install Bioinfoflow $REQUESTED_VERSION for linux/$PLATFORM_ARCH in $INSTALL_DIR"
  say "Would preserve application data in $DATA_DIR"
  exit 0
fi

umask 077
mkdir -p "$INSTALL_DIR" "$DATA_DIR"
chmod 700 "$INSTALL_DIR" "$DATA_DIR"
if [ ! -e "$DATA_MARKER" ]; then
  : > "$DATA_MARKER"
  chmod 600 "$DATA_MARKER"
fi
TMP_DIR=$(mktemp -d "$INSTALL_DIR/.install.XXXXXX")
# shellcheck disable=SC2329 # Invoked by the trap below.
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT HUP INT TERM

if [ "$ACTION" = update ] && [ "$VERSION_EXPLICIT" -eq 0 ]; then
  curl -fL --retry 2 --connect-timeout 15 -o "$TMP_DIR/latest-release.json" "$LATEST_RELEASE_URL" || die_with_hint "latest release lookup failed" "Check network access, or retry with --version followed by a known release tag."
  REQUESTED_VERSION=$(sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$TMP_DIR/latest-release.json" | sed -n '1p')
  [ -n "$REQUESTED_VERSION" ] || die_with_hint "latest release response did not contain tag_name" "Retry with --version followed by a known release tag."
fi

ASSET_BASE="$RELEASE_BASE/$REQUESTED_VERSION"
curl -fL --retry 2 --connect-timeout 15 -o "$TMP_DIR/install.sh" "$ASSET_BASE/install.sh" || die_with_hint "installer download failed" "Check that release tag '$REQUESTED_VERSION' exists and that GitHub releases are reachable."
curl -fL --retry 2 --connect-timeout 15 -o "$TMP_DIR/docker-compose.local.yml" "$ASSET_BASE/docker-compose.local.yml" || die_with_hint "release asset download failed" "Check that release tag '$REQUESTED_VERSION' exists and retry; partial downloads are discarded."
curl -fL --retry 2 --connect-timeout 15 -o "$TMP_DIR/SHA256SUMS" "$ASSET_BASE/SHA256SUMS" || die_with_hint "checksum download failed" "Check that release tag '$REQUESTED_VERSION' includes SHA256SUMS and retry."
sed -n '/[[:space:]]install\.sh$/p; /[[:space:]]docker-compose\.local\.yml$/p' "$TMP_DIR/SHA256SUMS" > "$TMP_DIR/assets.sha256"
[ "$(sed -n '$=' "$TMP_DIR/assets.sha256")" = 2 ] || die_with_hint "checksum manifest must contain install.sh and docker-compose.local.yml" "Do not bypass verification; retry the same release or choose another published release tag."
if command -v sha256sum >/dev/null 2>&1; then
  (cd "$TMP_DIR" && sha256sum -c assets.sha256 >/dev/null 2>&1) || die_with_hint "checksum verification failed" "Do not bypass verification; retry to replace the downloaded release assets."
elif command -v shasum >/dev/null 2>&1; then
  (cd "$TMP_DIR" && shasum -a 256 -c assets.sha256 >/dev/null 2>&1) || die_with_hint "checksum verification failed" "Do not bypass verification; retry to replace the downloaded release assets."
else
  die_with_hint "SHA-256 checksum tool is required (sha256sum or shasum)" "Install coreutils, or use the shasum command included with macOS, then retry."
fi

cat > "$TMP_DIR/.env" <<EOF
BIOINFOFLOW_HOME=$DATA_DIR
BIOINFOFLOW_VERSION=$REQUESTED_VERSION
BIOINFOFLOW_ARCH=$PLATFORM_ARCH
IMAGE_REGISTRY=$IMAGE_REGISTRY
FRONTEND_PORT=$FRONTEND_PORT
DOCKER_SOCKET_PATH=$DOCKER_SOCKET_PATH
BIOINFOFLOW_INSTALL_UID=$(id -u)
BIOINFOFLOW_INSTALL_GID=$(id -g)
EOF
printf '%s\n' "$REQUESTED_VERSION" > "$TMP_DIR/VERSION"
chmod 700 "$TMP_DIR/install.sh"
chmod 600 "$TMP_DIR/docker-compose.local.yml" "$TMP_DIR/.env" "$TMP_DIR/VERSION"

HAD_PREVIOUS=0
PREVIOUS_VERSION=unknown
if [ -f "$COMPOSE_FILE" ] && [ -f "$ENV_FILE" ]; then
  HAD_PREVIOUS=1
  [ ! -f "$VERSION_FILE" ] || PREVIOUS_VERSION=$(sed -n '1p' "$VERSION_FILE")
fi

rollback_transaction() {
  if [ "$HAD_PREVIOUS" -eq 1 ]; then
    if compose up -d --remove-orphans >/dev/null 2>&1; then
      printf 'Previous Bioinfoflow release %s was restored and restarted.\n' "$PREVIOUS_VERSION" >&2
    else
      printf 'Warning: previous Bioinfoflow release %s remains configured but could not be restarted automatically.\n' "$PREVIOUS_VERSION" >&2
    fi
  else
    compose_with "$TMP_DIR/.env" "$TMP_DIR/docker-compose.local.yml" down --remove-orphans >/dev/null 2>&1 || true
  fi
}

fail_transaction() {
  failure_message=$1
  show_diagnostics "$TMP_DIR/.env" "$TMP_DIR/docker-compose.local.yml"
  rollback_transaction
  die "$failure_message"
}

if ! compose_with "$TMP_DIR/.env" "$TMP_DIR/docker-compose.local.yml" pull; then
  fail_transaction "failed to pull Bioinfoflow images"
fi
if ! compose_with "$TMP_DIR/.env" "$TMP_DIR/docker-compose.local.yml" up -d --remove-orphans; then
  fail_transaction "failed to start Bioinfoflow"
fi

attempt=1
while [ "$attempt" -le "$HEALTH_ATTEMPTS" ]; do
  if curl -fsS "http://127.0.0.1:$BACKEND_PORT/api/v1/system/ping" >/dev/null 2>&1 && curl -fsS "http://127.0.0.1:$FRONTEND_PORT/" >/dev/null 2>&1; then
    mv "$TMP_DIR/install.sh" "$INSTALLED_INSTALLER"
    mv "$TMP_DIR/docker-compose.local.yml" "$COMPOSE_FILE"
    mv "$TMP_DIR/.env" "$ENV_FILE"
    mv "$TMP_DIR/VERSION" "$VERSION_FILE"
    say "Bioinfoflow $REQUESTED_VERSION is ready at http://localhost:$FRONTEND_PORT"
    if [ "$NO_OPEN" -eq 0 ]; then
      if command -v open >/dev/null 2>&1; then open "http://localhost:$FRONTEND_PORT" >/dev/null 2>&1 || true
      elif command -v xdg-open >/dev/null 2>&1; then xdg-open "http://localhost:$FRONTEND_PORT" >/dev/null 2>&1 || true
      fi
    fi
    exit 0
  fi
  attempt=$((attempt + 1))
  [ "$attempt" -gt "$HEALTH_ATTEMPTS" ] || sleep "$HEALTH_INTERVAL"
done

fail_transaction "health check timed out after $HEALTH_ATTEMPTS attempts"
