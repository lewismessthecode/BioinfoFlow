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

stage() {
  printf '→ %s\n' "$*"
}

success() {
  printf '✓ %s\n' "$*"
}

validate_port() {
  port_name=$1
  port_value=$2
  case "$port_value" in
    ''|*[!0-9]*) die_with_hint "$port_name must be a decimal port number" "Set $port_name to a value from 1 through 65535 and retry." ;;
  esac
  if [ "$port_value" -lt 1 ] 2>/dev/null || [ "$port_value" -gt 65535 ] 2>/dev/null; then
    die_with_hint "$port_name must be between 1 and 65535" "Set $port_name to a value from 1 through 65535 and retry."
  fi
}

report_port_owner() {
  owner_port=$1
  owner_details=$(lsof -nP -iTCP:"$owner_port" -sTCP:LISTEN 2>/dev/null || true)
  [ -z "$owner_details" ] || {
    printf '\nPort owner:\n' >&2
    printf '%s\n' "$owner_details" | sed -n '1,6p' >&2
  }
}

die_port_in_use() {
  port_role=$1
  busy_port=$2
  printf '%s: %s port %s is already in use\n' "$PROGRAM" "$port_role" "$busy_port" >&2
  report_port_owner "$busy_port"
  printf '\nRecovery: Choose two free ports and retry, for example:\n' >&2
  printf '  curl -fsSL https://github.com/lewismessthecode/BioinfoFlow/releases/latest/download/install.sh | FRONTEND_PORT=3100 BACKEND_PORT=8100 sh\n' >&2
  exit 1
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
SKILLS_DIR="$MANAGED_ROOT/skills"
STATE_DIR="$MANAGED_ROOT/state"
PROJECTS_DIR="$MANAGED_ROOT/projects"
SOURCES_DIR="$MANAGED_ROOT/sources"
LEGACY_DATA_DIR="$MANAGED_ROOT/data"
[ -z "${BIOINFOFLOW_INSTALL_DIR:-}" ] || [ "$BIOINFOFLOW_INSTALL_DIR" = "$INSTALL_DIR" ] || die_with_hint "BIOINFOFLOW_INSTALL_DIR must be the managed control path $INSTALL_DIR" "Unset BIOINFOFLOW_INSTALL_DIR; the localhost installer manages this path automatically."
[ -z "${BIOINFOFLOW_HOME:-}" ] || [ "$BIOINFOFLOW_HOME" = "$MANAGED_ROOT" ] || die_with_hint "BIOINFOFLOW_HOME must be the managed home $MANAGED_ROOT" "Unset BIOINFOFLOW_HOME; the localhost installer manages this path automatically."
COMPOSE_FILE="$INSTALL_DIR/docker-compose.local.yml"
ENV_FILE="$INSTALL_DIR/.env"
VERSION_FILE="$INSTALL_DIR/VERSION"
INSTALLED_INSTALLER="$INSTALL_DIR/install.sh"
HOME_MARKER="$MANAGED_ROOT/.managed-by-bioinfoflow"
RELEASE_BASE=${BIOINFOFLOW_RELEASE_BASE_URL:-$DEFAULT_RELEASE_BASE}
LATEST_RELEASE_URL=${BIOINFOFLOW_LATEST_RELEASE_URL:-$DEFAULT_LATEST_RELEASE_URL}
REQUESTED_FRONTEND_PORT=${FRONTEND_PORT:-}
REQUESTED_BACKEND_PORT=${BACKEND_PORT:-}
if [ -f "$ENV_FILE" ]; then
  installed_frontend_port=
  installed_backend_port=
  while IFS= read -r installed_env_line || [ -n "$installed_env_line" ]; do
    case "$installed_env_line" in
      FRONTEND_PORT=*) installed_frontend_port=${installed_env_line#FRONTEND_PORT=} ;;
      BACKEND_PORT=*) installed_backend_port=${installed_env_line#BACKEND_PORT=} ;;
    esac
  done < "$ENV_FILE"
  [ -n "$REQUESTED_FRONTEND_PORT" ] || REQUESTED_FRONTEND_PORT=$installed_frontend_port
  [ -n "$REQUESTED_BACKEND_PORT" ] || REQUESTED_BACKEND_PORT=$installed_backend_port
fi
FRONTEND_PORT=${REQUESTED_FRONTEND_PORT:-3000}
BACKEND_PORT=${REQUESTED_BACKEND_PORT:-8000}
validate_port FRONTEND_PORT "$FRONTEND_PORT"
validate_port BACKEND_PORT "$BACKEND_PORT"
[ "$FRONTEND_PORT" != "$BACKEND_PORT" ] || die_with_hint "FRONTEND_PORT and BACKEND_PORT must be different" "Choose two free ports and retry."
IMAGE_REGISTRY=${IMAGE_REGISTRY:-$DEFAULT_REGISTRY}
HEALTH_ATTEMPTS=${BIOINFOFLOW_HEALTH_ATTEMPTS:-60}
HEALTH_INTERVAL=${BIOINFOFLOW_HEALTH_INTERVAL:-2}

[ ! -L "$MANAGED_ROOT" ] || die_with_hint "managed root must not be a symlink: $MANAGED_ROOT" "Remove the symlink and retry; Bioinfoflow only manages real directories under HOME."
[ ! -L "$INSTALL_DIR" ] || die_with_hint "install directory must not be a symlink: $INSTALL_DIR" "Remove the symlink and retry; control files must stay under the managed root."
for runtime_dir in "$SKILLS_DIR" "$STATE_DIR" "$PROJECTS_DIR" "$SOURCES_DIR"; do
  [ ! -L "$runtime_dir" ] || die_with_hint "managed runtime directory must not be a symlink: $runtime_dir" "Remove the symlink and retry; Bioinfoflow only manages real directories under its home."
done
[ ! -L "$HOME_MARKER" ] || die_with_hint "managed home marker must not be a symlink: $HOME_MARKER" "Remove the symlink and retry."

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
  compose run --rm --no-deps --entrypoint /bin/chown backend -R "$installed_uid:$installed_gid" "$SKILLS_DIR" "$STATE_DIR" "$PROJECTS_DIR" "$SOURCES_DIR" >/dev/null 2>&1 || die_with_hint "Docker could not return managed home ownership to the installing user" "Preserve $INSTALL_DIR and $MANAGED_ROOT, resolve the container error, then retry."
  compose down --remove-orphans >/dev/null 2>&1 || die_with_hint "Docker Compose could not stop the installed project" "Resolve the Compose error and retry. Control files and data were preserved."
}

