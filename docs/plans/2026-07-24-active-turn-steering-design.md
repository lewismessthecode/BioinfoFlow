# Active-turn steering design

## Problem

Bioinfoflow currently treats every message submitted during an active response as
either a hard interrupt or a future turn. In interrupt mode the client cancels the
active turn, marks it interrupted, and creates a replacement turn. This makes a
small correction feel like two disconnected conversations and can cancel useful
tool work that the user intended to keep.

The custom-instructions form also uses more explanatory copy and visual nesting
than the setting requires.

## Goals

- Let a user add guidance to the currently running turn without cancelling it.
- Preserve completed work and let an in-flight model call or tool batch reach a
  safe boundary before the guidance is delivered.
- Show the submitted guidance immediately in the transcript and preserve it
  across refreshes.
- Keep queueing as an explicit alternative and keep the stop control as the only
  hard-cancel action.
- Flatten and shorten the custom-instructions setting.

## Non-goals

- Do not implement Hermes' separate immediate redirect mode.
- Do not interrupt an individual tool process to deliver ordinary guidance.
- Do not merge multiple user messages into one synthetic prompt.
- Do not change approval-card answer semantics.

## Interaction model

The active-response setting has two choices:

1. **Guide current response** (default): submit the message to the active turn.
   It appears immediately with a pending delivery label. The agent receives it
   after the current model call or complete tool batch, then continues the same
   turn.
2. **Queue as next message**: keep the current response running and create a new
   turn after it completes.

The composer remains usable while a turn runs. Enter submits according to the
selected policy. The square stop button remains available as a separate control
and always performs a hard cancellation.

If a steer request races with turn completion, the server rejects it once the
turn has sealed itself against new guidance. The client retains the optimistic
message and sends it as a normal turn after the active turn becomes idle. This
avoids loss and duplicate delivery.

## Backend architecture

### Persisted pending messages

Steering inputs reuse `agent_messages` with:

- `role="user"`
- `status="draft"` while waiting for a safe boundary
- `ordering_index=0` until delivery
- metadata containing `kind="steer"`, a stable `steer_id`, display metadata,
  and delivery state

Draft messages are excluded from model context by the existing committed-message
filter. At a safe boundary the loop promotes pending messages in creation order,
assigns normal transcript ordering indexes, marks them committed, and emits a
delivery event.

### Turn sealing

`agent_turns.accepts_steer` is true while a turn can accept guidance. Before the
loop returns a final answer it atomically seals the turn only when no draft steer
messages remain. A steer insert and turn sealing therefore serialize on the turn
row:

- insert wins: the loop observes and delivers the message, then continues;
- seal wins: the API rejects steering and the client falls back to a new turn.

Terminal, cancelled, and failed turns always set `accepts_steer=false`.

### Safe boundaries

The loop drains pending steering inputs:

- after an assistant response and all tool results for that response have been
  committed;
- after a text-only assistant response has been committed, before deciding
  whether the turn is complete;
- after a resumed approval batch finishes, before the next model invocation.

It never inserts a user message between an assistant tool-call message and its
tool results.

### Events

The ledger adds:

- `turn.steer.received`
- `turn.steer.delivered`
- `turn.steer.cancelled`

Each event carries `steer_id`, text/input-display data, and delivery state. The
received event is the durable UI acknowledgement. Delivered and cancelled events
update that same transcript item.

## Frontend architecture

The runtime client adds `steerAgentRuntimeTurn`. The workbench replaces the
interrupt-then-send branch with an optimistic steer submission. Queue behavior
is unchanged.

Timeline construction adds a `user_steer` segment keyed by `steer_id`. The
segment is sorted with assistant text and tool activity by ledger sequence, so a
correction appears where it entered the conversation. Pending steer messages show
"Will be considered after the current step"; delivered messages become normal
user bubbles; cancelled messages show that they were not processed.

The composer keeps both send and stop affordances during a run: sending submits
the draft, while stop remains a distinct square button.

## Custom-instructions layout

The form becomes one flat settings row rather than a standalone nested card.
The copy becomes one sentence: "Add lasting context for new conversations."
The new-session limitation moves to compact helper text beside the character
count. The textarea remains the only bordered input surface.

## Error handling

- Empty and oversized steer requests use the same validation limits as turns.
- A non-active or sealed turn returns a conflict response that the client treats
  as a normal-turn fallback, not a user-visible failure.
- Other API failures restore the draft to the composer and show the existing
  send-failure feedback.
- Hard cancellation marks undelivered steering messages superseded and emits
  `turn.steer.cancelled`.

## Testing

- Repository/service tests cover active-only insertion, FIFO promotion, sealing
  races, and cancellation.
- Runtime integration tests prove that a steer arriving during a tool call is
  absent from that tool batch, present in the next model request, and does not
  cancel the turn.
- Frontend tests cover same-turn optimistic display, API steering, race fallback,
  queue preservation, stop semantics, event-to-segment projection, and the flat
  custom-instructions layout in both locales.

## Benchmarks considered

- Codex: same-turn `turn/steer` with pending input and an expected active-turn id.
- Pi: explicit steer versus follow-up queues, drained at tool/turn boundaries.
- OpenCode: steer is the default follow-up behavior and the loop reads the latest
  user input at the next step.
- Hermes: distinguishes safe-boundary steer, active-turn redirect, queue, and
  hard stop.
- Goose: emphasizes immediate acknowledgement for messages that must wait.

