# Agent conversation stability and UI restoration

## Status

Accepted for TDD implementation. Work will be delivered as one reviewable PR in
three committed phases and will not be merged automatically.

## Problem

PR #230 replaced the Agent Harness and also deleted the mature Agent conversation
UI/runtime. The replacement exposed the new backend successfully, but regressed
the centered Composer, execution selector, starter prompts, Transcript density,
theme behavior, and several interaction details. Later polish restored parts of
the experience without establishing a boundary that can survive another Harness
replacement.

The stable visual reference is commit `34010661`. The last end-to-end
multi-environment behavior before the Harness replacement is commit `aa64e451`.
Neither implementation is restored wholesale: the first is a visual and behavior
reference, while the second supplies domain evidence for Auto/Manual execution.

## Product outcome

BioinfoFlow provides a Claude Code/Codex-style Agent Conversation:

- a new Conversation starts with a refined centered Composer;
- the Composer moves into a bottom dock when work begins;
- model, permission, and environment selectors remain visible and editable;
- project-aware starter prompts appear without blocking input;
- assistant text remains primary while reasoning, tools, interactions, artifacts,
  outcomes, timestamps, and scroll controls remain available through progressive
  disclosure;
- Light and Dark themes use the same semantic visual hierarchy;
- replacing the Agent Harness cannot replace or crash the conversation renderer.

Plan/Act is explicitly excluded until a Harness exposes a real selectable mode.

## Domain and architecture

```text
Harness-private state
        -> server Harness adapter
        -> versioned Presentation Contract
        -> frontend transport validation
        -> Conversation projection
        -> stable Conversation View
        -> Composer and Transcript UI
```

### Public boundary

The Presentation Contract owns product semantics only. It does not expose leases,
checkpoints, provider continuation objects, private tool state, credentials, or
Harness-specific event names.

The frontend separates:

- `transport`: validated HTTP/SSE DTOs and protocol versions;
- `projection`: Snapshot/Event reconciliation, migrations, ordering, and dedupe;
- `conversation-model`: stable UI-only Conversation, Composer, Transcript Block,
  active work, and capability types;
- `ui`: renderers that consume only the conversation model.

No UI component may import backend transport contracts. Unknown versions, events,
parts, and tools produce a safe diagnostic Transcript Block while known content
continues rendering.

### Conversation and Run settings

BioInfoFlow follows the Codex setting model documented in
`docs/research/2026-08-16-openai-codex-turn-settings-semantics.md`:

- model, permission, and environment scope are sticky Conversation settings;
- selectors can change while a Conversation exists;
- the server confirms requested changes with an authoritative settings revision;
- an active Run keeps the immutable Turn Execution Config captured at start;
- queued messages use the latest confirmed settings when they actually start;
- historical Runs retain their effective configuration for audit, without adding
  configuration banners to the main Transcript;
- the current settings remain visible in the Composer.

Model changes preserve canonical history and the Conversation prompt-cache key.
Provider-specific incremental continuation may be discarded when its request
identity no longer matches.

### Execution environments

Auto exposes local and every authorized SSH environment in the Workspace. Manual
exposes the user-selected subset and supports Local plus multiple SSH environments.
One Run may use multiple environments through separate tool calls.

The tool model is:

```text
list_environments()
read(environment_id?, path, ...)
bash(environment_id?, command, ...)
edit(environment_id?, path, ...)
write(environment_id?, path, ...)
```

Environment IDs are opaque server-owned identifiers. The frontend never submits
hosts, usernames, roots, or credentials. A Workspace Router resolves the requested
environment, checks membership in the Run's immutable Environment Scope, refreshes
authorization, applies permission/approval middleware, selects the backend, and
records the resolved environment with the Tool Result.

There is no mutable global current environment. Dynamic environment IDs never
appear as tool-schema enums. `list_environments` performs progressive discovery,
and unavailable environments return a typed result the Agent can explain.

### Prompt stability

- stable identity, core instructions, and stable tool schemas remain byte-stable;
- the Conversation ID remains the prompt-cache key;
- project and session context is frozen or appended without rewriting the prefix;
- volatile availability or environment status is obtained through tools or a
  typed per-Run context suffix;
- volatile context is excluded from canonical-history continuation identity;
- settings changes append an explicit context diff rather than rebuilding the
  stable prompt.

### Reasoning

Every textual reasoning field returned by a provider is normalized as a durable
`reasoning_trace` with provider, model, source field, truncation, and timestamps.
It streams and remains expandable after refresh. Encrypted continuation, signatures,
and opaque provider state remain private and never enter SSE, history, logs, or UI.

