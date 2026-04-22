# Release Readiness Review Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Harden the repo for an initial product release by fixing concrete security and logic issues, removing dead code, syncing docs with code, and preparing a clean handoff repository for a fresh Git history.

**Architecture:** Keep the scope tightly evidence-driven. Fix only issues confirmed by tests, static checks, or direct code-path review; avoid product-behavior churn unless the current behavior is clearly unsafe or inconsistent. Prefer additive guards, small API-compatible simplifications, and documentation that reflects the real runtime.

**Tech Stack:** FastAPI, SQLite, Better Auth, Next.js 16, React 19, TypeScript, pytest, Vitest, Ruff, Knip

### Task 1: Lock Down Interactive Runtime Surfaces

**Files:**
- Modify: `backend/app/api/v1/terminal.py`
- Modify: `backend/app/services/terminal_service.py`
- Modify: `backend/app/api/v1/scheduler.py`
- Modify: `backend/app/auth/dependencies.py` or `backend/app/api/deps.py`
- Test: `backend/tests/test_api/test_terminal_ws.py`
- Test: `backend/tests/test_api/test_terminal_api.py`
- Test: `backend/tests/test_api/test_scheduler_btop.py`

**Step 1: Write failing terminal authorization tests**

- Add a test proving an auth-enabled websocket connection without a valid session cookie cannot attach to an existing terminal session.
- Add a test proving a user cannot close a terminal session they do not own or cannot access.

**Step 2: Run the focused backend tests and verify they fail**

Run: `cd backend && uv run pytest tests/test_api/test_terminal_ws.py tests/test_api/test_terminal_api.py -v`
Expected: New authorization tests fail against the current implementation.

**Step 3: Write failing scheduler btop websocket auth test**

- Add a test proving the `/scheduler/btop/ws` socket rejects unauthenticated access when auth is enabled.

**Step 4: Run the focused websocket test and verify it fails**

Run: `cd backend && uv run pytest tests/test_api/test_scheduler_btop.py -v`
Expected: The new auth test fails against the current implementation.

**Step 5: Implement the minimal auth checks**

- Tie terminal websocket attachment to the same session cookie auth used by HTTP routes.
- Verify session/project access before terminal close and websocket attach.
- Require authenticated access for the scheduler btop websocket while preserving `AUTH_MODE=dev` behavior.

**Step 6: Re-run focused backend tests**

Run: `cd backend && uv run pytest tests/test_api/test_terminal_ws.py tests/test_api/test_terminal_api.py tests/test_api/test_scheduler_btop.py -v`
Expected: All pass.

### Task 2: Tighten Release Configuration and Version Consistency

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/config.py`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `RUNBOOK.md`
- Modify: `backend/README.md`
- Test: `backend/tests/test_smoke.py`

**Step 1: Write failing config/version tests**

- Add or extend tests for any new release-safety config, such as host validation or version consistency.
- Add a test capturing the expected FastAPI metadata behavior if the implementation changes.

**Step 2: Run the focused backend test and verify it fails**

Run: `cd backend && uv run pytest tests/test_smoke.py -v`
Expected: The new expectation fails before the implementation change.

**Step 3: Implement the smallest safe config changes**

- Introduce explicit release-safety settings only where they improve the default security posture without breaking local development.
- Remove obvious version drift between backend metadata, package manifests, and docs.

**Step 4: Re-run the focused backend test**

Run: `cd backend && uv run pytest tests/test_smoke.py -v`
Expected: Pass.

### Task 3: Remove Dead Code and Simplify Small Frontend Surfaces

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/lib/form-spec.ts`
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/format-utils.ts`
- Modify: any frontend files that still rely on removed exports
- Test: `frontend/tests/unit/lib/api.test.ts`

**Step 1: Confirm dead-code findings still reproduce**

Run: `cd frontend && bun run lint:dead-code`
Expected: Fails with the current unused dependency/export findings.

**Step 2: Remove only the confirmed dead code**

- Drop the unused `@codemirror/lang-json` dependency.
- Remove unused exported types/functions that are not referenced anywhere.
- Keep API contracts intact where types are still useful internally.

**Step 3: Tighten small frontend security affordances**

- Replace raw `window.open(..., "_blank")` calls with a safer shared helper where appropriate.

**Step 4: Re-run frontend static checks**

Run: `cd frontend && bun run lint && bun run lint:dead-code`
Expected: Both pass.

### Task 4: Sync Documentation With the Real Runtime

**Files:**
- Modify: `README.md`
- Modify: `RUNBOOK.md`
- Modify: `backend/README.md`
- Modify: `docs/api/reference.md`
- Modify: any codemap or overview doc made inaccurate by the code changes

**Step 1: Audit docs against the implemented runtime**

- Fix any references that no longer match authentication, runtime defaults, version numbers, or exposed endpoints.
- Remove placeholder release-facing copy that would look unfinished in a first public version.

**Step 2: Verify doc references**

Run: `rg -n "/api/v1/docs|1.0.0|v0.1|changeme|TODO: Replace" README.md RUNBOOK.md backend/README.md docs`
Expected: Only intentional references remain.

### Task 5: Verify, Tag, and Prepare the Fresh Repo Copy

**Files:**
- Modify: release metadata files as needed
- Create: clean copied repository outside the current `.git`

**Step 1: Run release verification**

Run: `cd backend && uv run pytest`
Expected: Pass, or document any blocked test subset.

Run: `cd frontend && bun run test`
Expected: Pass, or document any blocked test subset.

Run: `cd backend && uv run ruff check .`
Expected: Pass.

Run: `cd frontend && bun run lint && bun run lint:dead-code`
Expected: Pass.

**Step 2: Create the initial release tag**

- Use the synchronized version as the initial release tag.
- Keep the current repository and Git history intact.

**Step 3: Create a clean derivative repo**

- Copy the cleaned working tree to a sibling directory.
- Exclude Git metadata and ignored runtime artifacts.
- Initialize a brand-new `.git` there so follow-on work starts from a clean history.

**Step 4: Record the exact modified files and verification commands**

- Preserve the final modified file list.
- Preserve all verification commands run and their outcomes.