if [ "$ACTION" = uninstall ] || [ "$ACTION" = purge ]; then
  if [ "$DRY_RUN" -eq 1 ]; then
    say "Would remove the Bioinfoflow launcher from $INSTALL_DIR"
    [ "$ACTION" = purge ] && say "Would also remove managed home $MANAGED_ROOT"
    exit 0
  fi
  stop_installed_or_fail
  if [ "$ACTION" = purge ]; then
    if [ -e "$MANAGED_ROOT" ] && [ ! -f "$HOME_MARKER" ]; then
      die_with_hint "refusing to purge unmarked Bioinfoflow home $MANAGED_ROOT" "Move or back up that directory, then remove it manually if deletion is intended."
    fi
    [ ! -e "$MANAGED_ROOT" ] || rm -rf "$MANAGED_ROOT"
    say "Bioinfoflow and its data were purged."
  else
    rm -rf "$INSTALL_DIR"
    rmdir "$MANAGED_ROOT" 2>/dev/null || true
    say "Bioinfoflow was uninstalled. Skills and data were preserved at $MANAGED_ROOT."
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
success "Docker is ready"

ARCH=$(uname -m)
case "$ARCH" in
  x86_64|amd64) PLATFORM_ARCH=amd64 ;;
  arm64|aarch64) PLATFORM_ARCH=arm64 ;;
  *) die_with_hint "Unsupported architecture: $ARCH" "Use an amd64 or arm64 host, the architectures published by Bioinfoflow." ;;
