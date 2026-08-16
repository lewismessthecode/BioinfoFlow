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

### Final screenshot acceptance

The final UI pass uses the supplied pre-refactor screenshots as the acceptance
reference and keeps the same Presentation Contract boundary:

- the Workspace action lives in the conversation header's top-right corner;
- the Workspace panel contains Files and Workflows only; Run Monitor and its
  dedicated panel code are removed;
- the draft canvas shows one quiet welcome sentence above a unified Composer,
  with no hero icon, explanatory paragraph, or capability-hint row;
- model, permission, and Auto/Manual environment controls share one compact
  height and baseline, and Auto is expressed once;
- three starter prompts render as flat hairline-separated rows without an outer
  card or section heading;
- timestamps are progressive disclosure on message hover/focus, and Copy appears
  once at the bottom of the final completed assistant response;
- completed activity groups and tool calls are compact and collapsed by default;
- one Run outcome produces one visible outcome row, and fenced code remains
  readable without breaking the Transcript width.

These are DOM and browser acceptance requirements, not additions to the Harness
transport contract.

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
- use ordinary code review only; do not start Codex Security scans;
- fix all actionable findings and rerun affected checks;
- rebase on current `origin/main` before publishing;
- push `codex/stabilize-agent-conversation-ui`;
- open one Conventional Commit titled PR;
- do not merge or enable auto-merge.

## Final screenshot acceptance: selector and shell restoration

The latest screenshot comparison adds these concrete acceptance criteria:

- model, permission, and environment controls reuse one Composer selector trigger
  primitive with the same fixed height, icon sizing, text metrics, chevron, focus
  treatment, and vertical alignment;
- their dropdowns reuse the same menu surface and compact row density; permission
  descriptions must not create a visually larger card system;
- the Draft view contains no starter section heading such as
  “从与当前项目相关的建议开始”;
- starter rows use plain check, message, and history icons without enclosing
  circles, bordered tiles, or filled icon backgrounds;
- a quiet bottom hint rotates between truthful `/` command and `@` mention
  guidance, matching the pre-refactor Draft layout;
- Workspace is an icon-only action registered in the application Navbar action
  group beside Terminal, never an absolutely positioned pill inside the Agent
  canvas;
- DOM/browser acceptance tests measure the three selector trigger heights and
  verify Navbar ownership, menu density, starter simplification, and both hints.

## Final screenshot acceptance: editorial transcript and decision UI

The DeepSeek and Codex reference screenshots refine the visual implementation
without changing the Presentation Contract or Conversation View Model:

- the main Agent canvas does not render a conversation title/model header card;
  generated titles continue to update only the left conversation sidebar;
- the Transcript reads as one continuous editorial document in a narrow column,
  with assistant prose unboxed and operational blocks expressed as compact rows;
- completed Thinking and tool/activity disclosures use a 34-40px summary row,
  concise one-line previews, muted metadata, and tight 10-14px rhythm rather than
  large nested cards or empty containers;
- the dock Composer does not show the visible labels “Adjust current task” or
  “Changes apply on the next run”; equivalent actions remain accessible through
  icon controls and accessible names where the capability still exists;
- Draft and dock Composer surfaces have a clearly distinguishable neutral
  surface, a visible one-pixel boundary, and no glow, gradient, or heavy shadow;
- model, permission, and environment selector text uses the same font size,
  line-height, icon box, text wrapper, chevron box, and baseline in addition to
  sharing the same outer trigger height;
- the Draft rotating slash/mention hint remains associated with the Composer but
  sits above the viewport edge with intentional breathing room;
- Ask User renders as one focused decision surface: a quiet category label,
  strong question, vertically stacked numbered option rows separated by
  hairlines, small recommendation metadata, optional free text where supported,
  and a compact navigation/action footer;
- Ask User does not create a grid of nested option cards, and its Light/Dark
  contrast remains semantic and keyboard/screen-reader accessible.

### TDD tracer slices

1. main-canvas header absence plus sidebar title refresh;
2. compact Thinking/tool/activity row behavior and Transcript rhythm;
3. Composer helper-label removal, surface contrast, hint position, and selector
   glyph/baseline geometry;
4. Ask User option selection, completion, keyboard semantics, and responsive
   single-surface layout;
5. Playwright geometry checks in Light/Dark desktop and a narrow viewport.

## Final screenshot acceptance: continuous activity and durable titles

The last comparison against the DeepSeek transcript and the earlier BioinfoFlow
draft state adds the following acceptance criteria without expanding the Harness
protocol surface:

