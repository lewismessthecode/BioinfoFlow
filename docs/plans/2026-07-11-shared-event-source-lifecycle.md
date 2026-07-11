# Shared EventSource Lifecycle Implementation Plan

**Goal:** Extract the repeated EventSource connection, retry timer, backoff, and
cleanup mechanics without changing any consumer's URL construction, event
parsing, credentials, reconnect predicate, or source-closing policy.

**Architecture:** Add a small `connectEventSource` primitive that owns one active
source, at most one reconnect timer, exponential backoff state, and disposal.
Callers provide the URL, `EventSourceInit`, retry predicate, failed-source close
policy, and a per-connection binding callback. Domain event names, JSON parsing,
cursor updates, React state, and callback semantics remain in the callers.

**Tech Stack:** TypeScript, React 19 hooks, browser EventSource, Vitest fake
timers, Testing Library `renderHook`.

---

## Preserved behavior matrix

| Behavior | Live runtime | Agent runtime | Resource hook |
| --- | --- | --- | --- |
| URL owner | `buildLiveApiUrl` | `buildApiUrl` with mutable `after_seq` | `buildApiUrl` |
| Credentials | `{ withCredentials: true }` | `{ withCredentials: true }` | omitted |
| Events | four named envelope events | `ready`, default message, known named events | `scheduler.resources` |
| Invalid JSON | ignored | ignored | ignored |
| Reconnect predicate | `readyState === CLOSED` | any error | `readyState === CLOSED` |
| Close failed source | no | yes | no |
| Backoff | 1s, x2, capped at 30s | 1s, x2, capped at 15s | 1s, x2, capped at 30s |
| Backoff reset | source open | source open | source open |
| Disposal | clear timer, close current source | clear timer, close current source | clear timer, close current source, set disconnected |

The shared primitive must prevent duplicate reconnect timers for repeated errors
from the same connection. It must not parse JSON, know event names, build domain
URLs, update the agent cursor, or own React state.

## Task 1: Characterize all three consumers

**Files:**

- Modify: `frontend/tests/unit/hooks/use-events.test.ts`
- Modify: `frontend/tests/unit/lib/agent-runtime/event-stream.test.ts`
- Create: `frontend/tests/unit/hooks/use-resource-stream.test.ts`

- [ ] Expand the fake EventSource helpers so tests can emit open, error,
  default-message, and named events and inspect close state.
- [ ] Cover exact URLs/query parameters and credentials for each consumer.
- [ ] Cover named/default bindings, valid delivery, and invalid JSON ignoring.
- [ ] Cover open/error callbacks and connection-state changes.
- [ ] Cover CLOSED-only versus any-error retry, failed-source closing policy,
  one pending timer, backoff progression/caps, reset on open, and cleanup.
- [ ] Cover agent `after_seq` advancing monotonically and being reused on the
  next connection.
- [ ] Run the focused suite and retain the expected RED that the shared
  lifecycle module does not exist yet or is not used yet.

Run from `frontend/`:

```bash
rtk bun run test tests/unit/hooks/use-events.test.ts tests/unit/hooks/use-resource-stream.test.ts tests/unit/lib/agent-runtime/event-stream.test.ts
```

## Task 2: Add the lifecycle primitive

**Files:**

- Create: `frontend/lib/runtime/event-source-connection.ts`
- Create: `frontend/tests/unit/lib/runtime/event-source-connection.test.ts`

- [ ] Write focused failing tests for one active source, one pending timer,
  configurable retry predicate/close policy, backoff sequence and cap, open
  reset, dynamic URL creation, and disposal.
- [ ] Implement only connection/timer/backoff/cleanup machinery.
- [ ] Keep source configuration and per-source binding callback inputs generic.
- [ ] Run the primitive test until green.

Run from `frontend/`:

```bash
rtk bun run test tests/unit/lib/runtime/event-source-connection.test.ts
```

## Task 3: Migrate consumers one at a time

**Files:**

- Modify: `frontend/lib/runtime/live-runtime.ts`
- Modify: `frontend/lib/agent-runtime/event-stream.ts`
- Modify: `frontend/hooks/use-resource-stream.ts`

- [ ] Migrate live runtime and rerun live plus primitive tests.
- [ ] Migrate agent runtime, retaining caller-owned parsing/event lists/cursor,
  then rerun agent plus primitive tests.
- [ ] Migrate resource hook, retaining caller-owned sampling/event derivation and
  state transitions, then rerun resource plus primitive tests.
- [ ] Run all four focused suites together and inspect timer cleanup output.

## Task 4: Verify, review, and commit

- [ ] Run `rtk bun run lint`.
- [ ] Run `rtk bun run lint:dead-code`.
- [ ] Run `rtk bun run test`.
- [ ] Run `rtk bun run build`.
- [ ] Run `rtk git diff --check` and review the full diff against the preserved
  behavior matrix.
- [ ] Sync `origin/main`, resolve any conflicts without changing the behavior
  contract, rerun the applicable verification gate, and commit as
  `refactor: share event source lifecycle`.