esac
stage "Stable release $REQUESTED_VERSION for linux/$PLATFORM_ARCH"

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
  if lsof -nP -iTCP:"$FRONTEND_PORT" -sTCP:LISTEN >/dev/null 2>&1; then die_port_in_use frontend "$FRONTEND_PORT"; fi
  if lsof -nP -iTCP:"$BACKEND_PORT" -sTCP:LISTEN >/dev/null 2>&1; then die_port_in_use backend "$BACKEND_PORT"; fi
fi

HAD_PREVIOUS=0
PREVIOUS_VERSION=unknown
if [ -f "$COMPOSE_FILE" ] && [ -f "$ENV_FILE" ]; then
  HAD_PREVIOUS=1
  [ ! -f "$VERSION_FILE" ] || PREVIOUS_VERSION=$(sed -n '1p' "$VERSION_FILE")
fi

LEGACY_LAYOUT=0
if [ "$HAD_PREVIOUS" -eq 1 ] && grep -Fqx "BIOINFOFLOW_HOME=$LEGACY_DATA_DIR" "$ENV_FILE"; then
  LEGACY_LAYOUT=1
  for runtime_name in skills state projects sources; do
    legacy_path="$LEGACY_DATA_DIR/$runtime_name"
    current_path="$MANAGED_ROOT/$runtime_name"
    if [ -e "$legacy_path" ] && [ -e "$current_path" ]; then
      die_with_hint "legacy and current runtime paths both exist for $runtime_name" "Merge or move one of $legacy_path and $current_path, then retry the update."
    fi
  done
fi

SEED_SKILLS=0
if [ "$HAD_PREVIOUS" -eq 0 ] && [ ! -e "$SKILLS_DIR" ]; then
  SEED_SKILLS=1
fi
[ ! -e "$SKILLS_DIR" ] || [ -d "$SKILLS_DIR" ] || die_with_hint "skills path is not a directory: $SKILLS_DIR" "Move that path aside and retry."

if [ "$DRY_RUN" -eq 1 ]; then
  say "Would install Bioinfoflow $REQUESTED_VERSION for linux/$PLATFORM_ARCH in $INSTALL_DIR"
  say "Would use Bioinfoflow home $MANAGED_ROOT"
  say "Would publish the frontend on port $FRONTEND_PORT and backend on port $BACKEND_PORT"
  [ "$SEED_SKILLS" -eq 0 ] || say "Would seed bundled NGS skills in $SKILLS_DIR"
  exit 0
fi

umask 077
mkdir -p "$INSTALL_DIR"
chmod 700 "$INSTALL_DIR"
if [ ! -e "$HOME_MARKER" ]; then
  : > "$HOME_MARKER"
  chmod 600 "$HOME_MARKER"
fi
TMP_DIR=$(mktemp -d "$INSTALL_DIR/.install.XXXXXX")
# shellcheck disable=SC2329 # Invoked by the trap below.
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT HUP INT TERM