- successful completion remains available in the stable Run audit data but does
  not become a visible Transcript row; failed or cancelled outcomes are inserted
  immediately after the final Transcript Block owned by that Run, so terminal
  rows from older Runs are never collected into an indistinguishable stack;
- one stable Run identity still projects at most one visible failure/cancellation
  outcome, using its latest revision;
- an activity group renders as a continuous sequence of individual compact tool
  disclosure rows (`Bash`, `Read`, `Edit`, errors, and similar operations), not as
  a visible “run N tools” summary card;
- each tool row owns its category icon, concise action summary, lifecycle state,
  duration, and collapsed public details; grouping remains a projection concern
  and never leaks Harness wording into the UI;
- active work ends the visible Transcript with a localized rotating spinner verb.
  Chinese and English use matching quiet verbs such as tracing clues, diving
  deeper, checking details, connecting context, and moving the task forward;
  reduced-motion users see a stable verb and assistive technology receives one
  non-rotating status announcement;
- the three Composer selectors share the same field wrapper in addition to the
  same trigger primitive. Their trigger row is top-aligned even while one setting
  shows pending or error feedback;
- the permission control is named Approval / 审批 because Harness
  `permission_mode` governs when approval is requested, not the workspace access
  boundary. Its three concise choices are Confirm changes / 更改确认, Confirm
  risks / 风险确认, and No approval / 免审批; the copy must state that workspace
  access and hard safety limits remain authoritative;
- Approval receives a public, sanitized action summary and input preview from the
  server presentation adapter. The card foregrounds the exact command or action,
  execution environment, and user-visible effects, while raw policy codes such as
  `ACT_HIGH` remain hidden implementation metadata;
- the Draft welcome line, centered Composer geometry, starter-row spacing, and
  CircleCheck / MessageCircle / RotateCcw icon language follow the pre-refactor
  implementation at `34010661` while keeping the current stable Composer API;
- the first meaningful user message assigns a compact automatic Conversation
  title only when no title already exists. Title derivation is a deterministic,
  Harness-independent session concern: it updates `SessionView.title` and the
  sidebar event path, but never enters canonical transcript history or prompt
  assembly, so the prompt-prefix cache identity is unchanged.

### Additional TDD tracer slices

1. two completed Runs remain available in `view.runs` without producing visible
   success rows, while failed/cancelled outcomes stay next to their owning Run;
2. grouped serial and parallel tools render as individual collapsed activity rows
   without group-count copy;
3. the running indicator rotates localized verbs with fake timers, stays fixed
   for reduced motion, and exposes one stable accessible status;
4. all three selector fields expose identical trigger/slot metrics and concise
   permission copy;
5. Approval fixtures prove exact command, target, and effects survive both live
   progress and refreshed durable history;
6. first-message title generation preserves Chinese and English text, does not
   overwrite manual titles, and refreshes the existing sidebar summary seam;
7. Draft DOM and Playwright geometry verify the restored welcome typography,
   starter icons, row density, Composer contrast, and Light/Dark parity.

## Final micro-polish: native language, scope clarity, and elevation

The final visual pass keeps the stable Presentation Contract unchanged and
clarifies only user-facing composition controls:

- generated starter prompts are short, imperative, and natural for the active
  locale; internal identifiers such as `bioinfoflow.demo.quickstart.v1` are
  excluded from generation context and cannot appear in the rendered fallback;
- the environment selector communicates scope rather than implementation:
  automatic scope is shown as All environments / 全部环境, while manual scope
  shows the selected environment name or count; status labels never wrap into
  vertical glyph columns at constrained menu widths;
- the empty-state welcome line uses the warmer Ready when you are. / 准备好了，
  随时开始 copy at a stronger but restrained display size;
- the send action is a true circular icon button with consistent hover, active,
  focus, disabled, touch-target, and Dark Mode states;
- the Composer surface uses a visible one-pixel boundary plus a restrained,
  background-tinted diffusion shadow. The shadow establishes elevation in both
  themes without glow, gradients, or stock heavy-shadow utilities.

### Final micro-polish TDD slices

1. locale and generator tests reject internal demo markers and assert concise,
   native-language starter prompts;
2. approval copy tests encode the three real Harness approval semantics without
   the ambiguous Auto / 自动 label;
3. environment DOM tests cover automatic scope, multi-target manual scope,
   truncated endpoints, and non-wrapping status badges;
4. Composer DOM and browser checks cover welcome typography, circular send
   geometry, border contrast, diffuse elevation, and Light/Dark parity.
