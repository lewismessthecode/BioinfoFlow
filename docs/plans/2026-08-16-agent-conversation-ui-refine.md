# Agent conversation UI refine and refactor

## Status

Accepted for implementation. This plan restores the interaction quality lost
during the Agent Harness rewrite without restoring the legacy runtime or
starting a speculative cross-Harness protocol migration.

## Goal

Make `/agent` feel calm, legible, controllable, and trustworthy across new and
historical conversations:

- preserve the real order of Thinking, response, tool, plan, interaction, and
  artifact activity;
- keep stop, steer, approve, workspace, progress, and artifact actions visible;
- keep details available through progressive disclosure without showing raw
  commands, arguments, output, or secrets by default;
- restore the centered new-conversation Composer and the compact docked
  conversation Composer;
- deliver equivalent Light/Dark, desktop/tablet/mobile, keyboard, and screen
  reader behavior;
- keep the frontend attached to the existing public Snapshot/Event contracts
  instead of coupling it to private Harness implementation details.

## Product invariants

1. **Readable:** activity is rendered in the order the user experienced it.
2. **Controllable:** the next meaningful action remains discoverable while the
   Agent is running, waiting, failed, or complete.
3. **Traceable:** public details can be expanded and inspected, but the default
   transcript stays quiet and the backend owns the disclosure boundary.

These invariants take priority over matching any screenshot pixel-for-pixel.
The pre-rewrite UI is a reference for interaction capability and information
density only; its runtime logic is not a migration source.

## Scope decisions

### Included

- An ordered frontend activity view model over the current authoritative
  `SessionSnapshot` and `AgentEvent` state.
- Compact Thinking disclosure, including a transient running state, public
  reasoning summary, and full Chain of Thought when the Harness explicitly
  supplies displayable content.
- Flat, whole-row-clickable tool activity with backend-produced, redacted
  `public_details`.
- Removal of duplicated live tool rows when the corresponding durable tool call
  already exists in history.
- Updated plan checklist rendering without exposing internal revision labels.
- Centered Draft Composer and bottom-docked conversation Composer with context,
  model capability, permission, voice, steer/stop, and send controls.
- A permanently discoverable desktop workspace button and inline progress /
  artifact actions that open the appropriate LiveDeck tab.
- Light/Dark, responsive, reduced-motion, keyboard, focus, and screen-reader
  refinement.
- Focused performance work needed for long transcripts and streaming updates.

### Explicitly excluded

- A Plan/Act selector. The current Harness has no selectable Plan Mode.
- A new `agent_protocol/` package, Harness registry, or Pi adapter.
- Guessing unsupported capabilities in the UI.
- Rendering server-private recovery state, hidden model context, or content the
  Harness did not explicitly publish.
- Reusing legacy runtime code or keeping two rendering systems alive.

Plan entries remain visible because they are activity, not because a Plan Mode
exists. A future mode selector must be capability-driven after a second real
Harness proves the seam.

## Architecture

### Stable data boundary

Keep the current transport and reducer as the stable boundary:

```text
Harness history + active run
        -> public Snapshot / AgentEvent
        -> applyAgentEvent()
        -> ordered Activity view model
        -> transcript renderers
```

The frontend view model is derived display state. It does not become a second
session store and does not invent provider-specific meaning.

The current contract cannot reconstruct arbitrary cross-type interleaving that
was never assigned a shared sequence number. For the current Harness lifecycle,
durable entry sequence plus message-part order is authoritative. Unmatched live
tool progress is appended as a recovery item. If a future Harness requires
arbitrary interleaving to survive refresh, add one authoritative public activity
sequence then; do not infer it in the browser now.

### Activity view model seam

Add `frontend/lib/agent/activity.ts` with a small public interface that:

- preserves assistant part order;
- merges only adjacent tools belonging to the same group;
- matches live `tool_progress` to durable `tool_call` items by call ID;
- updates status at the durable timeline position;
- excludes the same tool from the active-run tail;
- retains unmatched live tools as visible recovery activity;
- returns typed `thinking`, `response`, and `tool_group` items without exposing
  component state.

Thinking and tool disclosure state belongs to the renderer and uses stable IDs
that do not include mutable status or revision values.

### Public tool-detail seam

The browser must not receive raw tool arguments merely because they are hidden
in a collapsed row. Extend the backend public contract with a structured detail
model:

