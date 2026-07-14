# Agent Turn Durable Ownership Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development and superpowers:systematic-debugging task-by-task. Do not commit in this delegated phase.

**Goal:** Make AgentCore turn recovery and approval resume safe across processes, lease expiry, stale jobs, and long-running model/tool operations.

**Architecture:** Add an explicit per-claim owner token to durable turn state and make repository compare-and-set methods the only ownership boundary. A small ownership coordinator renews the lease from a separate database session, exposes ownership checks to the loop and tool executor, and prevents stale workers from publishing transcript/tool results or completing a turn. Recovery and approval resume both use atomic eligibility claims; resume additionally proves that the action belongs to the latest unresolved assistant tool-call batch.

**Tech Stack:** Python 3.13, FastAPI service layer, SQLAlchemy async, SQLite/PostgreSQL portable conditional updates, Alembic, pytest-asyncio.

---

### Task 1: Specify durable claim and recovery invariants

**Files:**
- Modify: `backend/tests/test_agent_core/test_runtime_reliability.py`
- Modify: `backend/tests/test_agent_core/test_model_runtime_integration.py`

- [ ] Add a two-session test where startup recovery sees a RUNNING turn with a future lease and must skip it without changing state or enqueueing work.
- [ ] Add a deterministic stale-job test where a prior approval batch is already paired, a second assistant approval batch is current, and the old action resume returns before claiming the turn.
- [ ] Run the focused tests and verify they fail because recovery is read-then-write and resume claim does not validate the latest unresolved batch.

### Task 2: Add generation-safe turn ownership persistence

**Files:**
- Modify: `backend/app/models/agent_core.py`
- Create: `backend/alembic/versions/0045_agent_turn_owner_token.py`
- Modify: `backend/app/repositories/agent_core_repo.py`
- Test: `backend/tests/test_agent_core/test_runtime_reliability.py`

- [ ] Add nullable `owner_token` to `agent_turns`; every claim writes a fresh UUID token and terminal/wait transitions clear it.
- [ ] Add portable repository CAS methods to claim queued/run recovery, claim current approval resumes, renew only the matching token, test current ownership, and complete/update only the matching token.
- [ ] Make recovery atomically transition only expired or unleased candidates; active leases remain untouched.
- [ ] Run focused repository/recovery tests and verify green on SQLite.

### Task 3: Gate approval resumes to the current unresolved batch

**Files:**
- Modify: `backend/app/services/agent_core/transcript/store.py`
- Modify: `backend/app/services/agent_core/approval_batches.py`
- Modify: `backend/app/services/agent_core/runtime.py`
- Test: `backend/tests/test_agent_core/test_model_runtime_integration.py`

- [ ] Resolve the latest committed assistant tool-call batch for the turn and determine whether each call has a committed tool result.
- [ ] Before the turn claim, return unchanged unless the requested action is in the latest unresolved batch and remains resume-eligible.
- [ ] Repeat batch eligibility inside the repository claim boundary using durable action state so concurrent/stale jobs cannot claim after the batch has moved on.
- [ ] Preserve recovery-enqueued RUNNING/no-lease REQUESTED actions and existing batch barrier behavior.

### Task 4: Heartbeat and fence long operations

**Files:**
- Create: `backend/app/services/agent_core/ownership.py`
- Modify: `backend/app/services/agent_core/runtime.py`
- Modify: `backend/app/services/agent_core/core/loop.py`
- Modify: `backend/app/services/agent_core/tools/specs.py`
- Modify: `backend/app/services/agent_core/tools/executor.py`
- Test: `backend/tests/test_agent_core/test_model_runtime_integration.py`
- Test: `backend/tests/test_agent_core/test_runtime_reliability.py`

- [ ] Add deterministic tests that replace an expired owner during a blocked model/tool call and prove the stale owner cannot append an assistant/tool message, overwrite action recovery state, or complete the turn.
- [ ] Start a separate-session heartbeat for each claimed worker; renew by `turn_id + owner_token + RUNNING`, and mark ownership lost when renewal fails.
- [ ] Check current ownership before and after long model/tool calls, before transcript/tool-result/action-result publication, and before final turn transition.
- [ ] Cancel/stop stale workers without emitting terminal state for the replacement owner.
- [ ] Condition final turn state updates on the owner token and clear the token only as part of the successful transition.

### Task 5: Regression verification

**Files:**
- Verify all modified backend files.

- [ ] Run `rtk uv run pytest tests/test_agent_core/test_runtime_reliability.py tests/test_agent_core/test_model_runtime_integration.py -q` from `backend/`.
- [ ] Run `rtk uv run pytest tests/test_agent_core tests/test_model_runtime -q` from `backend/`.
- [ ] Run `rtk uv run ruff check app/services/agent_core app/repositories/agent_core_repo.py app/models/agent_core.py tests/test_agent_core tests/test_model_runtime` from `backend/`.
- [ ] Run an Alembic upgrade to head against a fresh temporary SQLite database.
- [ ] Report changed files plus RED/GREEN evidence to the parent agent without committing.

## Completion Record

Implemented on 2026-07-13. The ownership-specific regressions pass, the full
AgentCore plus model-runtime slice passes (351 tests), Ruff passes, and a fresh
SQLite database upgrades through migration `0045`.

### Atomic publication follow-up

The initial heartbeat checks still left a check-then-publish window. Owned
transcript messages, ledger events, action creation/terminal updates, artifact
registration, Responses continuation metadata, and transcript compaction now
use repository-native conditional writes. Each write validates the current
`agent_turns.owner_token` in the database statement and fences the turn row in
the same transaction before commit. Non-owned service operations keep their
existing repository paths by omitting the optional owner token.
