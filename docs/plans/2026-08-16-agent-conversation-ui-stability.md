# Agent Conversation UI Stability

## Goal

Stabilize the Agent page behind a versioned BioinfoFlow-owned UI protocol while
restoring the polished empty state, composer, transcript, message actions, and
artifact experience lost during the Agent Harness rewrite.

Historical references:

- `9c4a06e8` is the visual reference for the centered empty-state composer.
- `34010661` is the last complete pre-Harness presentation implementation and
  may be mined only for protocol-independent renderers and styling.
- The current Harness contracts, runtime state, and private checkpoints remain
  authoritative. The old runtime, `/agent/fs/*`, Action/Decision vocabulary,
  and Plan/Act controls must not return.

## Stable seam

```text
Harness or provider private runtime
  -> backend Agent UI adapter/projector
  -> versioned Agent UI REST/SSE protocol
  -> frontend boundary decoder
  -> canonical Agent store
  -> transcript/composer view models
  -> stable renderer registry
```

The public module is `backend/app/services/agent_ui/`. A future Harness adds an
adapter at that seam; it must not add provider or Harness branches to frontend
rendering code.

## Product decisions

- Composer always retains Model, Permission, and Execution scope slots.
- Execution scope is `auto` or `manual(targetIds[])`; Manual always has at least
  one authorized target.
- A Message captures model, permission, and execution scope at submission.
  The resulting Run owns an immutable settings snapshot. Steer never changes it.
- A queued Message keeps the settings submitted with that Message.
- Local project Auto includes Local and visible SSH connections. Remote projects
  remain pinned to their project connection.
- Tool target selection is an optional `target` argument on workspace-bound
  tools. Target authorization, risk assessment, approval, and execution use the
  same immutable target snapshot.
- Dynamic target instructions are appended after the stable prompt. They never
  rewrite `session.prompt_snapshot` or durable memory.
- Harness starter prompts are normalized to at most four safe UI items. Invalid
  or unavailable suggestions fall back to localized built-ins.
- Reasoning, tools, and activity groups are collapsed by default. User disclosure
  state survives live-to-durable reconciliation.
- Retry appends a normal Message using current defaults. Edit restores canonical
  input into the composer. Neither operation rewrites history or creates branches.
- Artifact HTML is never executed. Unknown and oversized resources fall back to
  authenticated download.

## Protocol requirements

The Pydantic schema is the source of truth and is exported to
`docs/contracts/agent-ui-v1.json`. TypeScript is generated into
`frontend/lib/agent/protocol.generated.ts`; CI checks both generated artifacts.

The protocol includes:

- `protocol_version`
- capabilities and bootstrap defaults
- execution scope and safe execution target views
- immutable Run settings views
- safe tool target, timing, action, interaction, and artifact fields
- a stable `unknown` part for forward-compatible projection

REST paths and the six existing SSE event names remain stable during migration.
Malformed events, unsupported major versions, and revision/offset gaps trigger
an authoritative snapshot refresh.

## Core invariants

1. Frontend code never imports or branches on Harness/provider names.
2. The store contains one canonical append-only transcript.
3. Run settings freeze at Run creation and are not changed by later selectors.
4. Stable prompt content is an identical prefix across execution scopes.
5. Target authorization happens before risk assessment and cannot drift between
   approval and execution.
6. Public protocol data excludes credentials, raw checkpoints, raw tool output,
   unsafe absolute paths, and `user@host` labels.
7. Unknown protocol additions degrade locally instead of crashing the page.
8. SSE remains snapshot-first; the browser never guesses through a gap.
9. Missing capabilities disable one slot/card without restructuring Composer.
10. Retry/Edit append or refill only; durable history is immutable.

## Delivery stages

1. Characterize existing snapshot/SSE ordering, recovery, approval, and privacy.
2. Add the versioned backend protocol, projector seam, schema export, generated
   TypeScript, and runtime decoder.
3. Persist immutable Run settings and authorized execution target snapshots;
   route target-scoped tools through the frozen backend.
4. Add bootstrap/defaults/starter prompts.
5. Restore the centered empty state and docked Composer with stable selectors.
6. Move transcript grouping and live/durable reconciliation into pure view models
   and a stable part registry.
7. Add accessible message Copy/Retry/Edit actions and timestamps.
8. Add bounded safe artifact preview/download handling.
9. Finish semantic theme tokens, responsive behavior, accessibility, reduced
   motion, and streaming render performance.

Each stage is delivered as a vertical TDD slice and may be committed separately
once its focused and regression gates are green.

## Verification gates

Backend:

```bash
rtk uv run alembic upgrade head
rtk uv run pytest
rtk uv run ruff check .
rtk uv run python scripts/export_openapi_contract.py --check ../docs/contracts/openapi-v1.json
rtk uv run python scripts/export_agent_ui_contract.py --check ../docs/contracts/agent-ui-v1.json
```

Frontend:

```bash
rtk bun run generate:agent-protocol --check
rtk bun run lint
rtk bun run lint:i18n
rtk bun run lint:dead-code
rtk bun run test
rtk bun run build
```

Browser verification uses `AUTH_MODE=dev` in this worktree and covers desktop,
tablet, mobile, light/dark themes, keyboard-only navigation, reduced motion,
reconnect/restart, queued/steer/approval/recovery, actions, and artifact previews.