```python
class ToolPublicDetail(StrictContract):
    id: str
    kind: Literal[
        "command",
        "working_directory",
        "path",
        "input",
        "output",
        "changes",
        "error",
        "metadata",
    ]
    label: str | None = None
    value: str
    format: Literal["text", "code", "path", "json", "diff"] = "text"
    copyable: bool = False
    truncated: bool = False
    redacted: bool = False
```

Add `public_details` with an empty default to public progress and historical
tool parts. Preserve raw internal history for model context and recovery, but
project it on every Snapshot, SSE event, and historical entry response.

Rules:

- public arguments are `{}` and raw textual output is absent;
- errors are stable public messages, not raw exceptions;
- known tools use explicit allowlisted projections;
- unknown tools expose no details by default;
- `bash` may expose a redacted command and normalized working directory;
- `read` exposes path/range metadata, not file contents or image Base64;
- `write` and `edit` expose path/change metadata, not written or replaced text;
- `update_plan` and `ask_user` are rendered by their dedicated activity types;
- known secret values, sensitive field names, absolute workspace prefixes,
  control characters, and excess length are removed before serialization;
- suspicious values that cannot be made safe are omitted with a public hidden
  detail rather than partially leaked.

The frontend renders only `public_details` and never falls back to legacy
`arguments`, raw output, or raw error fields.

## Visual system

### Transcript

- Use one centered reading column, approximately `46rem` maximum width.
- Turns use whitespace and restrained separators instead of nested cards.
- User messages use a quiet right-aligned bubble; assistant prose is unboxed.
- Historical and active content share the same visual grammar.
- Long transcript rows retain `content-visibility` and stable scroll anchoring.
- The return-to-latest action includes text and does not rely on an unlabeled
  icon.

### Activity rows

- Activity is flat. A group uses one subtle left guide, not an outer card plus
  nested child cards.
- Tool collapsed rows contain status, name, human summary, duration, and a
  disclosure affordance only.
- Commands, arguments, paths, output, and stacks are mounted only inside the
  expanded public-details region.
- The entire summary row is a real button with `aria-expanded` and
  `aria-controls`.
- Running, failed, approval-blocked tools may start expanded; complete and
  cancelled tools start collapsed. A user choice survives subsequent status
  updates.
- Empty public details produce no disclosure affordance.
- Detail regions use a low-contrast semantic surface, monospace for code, a
  bounded output height, and copy actions only for explicitly copyable values.

### Thinking

- While content is not yet available, show a compact `正在思考…` / `Thinking…`
  status and elapsed time.
- With content, render an expandable row; the collapsed summary is one concise
  line and the expanded region contains only content explicitly published by
  the Harness.
- Completed Thinking defaults collapsed and may show `思考了 12 秒`.
- Streaming revisions preserve the user's expansion state.
- Do not wrap Thinking in a large card or infer hidden reasoning from tool use.

### Plan

- Render the latest plan revision as one in-place checklist.
- Show meaningful progress such as `2/4`; hide internal revision numbers.
- Keep complete items quiet and current items clear without excessive animation
  or strike-through.
- Rendering a plan never implies that a Plan Mode selector exists.

### Composer

- Draft state combines the page prompt, up to three contextual starters, and a
  centered Composer around `42rem` wide, slightly above the optical center.
- Active/history state uses the same Composer in a bottom dock aligned to the
  transcript column.
- The Composer is one restrained `20–24px` radius surface; the textarea has no
  separate box.
- Its compact control row contains context, model capability, permission,
  voice, steer/stop, and send. Unsupported controls are omitted.
- Model selection is interactive only when the model catalog offers a real
  choice; otherwise show the current model as informational text.
- Draft input begins around `80px`; docked input begins around `48px`; both grow
  to a bounded maximum.
- Submission failure preserves the draft and appears adjacent to the Composer.
- On small screens, secondary controls may wrap or move into an explicit menu,
  while send, stop, and approval actions remain visible.

### Header and workspace

- Keep the conversation header approximately `44–48px` high.
- Show title and model as primary/secondary information.
- Show connection state prominently only when connecting, reconnecting, or
  offline.
- A labeled workspace action remains visible on desktop and mobile even when
  LiveDeck is collapsed.
- Inline `查看进度` / `查看产物` actions open LiveDeck on the relevant tab.
- Desktop LiveDeck may remember open state, active tab, and width; tablet/mobile
  use a Sheet or overlay so the transcript retains a readable width.

