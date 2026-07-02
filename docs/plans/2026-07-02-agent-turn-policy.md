# Agent Turn Policy Implementation Plan

Goal: prevent overlapping active assistant turns when the user sends a message while Bioinfoflow is already responding.

Architecture: keep the backend turn API unchanged and add a small frontend policy layer around the existing composer submit path. The policy has two states that matter: `idle` sends immediately; `active` either interrupts the current turn before sending or queues the draft until the current turn is no longer active. A local user preference controls the choice.

Policy:

- `interrupt`: the default. Submitting during an active turn calls `interrupt()` first, then creates the new turn. This matches Codex-style "steer or replace the current active turn" behavior.
- `queue`: submitting during an active turn stores the draft locally, clears the composer, shows queued draft state in the transcript via the existing optimistic-turn path only when it becomes active, and sends it after the active turn leaves `running`/`loading`.

Implementation phases:

1. Add a small `agent-turn-policy` preference module under `frontend/lib/agent-runtime/` with localStorage read/write helpers and tests.
2. Add TDD coverage in `AgentWorkbench` for interrupt and queue submission semantics, then implement the minimal queue/interrupt submit coordinator.
3. Add the setting in `Settings > Appearance` near other local experience preferences, with English and Chinese messages and a focused settings test.
4. Run frontend verification: targeted tests, `bun run lint:i18n`, `bun run lint`, and `bun run test` if practical.
5. Request parallel review agents, fix findings, then push and open a draft PR.

Validation notes:

- No backend migration is needed.
- No LLM service is required for automated tests because the submit path is mocked.
- The UI should never show two independently active assistant turns caused by one user interjection.