The UI labels this content as Thinking / Reasoning Trace rather than claiming it
is a provider's complete private Chain of Thought.

### Starter prompts

Starter prompts are generated asynchronously from a bounded Project fingerprint,
cached server-side, and never create a hidden Conversation or Run. The UI remains
interactive while generation is pending. When no provider exists, generation
fails, or the cache is cold, three deterministic localized fallbacks are used.

## Visual restoration

### Draft state

- approximately 42rem centered reading/composer column;
- contextual prompt above one unified Composer surface;
- textarea is visually transparent in both Light and Dark themes;
- control row contains context, model, permission, Auto/Manual environment, voice,
  and send controls;
- up to three starter prompts and one honest capability hint appear below;
- no Plan/Act control.

### Conversation state

- approximately 46rem centered Transcript column;
- the same Composer becomes a compact bottom dock;
- user messages use a quiet right-aligned surface;
- assistant prose is unboxed;
- tool and activity groups use flat disclosure rows, not nested cards;
- Thinking is collapsed after completion and shows duration;
- Approval, Ask User, Recovery, and Artifact content retain dedicated lifecycle
  cards;
- timestamps, copy, retry where supported, stop/steer, and return-to-latest remain
  discoverable;
- the Workspace action stays visible but does not dominate the canvas.

### Theme and responsiveness

- use existing semantic theme tokens and configured typefaces;
- add no new icon or animation framework;
- remove the Composer's inherited `dark:bg-input/30` inner rectangle with an
  explicit transparent/unstyled textarea treatment;
- support desktop, tablet, mobile, keyboard, screen reader, and reduced motion;
- preserve content visibility and stable scroll anchoring for long Transcripts.

## TDD seams

Tests are written only against these accepted public seams:

1. serialized HTTP/SSE Presentation Contract behavior;
2. Workspace Router and tool execution behavior;
3. pure Conversation projection output;
4. Composer/Transcript behavior observable through the DOM;
5. Playwright interaction and screenshot baselines.

Tests do not mock private helpers, assert internal call order, or use CSS snapshots
as the only behavioral proof.

## Phase 1: Presentation Contract

Vertical slices:

1. add protocol version validation and unknown-event fallback;
2. project authoritative Snapshot/history/live state into stable Transcript Blocks;
3. migrate supported historical entry versions server-side;
4. remove UI imports of transport contracts;
5. add golden traces covering empty, active, interaction-required, failed, completed,
   duplicate, out-of-order, reconnect, and unknown content.

Phase commit: `refactor: stabilize agent presentation contract`

## Phase 2: settings and environment routing

Vertical slices:

1. add requested/effective Conversation settings revisions;
2. capture immutable Turn Execution Config when a Run starts;
3. make model and permission changes apply to subsequent Runs;
4. add Environment Scope and safe environment summaries;
5. add `list_environments` and Workspace Router;
6. route read/bash/edit/write through an explicit environment ID;
7. preserve approval, authorization, fencing, audit, and artifact behavior;
8. keep stable prompt identity and append settings/environment context diffs.

Phase commit: `feat: add codex-style agent turn settings`

## Phase 3: UI restoration

Vertical slices:

1. restore the centered and docked Composer presentations;
2. restore model, permission, and Auto/Manual environment controls;
3. add generated and fallback starter prompts;
4. restore stable Transcript Blocks for reasoning, tools, activity groups,
   interactions, artifacts, outcomes, timestamps, and scrolling;
5. fix Dark Mode and responsive states;
6. add deterministic browser fixtures and visual baselines.

Phase commit: `feat: restore agent conversation experience`

## Verification

Backend:

```bash
rtk uv run pytest
rtk uv run ruff check .
```

Frontend:

```bash
rtk bun run lint
rtk bun run lint:i18n
rtk bun run lint:dead-code
rtk bun run test
rtk bun run build
```

Browser:

- Draft and active Conversation;
- Light and Dark;
- desktop and mobile;
- Auto and Manual multi-environment selection;
- settings update during an active Run;
- reasoning, tool group, approval, artifact, failure, reconnect, and unknown block;
- scroll follow and return-to-latest;
- no-provider starter fallback.

## Review and delivery

- commit each phase separately;
- run Standards and Spec reviews against `origin/main` in parallel;
- run focused security/authorization review for environment routing and public
  reasoning projection;
- fix all actionable findings and rerun affected checks;
- rebase on current `origin/main` before publishing;
- push `codex/stabilize-agent-conversation-ui`;
- open one Conventional Commit titled PR;
- do not merge or enable auto-merge.