### Theme, motion, and iconography

- Use existing semantic theme tokens; add no hardcoded light-only colors.
- Dark surfaces use charcoal/zinc hierarchy rather than pure black and weaken
  decorative borders while preserving focus, error, warning, and approval
  contrast.
- Keep the repository's configured shadcn/New York/Radix/Lucide system. Do not
  add a second icon library for this refactor.
- Motion is short, restrained, transform/opacity based, and removed when
  `prefers-reduced-motion` requests it.
- No gradients, heavy shadows, glass effects, or repeated card containers.

## TDD seams and vertical slices

The approved public test seams are:

1. The pure Activity view-model interface.
2. Agent transcript/component behavior observed through the DOM and user input.
3. Backend public Snapshot/Event/history projection observed through serialized
   contracts and existing HTTP behavior tests.

Tests must not mock private helpers, assert implementation call order, or treat
CSS snapshots as the only proof of behavior.

### Slice 1: ordered activity and duplicate removal

Red tests:

- assistant parts retain `response -> thinking -> response` order;
- A1, B, A2 tool groups do not become A1, A2, B;
- a durable tool call with matching live progress renders once at the durable
  timeline position with its live status;
- unmatched live tool progress remains visible;
- the DOM order for Thinking, tool, response fixtures matches the view model.

Green implementation:

- add the Activity view model;
- route historical message parts and ActiveRun through it;
- eliminate type-by-type filtering and global group-ID regrouping.

### Slice 2: safe tool projection and disclosure

Red tests:

- a sentinel secret is absent from serialized Snapshot, `tool.updated`, and
  historical entries;
- Bash credentials and secret flags are redacted;
- read/write/edit content never enters public details;
- unknown tools expose empty details;
- safe artifact/file/run references remain available;
- collapsed tool DOM contains no public command text;
- clicking anywhere on the row, Enter, and Space reveal public details;
- status updates preserve the user's disclosure choice;
- no-detail tools show no arrow.

Green implementation:

- add backend public detail contracts and tool-specific projection;
- sanitize all public projection paths;
- render only structured public details in the flat tool row/group UI.

### Slice 3: Thinking and plan activity

Red tests:

- active empty Thinking shows a compact live state, not an empty panel;
- published summary and displayable full reasoning can be expanded;
- historical Thinking defaults collapsed;
- streaming text updates do not reset disclosure;
- the latest plan revision updates in place and shows progress without an
  internal revision label.

Green implementation:

- add a dedicated Thinking row;
- normalize plan selection and checklist rendering in the activity layer.

### Slice 4: Composer and control restoration

Red tests:

- a Draft conversation presents one centered Composer;
- after the first message, the same controls appear in bottom-docked placement;
- supported model selection reaches session creation / turn input;
- permission, context, voice, send, steer, and stop remain available according
  to state;
- a failed send keeps user text;
- narrow layouts retain direct access to critical actions.

Green implementation:

- simplify AgentWorkbench's Draft/header composition;
- refine AgentComposer variants and wire real model capability;
- avoid fake Plan/Act controls.

### Slice 5: workspace, artifacts, responsive, and theme

Red tests:

- desktop users can open LiveDeck without a shortcut;
- progress and artifact actions open the correct tab;
- mobile Sheet retains accessible title/description and focus restoration;
- critical touch targets meet `44px` minimum sizing;
- semantic Agent styling introduces no hardcoded light/dark colors;
- reduced motion disables non-essential transition effects.

Green implementation:

- add the visible workspace trigger and tab-targeted open callback;
- refine responsive layout, safe areas, overflow, and dark semantic surfaces;
- add `color-scheme` support if the existing application theme layer lacks it.

## File map

Expected additions:

- `frontend/lib/agent/activity.ts`
- `frontend/tests/unit/lib/agent/activity.test.ts`
- `frontend/components/bioinfoflow/agent/agent-thinking.tsx`
- focused backend projection tests as required by the existing suite layout

Expected edits:

