# Remote Interactive Terminal Upgrade Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or equivalent focused worker/reviewer agents. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remote projects open a real interactive SSH PTY terminal in the bound remote project directory, while preserving the existing local terminal behavior.

**Architecture:** Keep the browser/WebSocket contract stable. Replace the unsupported remote terminal placeholder with backend-managed interactive transports: system `ssh -tt` for host-managed auth methods and AsyncSSH PTY processes for stored password/private-key auth. The terminal manager owns lifecycle, input, output, resize, safe relative `chdir`, session reuse, and cleanup for both local and remote sessions.

**Tech Stack:** FastAPI WebSocket, Python `pty`/`subprocess`, AsyncSSH, xterm.js, Next.js/React, pytest, Vitest/ESLint.

---

## Phase 0: Planning And Branch Setup

- [x] Confirm current worktree state and create `codex/remote-interactive-terminal`.
- [x] Write this implementation plan under `docs/plans/`.
- [x] Run `rtk git diff --check`.
- [x] Commit the plan as `docs: plan remote interactive terminal`.

## Phase 1: Backend Interactive Remote PTY

**Files:**
- Modify `backend/app/services/terminal_service.py`.
- Modify `backend/app/api/v1/terminal.py`.
- Modify `backend/tests/test_services/test_terminal_service.py`.
- Modify `backend/tests/test_api/test_terminal_api.py`.
- Modify `backend/tests/test_api/test_terminal_ws.py`.

- [x] Add failing tests showing remote terminal sessions are `running`, not `unsupported`, expose `target_type=remote`, start in `remote_root_path`, and forward input/resize to a remote interactive transport.
- [x] Add a small injectable remote terminal transport boundary so tests can use fakes without opening real SSH.
- [x] Implement system SSH PTY spawning for `agent`, `key_file`, and `ssh_config`-style connections, with `ssh -tt` and a quoted remote bootstrap command that runs `cd <remote_root_path> && exec "$SHELL" -i`.
- [x] Implement AsyncSSH PTY spawning for stored `password` and pasted `private_key` connections, reusing existing TOFU host-key behavior.
- [x] Keep `send_input`, `resize`, `change_directory`, `attach`, `detach`, session reuse, idle cleanup, close, and shutdown behavior consistent for local and remote sessions.
- [x] Ensure remote `chdir` only accepts relative paths under the remote project root.
- [x] Run focused backend tests:
  - from `backend/`: `rtk uv run pytest tests/test_services/test_terminal_service.py`
  - from `backend/`: `rtk uv run pytest tests/test_api/test_terminal_api.py tests/test_api/test_terminal_ws.py`
- [x] Commit as `feat: add remote interactive terminal sessions`.

## Phase 2: Frontend Terminal Dock Upgrade

**Files:**
- Modify `frontend/components/bioinfoflow/terminal/terminal-dock.tsx`.
- Modify `frontend/hooks/use-terminal-session.ts` only if backend state handling requires it.
- Modify `frontend/lib/types.ts` only if the terminal session contract changes.
- Modify `frontend/messages/en.json` and `frontend/messages/zh-CN.json` only for new user-facing copy.

- [x] Remove UI assumptions around remote `unsupported` sessions.
- [x] Make the dock header visually lighter: compact tab, warmer grey surface, softer divider, comfortable left/top spacing, and clear local/remote target label.
- [x] Keep xterm viewport stable and focused after connect/reconnect.
- [x] Run frontend checks:
  - `rtk bun run lint`
  - `rtk bun run test`
  - `rtk bun run lint:i18n` if messages changed.
- [x] Commit as `refactor: lighten terminal dock`.

## Phase 3: Documentation And Integration Verification

**Files:**
- Modify `docs/guides/remote-connections.md`.
- Modify `docs/reference/architecture.md` if needed.

- [x] Update remote connection docs to say project terminals now support interactive SSH PTY sessions.
- [x] Run backend broad verification:
  - `rtk uv run ruff check .`
  - `rtk uv run pytest`
- [x] Run frontend verification:
  - `rtk bun run lint`
  - `rtk bun run test`
- [x] Visual verification not needed for this phase; backend PTY behavior and terminal dock state are covered by automated tests.
- [ ] Commit as `docs: document remote terminal support`.

## Phase 4: Parallel Review And PR

- [ ] Spawn parallel review agents for backend security/lifecycle, frontend UI/UX, and test/doc coverage.
- [ ] Fix Critical and Important findings.
- [ ] Re-run the relevant backend/frontend verification commands after fixes.
- [ ] Commit review fixes if any.
- [ ] Push `codex/remote-interactive-terminal`.
- [ ] Open a draft PR with summary and verification evidence.
