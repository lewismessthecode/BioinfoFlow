# Agent Conversation Performance Plan

## Goal

Improve long Agent Core conversation usability by making the turn iteration budget
explicitly configurable, adding conversation-addressable URLs, and reducing the
initial payload used to render large historical conversations.

## Current Findings

- The loop uses `IterationBudget` and resolves runtime max iterations through
  `_max_iterations()` in `backend/app/services/agent_core/core/loop.py`.
- The runtime value comes from `AGENT_MAX_ITERATIONS`, which defaults to `90`.
- Local Codex config does not expose an equivalent turn-iteration setting in
  `~/.codex/config.toml`, so Bioinfoflow should own its setting.
- The `/agent` page stores the selected conversation in React context and local
  storage, so the URL cannot identify a conversation after refresh or sharing.
- `/agent/sessions/{session_id}/state` currently returns every session event.
  Long tool-heavy conversations therefore load a large payload and force a full
  timeline rebuild before the page settles.

## Design

1. Add an explicit `AGENT_MAX_ITERATIONS` setting with an evidence-backed default
   of `90`, matching Hermes Agent's default for most parent-agent tasks.
2. Keep `/agent` as the draft/default route and add `/agent/[sessionId]` as the
   canonical route for an existing conversation.
3. Update sidebar conversation selection to navigate to `/agent/{sessionId}`.
4. Let the runtime state API accept an event limit, returning all turns but only
   the most recent events needed for fast initial render. The SSE stream remains
   responsible for incremental updates.
5. Preserve the existing full-state endpoint behavior when no limit is supplied
   so older clients and tests keep working.

## Verification

- Backend: targeted API tests for default iteration settings and state event
  limiting, then `rtk uv run pytest` and `rtk uv run ruff check .` before PR.
- Frontend: targeted hook tests for URL navigation and state event limiting,
  then `rtk bun run lint`, `rtk bun run test`, and `rtk bun run lint:i18n`.
