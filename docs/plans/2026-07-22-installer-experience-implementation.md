# Installer Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep stable release installation immutable while adding concise stage output, actionable port-owner diagnostics, and runtime-selectable frontend and backend ports.

**Architecture:** Add one runtime configuration route to the Next.js frontend and resolve API URLs from its browser global before falling back to environment defaults. Persist validated ports in the installer environment and pass the chosen backend URL into the localhost frontend container. Keep direct browser HTTP, SSE, and WebSocket traffic and the existing numeric release image contract.

**Tech Stack:** POSIX shell, Docker Compose, Next.js 16, React 19, TypeScript, Vitest, GitHub Actions.

---

### Task 1: Runtime frontend API configuration

**Files:**
- Create: `frontend/lib/runtime/public-config.ts`
- Create: `frontend/app/runtime-config.js/route.ts`
- Create: `frontend/tests/unit/lib/runtime/public-config.test.ts`
- Modify: `frontend/app/layout.tsx`
- Modify: `frontend/lib/runtime/request-core.ts`
- Modify: `frontend/tests/unit/lib/api.test.ts`

- [ ] **Step 1: Write failing unit tests**

Test that the public route serializes `BIOINFOFLOW_PUBLIC_API_BASE_URL` safely,
that browser runtime configuration overrides the compiled default, and that
HTTP and WebSocket URLs use a custom backend port.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `rtk bun run test frontend/tests/unit/lib/runtime/public-config.test.ts frontend/tests/unit/lib/api.test.ts`

Expected: failures because the runtime configuration module and route do not
exist and request URL construction still uses the compiled constant.

- [ ] **Step 3: Implement the minimal runtime configuration seam**

Add a serializer returning a JavaScript assignment for
`window.__BIOINFOFLOW_RUNTIME_CONFIG__`, load `/runtime-config.js` with
`beforeInteractive` in the root layout, and resolve the API base URL at request
construction time.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `rtk bun run test frontend/tests/unit/lib/runtime/public-config.test.ts frontend/tests/unit/lib/api.test.ts`

Expected: all focused tests pass.

### Task 2: Configurable localhost ports

**Files:**
- Modify: `docker-compose.local.yml`
- Modify: `scripts/install.sh`
- Modify: `scripts/tests/install-test.sh`
- Modify: `scripts/tests/fixtures/local.env`
- Modify: `scripts/tests/fixtures/local-special-path.env`

- [ ] **Step 1: Write failing installer and Compose contract tests**

Add cases for `FRONTEND_PORT=3100 BACKEND_PORT=8100`, invalid ranges, identical
ports, persistence in `.env`, custom Compose mappings, and
`BIOINFOFLOW_PUBLIC_API_BASE_URL=http://localhost:8100/api/v1`.

- [ ] **Step 2: Run installer tests and verify RED**

Run: `rtk sh scripts/tests/install-test.sh`

Expected: the custom backend case fails because non-8000 ports are rejected and
the Compose mapping remains fixed.

- [ ] **Step 3: Implement validated port persistence and Compose wiring**

Accept decimal ports in the range 1-65535, reject identical ports, write both
values to the managed environment, use the selected host backend port in health
checks, and pass the runtime public API URL to the frontend container.

- [ ] **Step 4: Run installer tests and verify GREEN**

Run: `rtk sh scripts/tests/install-test.sh`

Expected: all installer contract tests pass.

### Task 3: Concise stages and actionable port diagnostics

**Files:**
- Modify: `scripts/install.sh`
- Modify: `scripts/tests/install-test.sh`

- [ ] **Step 1: Write failing output tests**

Require stable-release, asset verification, image download, startup, health,
and final URL stages. Require silent curl flags and bounded `lsof` details for
occupied ports without any `kill` invocation.

- [ ] **Step 2: Run installer tests and verify RED**

Run: `rtk sh scripts/tests/install-test.sh`

Expected: failures because curl progress and raw Compose progress remain and
port failures do not print owner details.

- [ ] **Step 3: Implement minimal output helpers**

Add plain stage and success helpers, switch downloads to `curl -fsSL`, suppress
successful Compose pull/start output, retain failure diagnostics, and print at
most the listener header plus matching records from `lsof`.

- [ ] **Step 4: Run installer tests and verify GREEN**

Run: `rtk sh scripts/tests/install-test.sh`

Expected: all installer tests pass with deterministic output.

### Task 4: Release smoke and documentation

**Files:**
- Modify: `.github/workflows/release.yml`
- Modify: `scripts/tests/install-test.sh`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `RUNBOOK.md`
- Modify: `docs/getting-started/docker.md`

- [ ] **Step 1: Add failing release workflow assertions**

Require the amd64 and arm64 smoke matrix to use `FRONTEND_PORT=3100` and
`BACKEND_PORT=8100`, verify both persisted values, and health-check the custom
backend port.

- [ ] **Step 2: Update workflow and documentation**

Document stable-release semantics, concise output, port-owner diagnostics, and
the retry form `FRONTEND_PORT=3100 BACKEND_PORT=8100 curl ... | sh`.

- [ ] **Step 3: Run workflow and documentation checks**

Run: `rtk actionlint .github/workflows/release.yml`

Run: `rtk git diff --check`

Expected: both commands exit successfully.

### Task 5: Full verification and publication

**Files:**
- Verify all modified files.

- [ ] **Step 1: Run shell verification**

Run: `rtk sh -n scripts/install.sh scripts/tests/install-test.sh`

Run: `rtk shellcheck -e SC2317 scripts/install.sh scripts/tests/install-test.sh`

Run: `rtk sh scripts/tests/install-test.sh`

- [ ] **Step 2: Run frontend verification**

Run from `frontend/`: `rtk bun run lint`

Run from `frontend/`: `rtk bun run test`

Run from `frontend/`: `rtk bun run build`

- [ ] **Step 3: Run release contract verification**

Run: `rtk docker compose --env-file scripts/tests/fixtures/local.env -f docker-compose.local.yml config`

Run: `rtk actionlint .github/workflows/release.yml`

Run: `rtk git diff --check`

- [ ] **Step 4: Commit and publish**

Stage only the planned files, commit with
`feat: improve localhost installer experience`, push the branch, open a ready
PR to `main`, and add `automerge` only after required checks are running.