if [ "$ACTION" = update ] && [ "$VERSION_EXPLICIT" -eq 0 ]; then
  curl -fsSL --retry 2 --connect-timeout 15 -o "$TMP_DIR/latest-release.json" "$LATEST_RELEASE_URL" || die_with_hint "latest release lookup failed" "Check network access, or retry with --version followed by a known release tag."
  REQUESTED_VERSION=$(sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$TMP_DIR/latest-release.json" | sed -n '1p')
  [ -n "$REQUESTED_VERSION" ] || die_with_hint "latest release response did not contain tag_name" "Retry with --version followed by a known release tag."
fi

ASSET_BASE="$RELEASE_BASE/$REQUESTED_VERSION"
stage "Downloading and verifying release assets"
curl -fsSL --retry 2 --connect-timeout 15 -o "$TMP_DIR/install.sh" "$ASSET_BASE/install.sh" || die_with_hint "installer download failed" "Check that release tag '$REQUESTED_VERSION' exists and that GitHub releases are reachable."
curl -fsSL --retry 2 --connect-timeout 15 -o "$TMP_DIR/docker-compose.local.yml" "$ASSET_BASE/docker-compose.local.yml" || die_with_hint "release asset download failed" "Check that release tag '$REQUESTED_VERSION' exists and retry; partial downloads are discarded."
curl -fsSL --retry 2 --connect-timeout 15 -o "$TMP_DIR/SHA256SUMS" "$ASSET_BASE/SHA256SUMS" || die_with_hint "checksum download failed" "Check that release tag '$REQUESTED_VERSION' includes SHA256SUMS and retry."
if [ "$SEED_SKILLS" -eq 1 ]; then
  command -v tar >/dev/null 2>&1 || die_with_hint "tar is required to install bundled skills" "Install tar and retry."
  curl -fsSL --retry 2 --connect-timeout 15 -o "$TMP_DIR/bioinfoflow-skills.tar.gz" "$ASSET_BASE/bioinfoflow-skills.tar.gz" || die_with_hint "skills archive download failed" "Check that release tag '$REQUESTED_VERSION' includes bioinfoflow-skills.tar.gz and retry."
  sed -n '/[[:space:]]install\.sh$/p; /[[:space:]]docker-compose\.local\.yml$/p; /[[:space:]]bioinfoflow-skills\.tar\.gz$/p' "$TMP_DIR/SHA256SUMS" > "$TMP_DIR/assets.sha256"
  [ "$(sed -n '$=' "$TMP_DIR/assets.sha256")" = 3 ] || die_with_hint "checksum manifest must contain installer, Compose, and skills assets" "Do not bypass verification; retry the same release or choose another published release tag."
else
  sed -n '/[[:space:]]install\.sh$/p; /[[:space:]]docker-compose\.local\.yml$/p' "$TMP_DIR/SHA256SUMS" > "$TMP_DIR/assets.sha256"
  [ "$(sed -n '$=' "$TMP_DIR/assets.sha256")" = 2 ] || die_with_hint "checksum manifest must contain install.sh and docker-compose.local.yml" "Do not bypass verification; retry the same release or choose another published release tag."
fi
if command -v sha256sum >/dev/null 2>&1; then
  (cd "$TMP_DIR" && sha256sum -c assets.sha256 >/dev/null 2>&1) || die_with_hint "checksum verification failed" "Do not bypass verification; retry to replace the downloaded release assets."
elif command -v shasum >/dev/null 2>&1; then
  (cd "$TMP_DIR" && shasum -a 256 -c assets.sha256 >/dev/null 2>&1) || die_with_hint "checksum verification failed" "Do not bypass verification; retry to replace the downloaded release assets."
else
  die_with_hint "SHA-256 checksum tool is required (sha256sum or shasum)" "Install coreutils, or use the shasum command included with macOS, then retry."
fi
success "Release assets verified"

STAGED_SKILLS="$TMP_DIR/skills"
if [ "$SEED_SKILLS" -eq 1 ]; then
  tar -tzf "$TMP_DIR/bioinfoflow-skills.tar.gz" > "$TMP_DIR/skills.entries" || die_with_hint "skills archive could not be read" "Retry the release download; the partial installation was not committed."
  tar -tvzf "$TMP_DIR/bioinfoflow-skills.tar.gz" > "$TMP_DIR/skills.verbose" || die_with_hint "skills archive metadata could not be read" "Retry the release download; the partial installation was not committed."
  while IFS= read -r archive_metadata || [ -n "$archive_metadata" ]; do
    case "$archive_metadata" in
      l*|h*) die_with_hint "skills archive contains links" "Use an official Bioinfoflow release asset and retry." ;;
    esac
  done < "$TMP_DIR/skills.verbose"
  while IFS= read -r archive_entry || [ -n "$archive_entry" ]; do
    normalized_entry=${archive_entry#./}
    case "$normalized_entry" in
      '') continue ;;
      /*|../*|*/../*|*/..) die_with_hint "skills archive contains an unsafe path: $archive_entry" "Use an official Bioinfoflow release asset and retry." ;;
    esac
  done < "$TMP_DIR/skills.entries"
  mkdir "$STAGED_SKILLS"
  tar -xzf "$TMP_DIR/bioinfoflow-skills.tar.gz" -C "$STAGED_SKILLS" || die_with_hint "skills archive extraction failed" "Retry the release download; the partial installation was not committed."
  if find "$STAGED_SKILLS" -type l -print -quit | grep -q .; then
    die_with_hint "skills archive contains symbolic links" "Use an official Bioinfoflow release asset and retry."
  fi
  skill_count=0
  for skill_dir in "$STAGED_SKILLS"/*; do
    [ -d "$skill_dir" ] || continue
    [ -f "$skill_dir/SKILL.md" ] || die_with_hint "bundled skill is missing SKILL.md: $skill_dir" "Use an official Bioinfoflow release asset and retry."
    skill_count=$((skill_count + 1))
  done
  [ "$skill_count" -gt 0 ] || die_with_hint "skills archive contains no native skills" "Use an official Bioinfoflow release asset and retry."
fi

MIGRATED_LEGACY_THIS_RUN=0
if [ "$LEGACY_LAYOUT" -eq 0 ]; then
  mkdir -p "$STATE_DIR" "$PROJECTS_DIR" "$SOURCES_DIR"
  [ "$SEED_SKILLS" -eq 1 ] || mkdir -p "$SKILLS_DIR"
  chmod 700 "$STATE_DIR" "$PROJECTS_DIR" "$SOURCES_DIR"
  [ "$SEED_SKILLS" -eq 1 ] || chmod 700 "$SKILLS_DIR"
fi

cat > "$TMP_DIR/.env" <<EOF
BIOINFOFLOW_HOME=$MANAGED_ROOT
BIOINFOFLOW_SKILLS_ROOT=$SKILLS_DIR
BIOINFOFLOW_VERSION=$REQUESTED_VERSION
BIOINFOFLOW_ARCH=$PLATFORM_ARCH
IMAGE_REGISTRY=$IMAGE_REGISTRY
FRONTEND_PORT=$FRONTEND_PORT
BACKEND_PORT=$BACKEND_PORT
DOCKER_SOCKET_PATH=$DOCKER_SOCKET_PATH
BIOINFOFLOW_INSTALL_UID=$(id -u)
BIOINFOFLOW_INSTALL_GID=$(id -g)
EOF
printf '%s\n' "$REQUESTED_VERSION" > "$TMP_DIR/VERSION"
chmod 700 "$TMP_DIR/install.sh"
chmod 600 "$TMP_DIR/docker-compose.local.yml" "$TMP_DIR/.env" "$TMP_DIR/VERSION"

SEEDED_SKILLS_THIS_RUN=0

rollback_transaction() {
  if [ "$MIGRATED_LEGACY_THIS_RUN" -eq 1 ]; then
    mkdir -p "$LEGACY_DATA_DIR"
    for runtime_name in skills state projects sources; do
      current_path="$MANAGED_ROOT/$runtime_name"
      legacy_path="$LEGACY_DATA_DIR/$runtime_name"
      if [ -e "$current_path" ]; then
        rm -rf "$legacy_path"
        mv "$current_path" "$legacy_path"
      fi
    done
    MIGRATED_LEGACY_THIS_RUN=0
  fi
  if [ "$HAD_PREVIOUS" -eq 1 ]; then
    if compose up -d --remove-orphans >/dev/null 2>&1; then
      printf 'Previous Bioinfoflow release %s was restored and restarted.\n' "$PREVIOUS_VERSION" >&2
    else
      printf 'Warning: previous Bioinfoflow release %s remains configured but could not be restarted automatically.\n' "$PREVIOUS_VERSION" >&2
    fi
  else
    compose_with "$TMP_DIR/.env" "$TMP_DIR/docker-compose.local.yml" down --remove-orphans >/dev/null 2>&1 || true
  fi
  if [ "$SEEDED_SKILLS_THIS_RUN" -eq 1 ]; then
    rm -rf "$SKILLS_DIR"
    SEEDED_SKILLS_THIS_RUN=0
  fi
}

fail_transaction() {
  failure_message=$1
  show_diagnostics "$TMP_DIR/.env" "$TMP_DIR/docker-compose.local.yml"
  rollback_transaction
  die "$failure_message"
}

stage "Downloading container images (the first install may take several minutes)"
if ! compose_with "$TMP_DIR/.env" "$TMP_DIR/docker-compose.local.yml" pull > "$TMP_DIR/pull.log" 2>&1; then
  say "Image download output:" >&2
  sed -n '1,120p' "$TMP_DIR/pull.log" >&2
  fail_transaction "failed to pull Bioinfoflow images"
fi
if [ "$LEGACY_LAYOUT" -eq 1 ]; then
  for runtime_name in skills state projects sources; do
    legacy_path="$LEGACY_DATA_DIR/$runtime_name"
    current_path="$MANAGED_ROOT/$runtime_name"
    if [ -e "$legacy_path" ]; then
      mv "$legacy_path" "$current_path"
    else
      mkdir -p "$current_path"
    fi
  done
  chmod 700 "$SKILLS_DIR" "$STATE_DIR" "$PROJECTS_DIR" "$SOURCES_DIR"
  MIGRATED_LEGACY_THIS_RUN=1
fi
if [ "$SEED_SKILLS" -eq 1 ]; then
  mv "$STAGED_SKILLS" "$SKILLS_DIR"
  chmod 700 "$SKILLS_DIR"
  SEEDED_SKILLS_THIS_RUN=1
fi
stage "Starting Bioinfoflow"
if ! compose_with "$TMP_DIR/.env" "$TMP_DIR/docker-compose.local.yml" up -d --remove-orphans > "$TMP_DIR/up.log" 2>&1; then
  say "Startup output:" >&2
  sed -n '1,120p' "$TMP_DIR/up.log" >&2
  fail_transaction "failed to start Bioinfoflow"
fi

stage "Waiting for frontend and backend health checks"
attempt=1
while [ "$attempt" -le "$HEALTH_ATTEMPTS" ]; do
  if curl -fsS "http://127.0.0.1:$BACKEND_PORT/api/v1/system/ping" >/dev/null 2>&1 && curl -fsS "http://127.0.0.1:$FRONTEND_PORT/" >/dev/null 2>&1; then
    mv "$TMP_DIR/install.sh" "$INSTALLED_INSTALLER"
    mv "$TMP_DIR/docker-compose.local.yml" "$COMPOSE_FILE"
    mv "$TMP_DIR/.env" "$ENV_FILE"
    mv "$TMP_DIR/VERSION" "$VERSION_FILE"
    if [ "$MIGRATED_LEGACY_THIS_RUN" -eq 1 ]; then
      rm -f "$LEGACY_DATA_DIR/.managed-by-bioinfoflow"
      rmdir "$LEGACY_DATA_DIR" 2>/dev/null || true
      MIGRATED_LEGACY_THIS_RUN=0
    fi
    success "Bioinfoflow $REQUESTED_VERSION is ready"
    say "Bioinfoflow: http://localhost:$FRONTEND_PORT"
    say "Backend: http://localhost:$BACKEND_PORT"
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
