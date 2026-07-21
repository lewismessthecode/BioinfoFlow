#!/bin/sh
set -eu

ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
INSTALLER="$ROOT/scripts/install.sh"
COMPOSE_SOURCE="$ROOT/docker-compose.local.yml"
PASS=0
FAIL=0

fail() {
  printf 'not ok - %s\n' "$1"
  FAIL=$((FAIL + 1))
}

pass() {
  printf 'ok - %s\n' "$1"
  PASS=$((PASS + 1))
}

assert_contains() {
  haystack=$1
  needle=$2
  case "$haystack" in
    *"$needle"*) return 0 ;;
    *) return 1 ;;
  esac
}

setup_case() {
  CASE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/bioinfoflow-install-test.XXXXXX")
  HOME_DIR="$CASE_DIR/home"
  BIN_DIR="$CASE_DIR/bin"
  CALLS="$CASE_DIR/calls"
  mkdir -p "$HOME_DIR" "$BIN_DIR"
  : > "$CALLS"
  SKILLS_SOURCE="$CASE_DIR/skills-source"
  SKILLS_ARCHIVE="$CASE_DIR/bioinfoflow-skills.tar.gz"
  mkdir -p "$SKILLS_SOURCE/ngs-analysis-router" "$SKILLS_SOURCE/ngs-runtime-env"
  printf '%s\n' '---' 'name: ngs-analysis-router' 'description: Route NGS analyses.' '---' '# Router' > "$SKILLS_SOURCE/ngs-analysis-router/SKILL.md"
  printf '%s\n' '---' 'name: ngs-runtime-env' 'description: Check NGS runtimes.' '---' '# Runtime' > "$SKILLS_SOURCE/ngs-runtime-env/SKILL.md"
  (cd "$SKILLS_SOURCE" && tar -czf "$SKILLS_ARCHIVE" .)

  cat > "$BIN_DIR/docker" <<'EOF'
#!/bin/sh
printf 'docker %s\n' "$*" >> "$FAKE_CALLS"
previous=
for argument in "$@"; do
  if [ "$previous" = --env-file ] && [ -f "$argument" ]; then
    sed -n 's/^BIOINFOFLOW_VERSION=/docker version=/p' "$argument" >> "$FAKE_CALLS"
  fi
  previous=$argument
done
case "$*" in
  "compose version"*) [ "${FAKE_COMPOSE_MISSING:-0}" = 0 ] ;;
  "info"*) [ "${FAKE_DAEMON_DOWN:-0}" = 0 ] ;;
  "context show"*) printf '%s\n' "${FAKE_DOCKER_CONTEXT:-default}" ;;
  "context inspect"*) printf '%s\n' "${FAKE_DOCKER_ENDPOINT:-unix:///var/run/docker.sock}" ;;
  "context inspect "*) printf '%s\n' "${FAKE_DOCKER_ENDPOINT:-unix:///var/run/docker.sock}" ;;
  context\ inspect*) printf '%s\n' "${FAKE_DOCKER_ENDPOINT:-unix:///var/run/docker.sock}" ;;
  *" pull"*) [ "${FAKE_PULL_FAIL:-0}" = 0 ] ;;
  *" up -d"*) [ "${FAKE_UP_FAIL:-0}" = 0 ] ;;
  *" stop"*) [ "${FAKE_STOP_FAIL:-0}" = 0 ] ;;
  *" run --rm --no-deps --entrypoint /bin/chown backend -R "*) [ "${FAKE_CHOWN_FAIL:-0}" = 0 ] ;;
  *" down --remove-orphans"*) [ "${FAKE_DOWN_FAIL:-0}" = 0 ] ;;
  *" ps"*) printf '%s\n' 'bioinfoflow status snapshot' ;;
  *" logs"*) printf '%s\n' 'bounded diagnostic log' ;;
  *) exit 0 ;;
esac
EOF

  cat > "$BIN_DIR/curl" <<'EOF'
#!/bin/sh
printf 'curl %s\n' "$*" >> "$FAKE_CALLS"
output=
url=
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o|--output) output=$2; shift 2 ;;
    -*) shift ;;
    *) url=$1; shift ;;
  esac
done
case "$url" in
  http://127.0.0.1:*|http://localhost:*) [ "${FAKE_HEALTH_FAIL:-0}" = 0 ]; exit ;;
  */releases/latest)
    [ "${FAKE_LATEST_FAIL:-0}" = 0 ] || exit 22
    printf '{"tag_name":"%s"}\n' "${FAKE_LATEST_VERSION:-v2.0.0}" > "$output"
    ;;
  */install.sh)
    cp "$FAKE_INSTALLER_SOURCE" "$output"
    ;;
  */docker-compose.local.yml)
    [ "${FAKE_DOWNLOAD_INTERRUPT:-0}" = 0 ] || { printf 'partial' > "$output"; exit 18; }
    cp "$FAKE_COMPOSE_SOURCE" "$output"
    ;;
  */bioinfoflow-skills.tar.gz)
    [ "${FAKE_SKILLS_DOWNLOAD_INTERRUPT:-0}" = 0 ] || { printf 'partial' > "$output"; exit 18; }
    cp "$FAKE_SKILLS_ARCHIVE_SOURCE" "$output"
    ;;
  */SHA256SUMS)
    printf '%s  install.sh\n' "${FAKE_CHECKSUM_VALUE:-valid}" > "$output"
    printf '%s  docker-compose.local.yml\n' "${FAKE_CHECKSUM_VALUE:-valid}" >> "$output"
    printf '%s  bioinfoflow-skills.tar.gz\n' "${FAKE_CHECKSUM_VALUE:-valid}" >> "$output"
    ;;
  *) exit 22 ;;
