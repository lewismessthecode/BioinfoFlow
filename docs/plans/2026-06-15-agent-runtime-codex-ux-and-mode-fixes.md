# Agent Runtime Codex UX And Mode Fixes

## Goal

Bring the Agent runtime closer to Codex / Claude Code behavior for plan-act
switching, durable streaming output, tool-call presentation, right-side
workspace panels, and terminal theming.

## Current Map

- Backend runtime core lives in `backend/app/services/agent_core/core/loop.py`.
- Tool registration and exposure are intentionally separate:
  `tools/__init__.py` registers all tools, `tools/toolsets.py` exposes per
  session/role.
- Streaming-visible output is currently stored mainly as `agent_events`.
  Final assistant text is committed to the transcript only for `assistant_final`
  turns; tool-call iterations append a tool-call transcript message.
- The current Agent UI is `frontend/components/bioinfoflow/agent-runtime/`.
  `AgentWorkbench` owns mode selection, the transcript, and the sidecar.
- `AgentTabbedPanel` is currently a rounded card. The Files tab calls
  `/agent/fs/tree` with no path and therefore defaults to `settings.repo_root`.
- `TerminalDock` computes an xterm theme from `useAppearance`, but visual
  shell/container classes still rely on general app tokens and need explicit
  synchronization checks.

## Fix Sequence

Each item should be verified and committed separately.

1. Plan/Act switching
   - Make the UI mode control clearly switch between plan and execution for the
     current session and for draft sessions.
   - Ensure the backend exposes the `plan` toolset in `/agent/toolsets`.
   - Confirm `exit_plan_mode` approval flips the session to execution and the
     frontend reflects it.
   - Tests: backend toolset/service tests and frontend hook/composer tests.

2. Stream persistence and stuck-turn recovery
   - Preserve streamed assistant thinking/text after tool calls and after
     refresh/reload.
   - Ensure a failed tool exposure attempt surfaces a visible assistant/error
     state instead of leaving the conversation apparently stuck.
   - Treat `tool is registered but not exposed for this session` as a recoverable
     user-visible runtime error with actionable output.
   - Tests: backend loop/event tests and frontend reducer/timeline tests.

3. Tool-call transcript UX
   - Replace tall per-tool cards with compact Codex-style collapsed rows.
   - Default collapsed, with explicit expand affordance for arguments.
   - Group repeated tool calls in a dense list so long workflows do not push
     assistant text out of view.
   - Tests: frontend transcript tests.

4. Right sidecar and Files tab
   - Restyle the sidecar as a Codex-like drawer attached to the right edge,
     not a floating rounded card.
   - Keep pending decisions pinned, but make tabs dense and content-first.
   - Make the Files tab open at the project directory when a project context is
     available; fall back to repo root only when no project directory exists.
   - Reference: inspect `claude-code-bible` only for interaction patterns; use
     local React/Radix primitives already in the app.
   - Tests: frontend component tests and backend fs endpoint tests.

5. Terminal theme synchronization
   - Ensure xterm theme, terminal dock surface, header, and app theme all switch
     together when the page theme changes.
   - Tests: frontend terminal dock/theme tests.

6. Visual verification and PR completion
   - Run backend and frontend verification matching touched files.
   - Run `AUTH_MODE=dev` local browser checks for `/agent` and capture desktop
     screenshots for transcript, sidecar, files tab, and terminal theme.
   - Push, open/update PR, resolve review comments, wait for CI/CD, then merge
     only when the PR is clean.

## Invariants

- A registered tool must never imply exposure.
- The user must see why a turn stopped, including exposure-policy failures.
- Streaming output that appeared in the transcript must survive state refresh.
- Read-only UI filesystem browsing must remain confined by `FilesystemPolicy`.
- Tool-call details should be available, but not dominate the main transcript.
- UI text changes must update both `frontend/messages/en.json` and
  `frontend/messages/zh-CN.json`.
