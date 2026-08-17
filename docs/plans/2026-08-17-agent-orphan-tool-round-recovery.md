# Agent Orphan Tool Round Recovery Plan

## Status

Implemented and verified on 2026-08-17.

## Evidence

Session `5c48de11-9c74-469e-8be1-730d02bb0a50` first failed while resolving a
remote Bash workspace because `BIOINFOFLOW_PUBLIC_API_BASE_URL` was not
configured. The assistant message had already committed three tool calls, but
the run terminated before any matching tool result was committed. Every later
plain-text Run reused that incomplete tool round and DeepSeek rejected the Chat
Completions request.

Separately, the Agent stream adapter still owns an internal reconnect loop even
though `useAgentSession` now owns snapshot-gated recovery. That duplicate owner
can continue requesting a deleted session.

## Invariants

- Every tool call exposed to a model has exactly one adjacent tool result before
  the next user or assistant turn.
- Workspace routing and runtime construction failures are ordinary failed tool
  results, not terminal Harness exceptions.
- Old incomplete histories remain resumable without rewriting public history.
- Agent SSE reconnect policy has one owner: `useAgentSession` after an
  authoritative snapshot. The transport performs no independent retry.

## Design

1. Normalize exceptions escaping routed workspace resolution or execution into
   failed `ToolResult` values with the original environment ID.
2. Repair legacy orphan tool calls only in the derived model input by inserting
   deterministic interrupted tool results before the next turn.
3. Disable internal retry in the Agent stream transport; the session hook
   disposes, snapshots, and creates a replacement subscription.
4. Keep the Presentation Contract unchanged. Durable run failures and original
   transcript entries remain visible exactly as recorded.

## Regression Seams

- routed workspace resolution raises before executing a remote tool;
- a permanent history contains a partial tool round followed by a user message;
- an Agent EventSource errors and time advances beyond maximum backoff;
- the next DeepSeek-compatible request receives a complete tool round.

## Verification

- Focused backend regression suite: 64 passed, including routed workspace
  failures, legacy history repair, recovery interaction ordering, and Chat
  Completions encoding.
- Focused frontend Agent stream and session-hook suite: 22 passed.
- Full frontend suite: 170 files and 957 tests passed.
- Full backend suite: 2258 passed and 2 skipped. Two unrelated shared-state
  flakes failed in the combined run (`database is locked` in a cross-worker
  cancellation test and transient LiteLLM xAI parameter-state drift); both
  passed immediately when rerun in isolation.
- Ruff and ESLint passed.
- `git diff --check`, PR CI, CodeQL, and Vercel checks remain required before
  rebase merge.