esac
EOF

  cat > "$BIN_DIR/sha256sum" <<'EOF'
#!/bin/sh
printf 'sha256sum %s\n' "$*" >> "$FAKE_CALLS"
[ "${FAKE_CHECKSUM_FAIL:-0}" = 0 ]
EOF

  cat > "$BIN_DIR/shasum" <<'EOF'
#!/bin/sh
printf 'shasum %s\n' "$*" >> "$FAKE_CALLS"
[ "${FAKE_CHECKSUM_FAIL:-0}" = 0 ]
EOF

  cat > "$BIN_DIR/uname" <<'EOF'
#!/bin/sh
printf '%s\n' "${FAKE_ARCH:-x86_64}"
EOF

cat > "$BIN_DIR/lsof" <<'EOF'
#!/bin/sh
printf 'lsof %s\n' "$*" >> "$FAKE_CALLS"
case "$*" in
  *-iTCP:8000*) [ "${FAKE_BACKEND_PORT_BUSY:-0}" = 1 ] || [ "${FAKE_PORTS_BUSY:-0}" = 1 ] ;;
  *) [ "${FAKE_PORTS_BUSY:-0}" = 1 ] ;;
esac
EOF

  cat > "$BIN_DIR/open" <<'EOF'
#!/bin/sh
printf 'open %s\n' "$*" >> "$FAKE_CALLS"
EOF

  cat > "$BIN_DIR/xdg-open" <<'EOF'