- `backend/app/services/agent_harness/contracts.py`
- `backend/app/services/agent_harness/tool_projection.py`
- `backend/app/services/agent_harness/projection.py`
- relevant Agent Harness API/projection tests
- `frontend/lib/agent/contracts.ts`
- `frontend/components/bioinfoflow/agent/active-run.tsx`
- `frontend/components/bioinfoflow/agent/conversation-entries.tsx`
- `frontend/components/bioinfoflow/agent/message-parts.tsx`
- `frontend/components/bioinfoflow/agent/agent-activity.tsx`
- `frontend/components/bioinfoflow/agent/agent-transcript.tsx`
- `frontend/components/bioinfoflow/agent/agent-plan-entry.tsx`
- `frontend/components/bioinfoflow/agent/agent-composer.tsx`
- `frontend/components/bioinfoflow/agent/agent-workbench.tsx`
- `frontend/app/(app)/agent/page.tsx`
- `frontend/components/bioinfoflow/live-deck.tsx`
- Agent integration/unit tests and both locale JSON files
- `frontend/app/globals.css` only if a missing semantic theme primitive cannot
  be expressed with existing tokens

The exact file set may shrink as tests reveal the smallest implementation.

## Commit plan

Each batch must be green before the next begins:

1. `docs: plan agent conversation UI refinement`
2. `fix: preserve agent activity order`
3. `fix: publish safe agent tool details`
4. `feat: refine agent thinking and tool activity`
5. `feat: restore the agent composer and controls`
6. `feat: restore agent workspace discoverability`
7. `fix: polish agent themes and responsive behavior`
8. Review-fix commits with specific Conventional Commit messages if needed

Do not squash locally; the PR will be rebase-merged so the reviewable batches
remain visible on `main`.

## Verification

### During each TDD slice

- run the smallest relevant frontend Vitest file or backend Pytest test;
- observe the intended failure before implementing;
- implement only enough behavior for the current slice;
- rerun the focused test before proceeding.

### Before each commit

- inspect `rtk git diff --check`;
- run the focused tests for all files in the batch;
- inspect `rtk git status --short` and avoid unrelated files.

### Final automated gates

From `frontend/`:

```bash
rtk bun run lint
rtk bun run lint:i18n
rtk bun run lint:dead-code
rtk bun run test
rtk bun run build
```

From `backend/`:

```bash
rtk uv run ruff check .
rtk uv run pytest
```

### Final visual gates

Run the application with `AUTH_MODE=dev`, then inspect at minimum:

- Draft, active, waiting approval, failed, cancelled, and historical sessions;
- Light and Dark at desktop, tablet, and mobile widths;
- long Thinking, long command/output, long path/model/tool names;
- keyboard-only disclosure, Composer, workspace Sheet, and panel navigation;
- scroll anchoring while streaming and when the Composer grows;
- screenshots comparable to the supplied pre-refactor and current-regression
  references.

## Independent review and delivery

1. Fetch the current Web Interface Guidelines and audit every changed Agent UI
   file with terse file/line findings.
2. Run the code-review skill from fixed point `origin/main` with independent
   Standards and Spec subagents. The spec source is this plan.
3. Run an additional visual/interaction review against the screenshots and the
   responsive/accessibility matrix.
4. Fix every Critical/Important issue and rerun affected verification.
5. Fetch `origin/main --prune`, rebase the branch, resolve and reverify any
   changed surface.
6. Push `codex/refine-agent-conversation-ui` and create a Conventional Commit
   PR.
7. Wait for required CI checks. Fix failures in focused commits.
8. Rebase-merge the PR; do not force-push `main`.
9. Confirm the merged commit exists on `origin/main` and report the PR, commits,
   verification, visual evidence, and any intentionally deferred work.

## Acceptance checklist

- [ ] Activity order is stable and no live tool appears twice.
- [ ] Thinking is compact, expandable, stream-stable, and displays only
      Harness-published content.
- [ ] Tool rows hide commands/details until expansion and receive only safe
      public details from the backend.
- [ ] Tool groups are flat and whole-row operable by pointer and keyboard.
- [ ] Plans update in place without a fake Plan Mode.
- [ ] Draft Composer is centered; conversation Composer is docked and complete.
- [ ] Stop, steer, approve, model, permission, context, voice, and send controls
      are visible when supported and relevant.
- [ ] Workspace, progress, and artifact entry points are discoverable.
- [ ] Light/Dark, responsive, reduced-motion, focus, and screen-reader behavior
      pass the stated matrix.
- [ ] Frontend and backend full gates pass.
- [ ] Independent Standards, Spec, guideline, and visual reviews pass.
- [ ] Branch is rebased on current `origin/main`, PR CI passes, and the PR is
      rebase-merged.
