# Agent Tool and Adapter Stability Plan

## Status

Implemented and verified on 2026-08-17.

## Goal

Restore the basic Agent tool loop without coupling the frontend to the current
Harness or model provider. The stable Presentation Contract remains the only
frontend input. Harness history, model wire protocols, sandbox process launch,
and browser stream lifecycle are repaired at their own boundaries.

## Evidence and Violated Invariants

### Stale session stream

The live log posts commands to session `692b...` while two EventSource clients
repeatedly request deleted session `9000...0001`. The latter does not exist in
the runtime database. A stream error currently starts its own reconnect timer
before the owning hook has confirmed whether the session still exists.

Invariant: every reconnect is gated by a successful authoritative snapshot for
the same session ID. A confirmed 404 is terminal for that hook generation.

### macOS bash sandbox

Every local bash attempt exits before interpreting the requested command because
Seatbelt launches `bash` through `PATH`. In the affected backend process that
resolves Homebrew bash, while the profile does not grant its Homebrew dylib
closure. Even a command containing `/bin/zsh` fails because the outer shell has
already crashed.

Invariant: the sandbox adapter must launch a known bootstrap shell whose runtime
dependencies are part of the platform baseline. On macOS that is `/bin/bash`.

### Invalid plan terminates useful work

The two edit scenarios failed with durable reason `invalid_plan` and private
error `missing required tool arguments: step`. The edit itself completed. The
Harness treats a malformed `update_plan` control call as a terminal run error.

Invariant: presentation/control metadata is recoverable model output. Invalid
control input is returned privately as a tool error so the model can correct it;
it does not roll back or terminate completed user work.

### Ask-user response breaks Chat Completions order

The UI persisted a valid ask-user response and the Harness persisted a completed
tool result. The following DeepSeek request was rejected with HTTP 400. The
canonical history adapter currently inserts the durable `interaction_response`
as a user message between the assistant tool call and its tool result.

Invariant: provider-neutral history must preserve a valid tool round:
`assistant tool_call -> tool result`. The durable interaction entry remains in
the Presentation Contract and compaction evidence, but the model receives the
answer through the tool result exactly once.

## Design

1. `useAgentSession` owns Agent reconnect policy. On stream error it disposes
   the failed source, refreshes the snapshot, and opens a replacement stream
   only after that snapshot confirms the same session still exists.
2. `SeatbeltAdapter` launches `/bin/bash` explicitly. Command strings and inner
   shells remain unchanged.
3. `AgentLoop` converts failed `update_plan` calls into a private tool
   call/result exchange and continues the model loop. Successful plans continue
   to publish only stable `plan` entries.
4. `build_history_view` excludes standalone interaction-response input parts.
   The matching tool result is the canonical model input; the permanent entry
   remains available to the public projection and deterministic compaction.

## Regression Seams

- frontend hook: a broken stream is unsubscribed immediately and replacement
  subscription waits for snapshot recovery;
- sandbox adapter: Seatbelt argv uses `/bin/bash` regardless of process `PATH`;
- Agent loop: malformed plan, corrected plan, and final answer complete one run;
- history plus chat codec: ask-user response never separates a tool call from
  its tool result.

## Verification

Backend:

```bash
rtk uv run pytest tests/test_agent_harness/test_history_context_recovery.py \
  tests/test_agent_harness/test_harness.py \
  tests/test_agent_harness/test_sandbox_security.py \
  tests/test_model_runtime/test_chat_completions_codec.py
rtk uv run pytest
rtk uv run ruff check .
```

Frontend:

```bash
rtk bun run test tests/unit/hooks/use-agent-session.test.tsx \
  tests/unit/lib/agent/stream.test.ts \
  tests/integration/components/agent-workbench-v2.test.tsx
rtk bun run lint
```

Repository:

```bash
rtk git diff --check
```

## Completion Criteria

- deleted sessions cannot produce a permanent Agent events reconnect storm;
- local macOS bash executes before any user command is interpreted;
- malformed plan metadata is self-correctable and does not terminate the run;
- ask-user resumes DeepSeek-compatible Chat Completions with valid message
  ordering;
- frontend continues to render only the stable Presentation Contract;
- focused and broad verification pass.

## Verification Result

- Backend focused regression suite: 140 passed.
- Backend full suite: 2257 passed, 2 skipped.
- Frontend focused regression suite: 45 passed.
- Frontend full suite: 956 passed.
- Backend Ruff, frontend ESLint, and `git diff --check`: passed.