#!/bin/sh
printf 'xdg-open %s\n' "$*" >> "$FAKE_CALLS"
EOF

  chmod +x "$BIN_DIR"/*
}

teardown_case() {
  rm -rf "$CASE_DIR"
}

run_installer() {
  set +e
  # ARGS is deliberately expanded by the isolated child shell.
  # shellcheck disable=SC2016
  OUTPUT=$(env \
    HOME="$HOME_DIR" \
    PATH="$BIN_DIR:/usr/bin:/bin" \
    FAKE_CALLS="$CALLS" \
    FAKE_COMPOSE_SOURCE="$COMPOSE_SOURCE" \
    FAKE_INSTALLER_SOURCE="$INSTALLER" \
    FAKE_SKILLS_ARCHIVE_SOURCE="$SKILLS_ARCHIVE" \
    BIOINFOFLOW_RELEASE_BASE_URL="https://example.test/releases/download" \
    BIOINFOFLOW_HEALTH_ATTEMPTS=2 \
    BIOINFOFLOW_HEALTH_INTERVAL=0 \
    INSTALLER="$INSTALLER" \
    "$@" \
    sh -c 'sh "$INSTALLER" ${ARGS:-}' 2>&1)
  STATUS=$?
  set -e
}

seed_legacy_install() {
  legacy_root="$HOME_DIR/.bioinfoflow"
  legacy_data="$legacy_root/data"
  mkdir -p "$legacy_root/install" "$legacy_data/skills/custom" "$legacy_data/state" "$legacy_data/projects" "$legacy_data/sources"
  printf '%s\n' 'legacy skill' > "$legacy_data/skills/custom/SKILL.md"
  printf '%s\n' 'legacy state' > "$legacy_data/state/state.txt"
  : > "$legacy_data/.managed-by-bioinfoflow"
  cp "$INSTALLER" "$legacy_root/install/install.sh"
  cp "$COMPOSE_SOURCE" "$legacy_root/install/docker-compose.local.yml"
  printf '%s\n' 'v1.0.0' > "$legacy_root/install/VERSION"
  cat > "$legacy_root/install/.env" <<EOF
BIOINFOFLOW_HOME=$legacy_data
BIOINFOFLOW_VERSION=v1.0.0
BIOINFOFLOW_ARCH=amd64
IMAGE_REGISTRY=ghcr.io/lewismessthecode
FRONTEND_PORT=3000
DOCKER_SOCKET_PATH=/var/run/docker.sock
BIOINFOFLOW_INSTALL_UID=$(id -u)
BIOINFOFLOW_INSTALL_GID=$(id -g)
EOF
}

test_failure() {
  name=$1
  expected=$2
  shift 2
  setup_case
  run_installer "$@"
  if [ "$STATUS" -ne 0 ] && assert_contains "$OUTPUT" "$expected"; then pass "$name"; else fail "$name (status=$STATUS output=$OUTPUT)"; fi
  teardown_case
}

test_success() {
  name=$1
  shift
  setup_case
  run_installer "$@"
  if [ "$STATUS" -eq 0 ]; then pass "$name"; else fail "$name (status=$STATUS output=$OUTPUT)"; fi
  teardown_case
}

test_failure_with_hint() {
  name=$1
  expected=$2
  hint=$3
  shift 3
  setup_case
  run_installer "$@"
  if [ "$STATUS" -ne 0 ] && assert_contains "$OUTPUT" "$expected" && assert_contains "$OUTPUT" "$hint"; then pass "$name"; else fail "$name (status=$STATUS output=$OUTPUT)"; fi
  teardown_case
}

test_failure_with_hint "reports missing Docker Compose with recovery" "Docker Compose" "Install Docker Desktop" FAKE_COMPOSE_MISSING=1
test_failure_with_hint "reports a stopped Docker daemon with recovery" "Docker daemon" "Start Docker" FAKE_DAEMON_DOWN=1
test_failure_with_hint "rejects a remote Docker endpoint with recovery" "local Unix" "docker context use" FAKE_DOCKER_CONTEXT=production FAKE_DOCKER_ENDPOINT=tcp://docker.example.test:2376

setup_case
run_installer FAKE_ARCH=x86_64 ARGS=--no-open
if [ "$STATUS" -eq 0 ] && assert_contains "$(cat "$HOME_DIR/.bioinfoflow/install/.env")" "BIOINFOFLOW_ARCH=amd64"; then pass "maps x86_64 to amd64"; else fail "maps x86_64 to amd64"; fi
teardown_case

setup_case
run_installer FAKE_ARCH=arm64 ARGS=--no-open
if [ "$STATUS" -eq 0 ] && assert_contains "$(cat "$HOME_DIR/.bioinfoflow/install/.env")" "BIOINFOFLOW_ARCH=arm64"; then pass "maps arm64 to arm64"; else fail "maps arm64 to arm64"; fi
teardown_case

setup_case
run_installer ARGS=--no-open
if [ "$STATUS" -eq 0 ] && \
   [ -f "$HOME_DIR/.bioinfoflow/skills/ngs-analysis-router/SKILL.md" ] && \
   [ -f "$HOME_DIR/.bioinfoflow/skills/ngs-runtime-env/SKILL.md" ] && \
   grep -q "BIOINFOFLOW_HOME=$HOME_DIR/.bioinfoflow" "$HOME_DIR/.bioinfoflow/install/.env"; then
  pass "fresh install seeds native NGS skills in the unified home"
else
  fail "fresh install seeds native NGS skills in the unified home (status=$STATUS output=$OUTPUT)"
fi
teardown_case

setup_case
run_installer BIOINFOFLOW_VERSION=v1.0.0 ARGS=--no-open
printf '%s\n' 'user modified skill' > "$HOME_DIR/.bioinfoflow/skills/ngs-analysis-router/SKILL.md"
: > "$CALLS"
run_installer BIOINFOFLOW_VERSION=v1.1.0 ARGS="--update --no-open"
if [ "$STATUS" -eq 0 ] && \
   grep -q 'user modified skill' "$HOME_DIR/.bioinfoflow/skills/ngs-analysis-router/SKILL.md" && \
   ! grep -q 'bioinfoflow-skills.tar.gz' "$CALLS"; then
  pass "update preserves existing skills without downloading the bundle"
else
  fail "update preserves existing skills without downloading the bundle (status=$STATUS output=$OUTPUT calls=$(cat "$CALLS"))"
fi
teardown_case

setup_case
mkdir -p "$HOME_DIR/.bioinfoflow/skills/custom-skill"
printf '%s\n' 'custom skill' > "$HOME_DIR/.bioinfoflow/skills/custom-skill/SKILL.md"
run_installer ARGS=--no-open
if [ "$STATUS" -eq 0 ] && \
   grep -q 'custom skill' "$HOME_DIR/.bioinfoflow/skills/custom-skill/SKILL.md" && \
   [ ! -e "$HOME_DIR/.bioinfoflow/skills/ngs-analysis-router" ] && \
   ! grep -q 'bioinfoflow-skills.tar.gz' "$CALLS"; then
  pass "first install preserves a pre-existing skills directory"
else
  fail "first install preserves a pre-existing skills directory (status=$STATUS output=$OUTPUT calls=$(cat "$CALLS"))"
fi
teardown_case

test_failure_with_hint "rejects unsupported architectures with recovery" "Unsupported architecture" "amd64 or arm64" FAKE_ARCH=riscv64
test_failure_with_hint "rejects occupied localhost ports with recovery" "already in use" "FRONTEND_PORT" FAKE_PORTS_BUSY=1
test_failure_with_hint "requires fixed backend port 8000 to be free" "backend port 8000 is already in use" "Stop the process using port 8000" FAKE_BACKEND_PORT_BUSY=1
test_failure_with_hint "keeps interrupted downloads out of place with recovery" "download" "release tag" FAKE_DOWNLOAD_INTERRUPT=1
test_failure_with_hint "rejects checksum failures with recovery" "checksum" "Do not bypass" FAKE_CHECKSUM_FAIL=1
test_failure "rejects DOCKER_HOST TCP endpoints" "local Unix" DOCKER_HOST=tcp://docker.example.test:2376
test_failure_with_hint "rejects unsupported backend port overrides" "backend port is fixed at 8000" "port 8000" BACKEND_PORT=8100

setup_case
PACKAGED_INSTALLER="$CASE_DIR/install-v9.8.7.sh"
sed 's/__BIOINFOFLOW_VERSION__/v9.8.7/g' "$INSTALLER" > "$PACKAGED_INSTALLER"
chmod +x "$PACKAGED_INSTALLER"
INSTALLER="$PACKAGED_INSTALLER"
run_installer ARGS=--version
version_output=$OUTPUT
: > "$CALLS"
run_installer ARGS=--no-open
if [ "$version_output" = v9.8.7 ] && [ "$STATUS" -eq 0 ] && grep -q '/v9.8.7/install.sh' "$CALLS"; then
  pass "packaged installer retains its embedded release tag"
else
  fail "packaged installer retains its embedded release tag (version=$version_output status=$STATUS calls=$(cat "$CALLS"))"
fi
teardown_case
INSTALLER="$ROOT/scripts/install.sh"

test_failure_with_hint "reports latest release lookup recovery" "latest release lookup" "--version" FAKE_LATEST_FAIL=1 ARGS="--update --no-open"

setup_case
run_installer DOCKER_HOST=unix:///tmp/docker-test.sock ARGS=--no-open
if [ "$STATUS" -eq 0 ] && grep -q 'DOCKER_SOCKET_PATH=/tmp/docker-test.sock' "$HOME_DIR/.bioinfoflow/install/.env"; then pass "derives the mounted socket from DOCKER_HOST"; else fail "derives the mounted socket from DOCKER_HOST"; fi
teardown_case

setup_case
run_installer BIOINFOFLOW_VERSION=v1.0.0 ARGS=--no-open
: > "$CALLS"
run_installer BIOINFOFLOW_VERSION=v2.0.0 FAKE_PULL_FAIL=1 ARGS="--update --no-open"
if [ "$STATUS" -ne 0 ] && [ "$(cat "$HOME_DIR/.bioinfoflow/install/VERSION")" = v1.0.0 ] && grep -q 'docker version=v1.0.0' "$CALLS" && assert_contains "$OUTPUT" "restored"; then pass "rolls back control files and restarts the previous release after pull failure"; else fail "rolls back control files and restarts the previous release after pull failure"; fi
teardown_case

setup_case
run_installer BIOINFOFLOW_VERSION=v1.0.0 ARGS=--no-open
: > "$CALLS"
run_installer BIOINFOFLOW_VERSION=v2.0.0 FAKE_HEALTH_FAIL=1 ARGS="--update --no-open"
up_count=$(grep -c ' up -d' "$CALLS" || true)
if [ "$STATUS" -ne 0 ] && [ "$(cat "$HOME_DIR/.bioinfoflow/install/VERSION")" = v1.0.0 ] && [ "$up_count" -ge 2 ] && grep -q 'docker version=v1.0.0' "$CALLS"; then pass "rolls back and restarts the previous release after health failure"; else fail "rolls back and restarts the previous release after health failure"; fi
teardown_case

setup_case
run_installer BIOINFOFLOW_VERSION=v2.0.0 FAKE_PULL_FAIL=1 ARGS=--no-open
if [ "$STATUS" -ne 0 ] && [ ! -e "$HOME_DIR/.bioinfoflow/install/VERSION" ] && [ ! -e "$HOME_DIR/.bioinfoflow/install/docker-compose.local.yml" ] && [ ! -e "$HOME_DIR/.bioinfoflow/skills" ]; then pass "does not commit control files or seeded skills for a failed fresh install"; else fail "does not commit control files or seeded skills for a failed fresh install"; fi
teardown_case

setup_case
run_installer FAKE_PULL_FAIL=1 ARGS=--no-open
if [ "$STATUS" -ne 0 ] && assert_contains "$OUTPUT" "pull" && assert_contains "$OUTPUT" "status snapshot" && assert_contains "$OUTPUT" "Recovery commands"; then pass "reports pull failure status and recovery commands"; else fail "reports pull failure status and recovery commands"; fi
teardown_case
test_failure "reports compose startup failures" "start" FAKE_UP_FAIL=1

setup_case
run_installer FAKE_HEALTH_FAIL=1 ARGS=--no-open
if [ "$STATUS" -ne 0 ] && assert_contains "$OUTPUT" "health" && assert_contains "$OUTPUT" "bounded diagnostic log" && rtk_count=$(grep -c -- '--tail 100' "$CALLS" || true) && [ "$rtk_count" -ge 1 ]; then pass "bounds health polling and prints bounded logs"; else fail "bounds health polling and prints bounded logs"; fi
teardown_case

setup_case
run_installer ARGS=--no-open
first_status=$STATUS
run_installer ARGS=--no-open
if [ "$first_status" -eq 0 ] && [ "$STATUS" -eq 0 ]; then pass "repairs idempotently on rerun"; else fail "repairs idempotently on rerun"; fi
teardown_case

setup_case
run_installer BIOINFOFLOW_VERSION=v1.0.0 ARGS=--no-open
run_installer BIOINFOFLOW_VERSION=v1.1.0 ARGS="--update --no-open"
if [ "$STATUS" -eq 0 ] && [ "$(cat "$HOME_DIR/.bioinfoflow/install/VERSION")" = v1.1.0 ]; then pass "updates to an explicit version"; else fail "updates to an explicit version"; fi
teardown_case

setup_case
seed_legacy_install
run_installer BIOINFOFLOW_VERSION=v1.1.0 ARGS="--update --no-open"
if [ "$STATUS" -eq 0 ] && \
   [ -f "$HOME_DIR/.bioinfoflow/skills/custom/SKILL.md" ] && \
   [ -f "$HOME_DIR/.bioinfoflow/state/state.txt" ] && \
   [ ! -e "$HOME_DIR/.bioinfoflow/data/state" ] && \
   grep -q "BIOINFOFLOW_HOME=$HOME_DIR/.bioinfoflow" "$HOME_DIR/.bioinfoflow/install/.env"; then
  pass "update migrates the legacy data subdirectory into the unified home"
else
  fail "update migrates the legacy data subdirectory into the unified home (status=$STATUS output=$OUTPUT)"
fi
teardown_case

setup_case
seed_legacy_install
run_installer BIOINFOFLOW_VERSION=v1.1.0 FAKE_UP_FAIL=1 ARGS="--update --no-open"
if [ "$STATUS" -ne 0 ] && \
   [ -f "$HOME_DIR/.bioinfoflow/data/skills/custom/SKILL.md" ] && \
   [ -f "$HOME_DIR/.bioinfoflow/data/state/state.txt" ] && \
   [ ! -e "$HOME_DIR/.bioinfoflow/state" ] && \
   grep -q "BIOINFOFLOW_HOME=$HOME_DIR/.bioinfoflow/data" "$HOME_DIR/.bioinfoflow/install/.env"; then
  pass "failed update rolls the legacy home migration back"
else
  fail "failed update rolls the legacy home migration back (status=$STATUS output=$OUTPUT calls=$(cat "$CALLS"))"
fi
teardown_case

setup_case
run_installer BIOINFOFLOW_VERSION=v1.0.0 ARGS=--no-open
run_installer FAKE_LATEST_VERSION=v1.2.0 ARGS="--update --no-open"
if [ "$STATUS" -eq 0 ] && [ "$(cat "$HOME_DIR/.bioinfoflow/install/VERSION")" = v1.2.0 ] && grep -q '/v1.2.0/install.sh' "$CALLS"; then pass "update resolves and downloads the latest release installer"; else fail "update resolves and downloads the latest release installer"; fi
teardown_case

setup_case
run_installer ARGS=--no-open
mkdir -p "$HOME_DIR/.bioinfoflow"
printf 'keep me\n' > "$HOME_DIR/.bioinfoflow/user-file"
: > "$CALLS"
run_installer ARGS=--uninstall
if [ "$STATUS" -eq 0 ] && [ -f "$HOME_DIR/.bioinfoflow/user-file" ] && [ ! -e "$HOME_DIR/.bioinfoflow/install" ] && grep -q ' stop' "$CALLS" && grep -q ' run --rm --no-deps --entrypoint /bin/chown backend -R ' "$CALLS"; then pass "uninstall preserves host-owned user data"; else fail "uninstall preserves host-owned user data (status=$STATUS output=$OUTPUT calls=$(cat "$CALLS"))"; fi
teardown_case

setup_case
run_installer ARGS=--no-open
run_installer FAKE_CHOWN_FAIL=1 ARGS=--uninstall
if [ "$STATUS" -ne 0 ] && [ -e "$HOME_DIR/.bioinfoflow/install" ] && [ -f "$HOME_DIR/.bioinfoflow/.managed-by-bioinfoflow" ] && assert_contains "$OUTPUT" "ownership"; then pass "uninstall preserves control and data when ownership handoff fails"; else fail "uninstall preserves control and data when ownership handoff fails (status=$STATUS output=$OUTPUT)"; fi
teardown_case

setup_case
run_installer ARGS=--no-open
printf 'keep me\n' > "$HOME_DIR/.bioinfoflow/user-file"
rm "$BIN_DIR/docker"
NO_DOCKER_BIN="$CASE_DIR/no-docker-bin"
mkdir "$NO_DOCKER_BIN"
ln -s "$(command -v sh)" "$NO_DOCKER_BIN/sh"
ln -s "$(command -v rm)" "$NO_DOCKER_BIN/rm"
ln -s "$(command -v rmdir)" "$NO_DOCKER_BIN/rmdir"
run_installer PATH="$NO_DOCKER_BIN" ARGS=--uninstall
if [ "$STATUS" -ne 0 ] && [ -f "$HOME_DIR/.bioinfoflow/user-file" ] && [ -e "$HOME_DIR/.bioinfoflow/install" ] && assert_contains "$OUTPUT" "Docker is unavailable"; then pass "uninstall preserves control and data when Docker is unavailable"; else fail "uninstall preserves control and data when Docker is unavailable (status=$STATUS output=$OUTPUT)"; fi
teardown_case

setup_case
run_installer ARGS=--no-open
mkdir -p "$HOME_DIR/.bioinfoflow"
printf 'delete me\n' > "$HOME_DIR/.bioinfoflow/user-file"
run_installer ARGS=--purge
if [ "$STATUS" -eq 0 ] && [ ! -e "$HOME_DIR/.bioinfoflow" ]; then pass "purge explicitly removes user data"; else fail "purge explicitly removes user data"; fi
teardown_case

setup_case
run_installer ARGS=--no-open
run_installer FAKE_DAEMON_DOWN=1 ARGS=--purge
if [ "$STATUS" -ne 0 ] && [ -e "$HOME_DIR/.bioinfoflow/install" ] && [ -f "$HOME_DIR/.bioinfoflow/.managed-by-bioinfoflow" ] && assert_contains "$OUTPUT" "Docker daemon"; then pass "purge preserves control and data when the Docker daemon is unavailable"; else fail "purge preserves control and data when the Docker daemon is unavailable (status=$STATUS output=$OUTPUT)"; fi
teardown_case

setup_case
run_installer ARGS=--no-open
run_installer FAKE_DOCKER_ENDPOINT=tcp://remote.example.test:2376 ARGS=--uninstall
if [ "$STATUS" -ne 0 ] && [ -e "$HOME_DIR/.bioinfoflow/install" ] && assert_contains "$OUTPUT" "local Unix socket"; then pass "uninstall preserves control files with a remote Docker context"; else fail "uninstall preserves control files with a remote Docker context (status=$STATUS output=$OUTPUT)"; fi
teardown_case

setup_case
run_installer DOCKER_HOST=unix:///tmp/bioinfoflow-installed.sock ARGS=--no-open
: > "$CALLS"
run_installer DOCKER_HOST=unix:///tmp/bioinfoflow-other.sock ARGS=--uninstall
if [ "$STATUS" -ne 0 ] && [ -e "$HOME_DIR/.bioinfoflow/install" ] && [ -f "$HOME_DIR/.bioinfoflow/.managed-by-bioinfoflow" ] && ! grep -q ' down --remove-orphans' "$CALLS" && assert_contains "$OUTPUT" "does not match the installed Docker socket"; then pass "uninstall preserves control and data on local Docker socket mismatch"; else fail "uninstall preserves control and data on local Docker socket mismatch (status=$STATUS output=$OUTPUT calls=$(cat "$CALLS"))"; fi
teardown_case

setup_case
run_installer DOCKER_HOST=unix:///tmp/bioinfoflow/../bioinfoflow-installed.sock ARGS=--no-open
: > "$CALLS"
run_installer DOCKER_HOST=unix:///tmp/bioinfoflow-other.sock ARGS=--purge
if [ "$STATUS" -ne 0 ] && [ -e "$HOME_DIR/.bioinfoflow/install" ] && [ -f "$HOME_DIR/.bioinfoflow/.managed-by-bioinfoflow" ] && ! grep -q ' down --remove-orphans' "$CALLS" && assert_contains "$OUTPUT" "does not match the installed Docker socket"; then pass "purge preserves control and data on normalized local Docker socket mismatch"; else fail "purge preserves control and data on normalized local Docker socket mismatch (status=$STATUS output=$OUTPUT calls=$(cat "$CALLS"))"; fi
teardown_case

setup_case
run_installer DOCKER_HOST=unix:///tmp/bioinfoflow/../bioinfoflow-installed.sock ARGS=--no-open
run_installer DOCKER_HOST=unix:///tmp/bioinfoflow-installed.sock ARGS=--uninstall
if [ "$STATUS" -eq 0 ] && [ ! -e "$HOME_DIR/.bioinfoflow/install" ] && [ -f "$HOME_DIR/.bioinfoflow/.managed-by-bioinfoflow" ]; then pass "uninstall accepts normalized paths to the installed Docker socket"; else fail "uninstall accepts normalized paths to the installed Docker socket (status=$STATUS output=$OUTPUT)"; fi
teardown_case

setup_case
run_installer ARGS=--no-open
run_installer FAKE_DOWN_FAIL=1 ARGS=--uninstall
if [ "$STATUS" -ne 0 ] && [ -e "$HOME_DIR/.bioinfoflow/install" ] && [ -f "$HOME_DIR/.bioinfoflow/.managed-by-bioinfoflow" ] && assert_contains "$OUTPUT" "could not stop"; then pass "uninstall preserves control and data when Compose down fails"; else fail "uninstall preserves control and data when Compose down fails (status=$STATUS output=$OUTPUT)"; fi
teardown_case

setup_case
run_installer ARGS=--no-open
run_installer ARGS=--uninstall
rm "$BIN_DIR/docker"
NO_DOCKER_BIN="$CASE_DIR/no-docker-bin"
mkdir "$NO_DOCKER_BIN"
ln -s "$(command -v sh)" "$NO_DOCKER_BIN/sh"
ln -s "$(command -v rm)" "$NO_DOCKER_BIN/rm"
ln -s "$(command -v rmdir)" "$NO_DOCKER_BIN/rmdir"
run_installer PATH="$NO_DOCKER_BIN" ARGS=--purge
if [ "$STATUS" -eq 0 ] && [ ! -e "$HOME_DIR/.bioinfoflow" ]; then pass "data-only purge remains available without Docker after uninstall"; else fail "data-only purge remains available without Docker after uninstall (status=$STATUS output=$OUTPUT)"; fi
teardown_case

setup_case
printf 'do not delete\n' > "$HOME_DIR/sentinel"
run_installer BIOINFOFLOW_INSTALL_DIR="$HOME_DIR" ARGS=--purge
if [ "$STATUS" -ne 0 ] && [ -f "$HOME_DIR/sentinel" ]; then pass "purge rejects arbitrary install roots and preserves HOME"; else fail "purge rejects arbitrary install roots and preserves HOME"; fi
teardown_case

setup_case
mkdir -p "$CASE_DIR/linked-root"
ln -s "$CASE_DIR/linked-root" "$HOME_DIR/.bioinfoflow"
run_installer ARGS=--no-open
if [ "$STATUS" -ne 0 ] && assert_contains "$OUTPUT" "symlink"; then pass "rejects a symlinked managed root"; else fail "rejects a symlinked managed root"; fi
teardown_case

setup_case
mkdir -p "$HOME_DIR/.bioinfoflow" "$CASE_DIR/linked-install"
ln -s "$CASE_DIR/linked-install" "$HOME_DIR/.bioinfoflow/install"
run_installer ARGS=--no-open
if [ "$STATUS" -ne 0 ] && assert_contains "$OUTPUT" "symlink"; then pass "rejects a symlinked install directory"; else fail "rejects a symlinked install directory"; fi
teardown_case

setup_case
mkdir -p "$HOME_DIR/.bioinfoflow" "$CASE_DIR/linked-skills"
ln -s "$CASE_DIR/linked-skills" "$HOME_DIR/.bioinfoflow/skills"
run_installer ARGS=--no-open
if [ "$STATUS" -ne 0 ] && assert_contains "$OUTPUT" "symlink"; then pass "rejects a symlinked skills directory"; else fail "rejects a symlinked skills directory"; fi
teardown_case

setup_case
run_installer ARGS=--dry-run
if [ "$STATUS" -eq 0 ] && [ ! -e "$HOME_DIR/.bioinfoflow" ]; then pass "dry-run does not mutate the installation"; else fail "dry-run does not mutate the installation"; fi
teardown_case

setup_case
run_installer ARGS=--no-open
if [ "$STATUS" -eq 0 ] && ! grep -Eq 'open |xdg-open ' "$CALLS"; then pass "no-open suppresses browser launch"; else fail "no-open suppresses browser launch"; fi
teardown_case

setup_case
run_installer ARGS=--no-open
if [ "$STATUS" -eq 0 ] && [ -f "$HOME_DIR/.bioinfoflow/install/docker-compose.local.yml" ] && [ -f "$HOME_DIR/.bioinfoflow/.managed-by-bioinfoflow" ]; then pass "separates control files from managed data"; else fail "separates control files from managed data"; fi
teardown_case

if [ -x "$INSTALLER" ] && [ -x "$ROOT/scripts/tests/install-test.sh" ]; then pass "installer scripts are executable"; else fail "installer scripts are executable"; fi

RELEASE_WORKFLOW="$ROOT/.github/workflows/release.yml"
if grep -q 'sh -n scripts/install.sh scripts/tests/install-test.sh' "$RELEASE_WORKFLOW" && \
   grep -q 'shellcheck -e SC2317 scripts/install.sh scripts/tests/install-test.sh' "$RELEASE_WORKFLOW" && \
   grep -q 'sh scripts/tests/install-test.sh' "$RELEASE_WORKFLOW" && \
   grep -q 'docker compose.*docker-compose.local.yml config' "$RELEASE_WORKFLOW" && \
   grep -q 'sha256sum -c SHA256SUMS' "$RELEASE_WORKFLOW" && \
   grep -q 'imagetools inspect' "$RELEASE_WORKFLOW"; then
  pass "release workflow verifies installer, Compose, checksums, and multiarch manifests"
else
  fail "release workflow verifies installer, Compose, checksums, and multiarch manifests"
fi

# The workflow expression is intentionally matched as a literal string.
# shellcheck disable=SC2016
if grep -Fq '[ "$GITHUB_REF_NAME" != "$version" ] && [ "$GITHUB_REF_NAME" != "main" ]' "$RELEASE_WORKFLOW" && \
   grep -q 'checkout_ref:.*needs.resolve.outputs.version' "$RELEASE_WORKFLOW" && \
   [ "$(grep -c '^[[:space:]]*ref:.*needs.resolve.outputs.version' "$RELEASE_WORKFLOW" || true)" -eq 0 ] && \
   grep -q 'gh release upload.*RELEASE_TAG.*--clobber' "$RELEASE_WORKFLOW"; then
  pass "release recovery packages fixed main assets while images use immutable tag source"
else
  fail "release recovery packages fixed main assets while images use immutable tag source"
fi

if grep -q 'AUTH_MODE == "dev"' "$RELEASE_WORKFLOW" && \
   grep -q 'DOCKER_SOCKET == "unix:///var/run/docker.sock"' "$RELEASE_WORKFLOW" && \
   grep -q 'source == "/var/run/docker.sock"' "$RELEASE_WORKFLOW"; then
  pass "release workflow asserts dev auth and Docker socket Compose contract"
else
  fail "release workflow asserts dev auth and Docker socket Compose contract"
fi

if grep -q 'ubuntu-24.04-arm' "$RELEASE_WORKFLOW" && \
   grep -q 'ubuntu-24.04' "$RELEASE_WORKFLOW" && \
   grep -q 'python3 -m http.server' "$RELEASE_WORKFLOW" && \
   grep -q 'BIOINFOFLOW_RELEASE_BASE_URL=http://127.0.0.1' "$RELEASE_WORKFLOW" && \
   grep -q 'installer_path=.*install.sh' "$RELEASE_WORKFLOW" && \
   grep -q "sh \"\$installer_path\" --no-open" "$RELEASE_WORKFLOW" && \
   grep -q -- '--uninstall' "$RELEASE_WORKFLOW" && \
   grep -q 'api/v1/system/ping' "$RELEASE_WORKFLOW"; then
  pass "release workflow smoke-tests the installer on amd64 and arm64"
else
  fail "release workflow smoke-tests the installer on amd64 and arm64"
fi

if grep -q 'docker/metadata-action@' "$ROOT/.github/workflows/container-release.yml" && \
   grep -q 'type=raw,value=main,enable=.*refs/heads/main' "$ROOT/.github/workflows/container-release.yml" && \
   grep -q 'type=sha,prefix=sha-,enable=.*refs/heads/main' "$ROOT/.github/workflows/container-release.yml" && \
   grep -q 'type=raw,value=.*inputs.release_version' "$ROOT/.github/workflows/container-release.yml" && \
   grep -q 'type=raw,value=latest,enable=.*inputs.release_version' "$ROOT/.github/workflows/container-release.yml" && \
   ! grep -q 'type=raw,value=latest,enable=.*refs/heads/main' "$ROOT/.github/workflows/container-release.yml" && \
   grep -q 'gh workflow run release.yml --ref' "$ROOT/.github/workflows/release-please.yml" && \
   grep -q 'release_version:' "$RELEASE_WORKFLOW" && \
   ! grep -q 'secrets: inherit' "$RELEASE_WORKFLOW"; then
  pass "numeric releases isolate stable aliases from development tags"
else
  fail "numeric releases isolate stable aliases from development tags"
fi

latest_flavor_count=$(grep -c 'latest=false' "$ROOT/.github/workflows/container-release.yml" || true)
if [ "$latest_flavor_count" -eq 3 ]; then
  pass "tag metadata cannot implicitly publish latest"
else
  fail "tag metadata cannot implicitly publish latest"
fi

if grep -qi 'signed checksum\|signed release' "$INSTALLER" "$RELEASE_WORKFLOW"; then
  fail "checksum wording does not claim cryptographic signing"
else
  pass "checksum wording does not claim cryptographic signing"
fi

SPECIAL_COMPOSE=$(docker compose --env-file "$ROOT/scripts/tests/fixtures/local-special-path.env" -f "$COMPOSE_SOURCE" config --format json 2>/dev/null || true)
if printf '%s' "$SPECIAL_COMPOSE" | jq -e '.services.backend.volumes[] | select(.source == "/tmp/Bioinfoflow Data:Local/state" and .target == "/tmp/Bioinfoflow Data:Local/state")' >/dev/null 2>&1 && \
   ! printf '%s' "$SPECIAL_COMPOSE" | jq -e '.services.backend.volumes[] | select(.source == "/tmp/Bioinfoflow Data:Local/install")' >/dev/null 2>&1; then
  pass "Compose renders managed paths containing spaces and colons"
else
  fail "Compose renders managed paths containing spaces and colons"
fi

printf '%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
