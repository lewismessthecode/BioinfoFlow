# Provider-neutral plan round and panel

## Problem

BioinfoFlow currently removes `update_plan` from the Tool Round returned by the
model and replays it as a synthetic assistant/tool exchange. That changes the
model's response boundary and drops provider continuation fields such as
DeepSeek's `reasoning_content`. DeepSeek thinking models reject the next request.

The frontend also projects durable plan entries into Transcript Blocks, so the
plan consumes conversation space and its spinner follows stale item state rather
than the authoritative Run lifecycle.

## Invariants

1. One model response produces one immutable assistant Tool Round. Harness
   control behavior must not split, reorder, or synthesize assistant rounds.
2. Provider-specific continuation fields are owned by the Model Runtime adapter.
   Harness and Presentation Contract types remain provider-neutral.
3. A durable plan is product state, not transcript content. The Conversation
   projection exposes one latest `currentPlan` ViewModel.
4. A Plan can animate only while its owning Run is active. A successfully
   completed Run presents every plan item as completed; failed or cancelled Runs
   preserve item facts but never display an active spinner.

## Seams

### Model Runtime seam

The Harness history interface carries a provider-neutral reasoning part beside
assistant text and tool calls. The Chat Completions adapter groups those parts
into one assistant message and maps the reasoning source to the provider wire
field. Responses API continuation remains opaque inside its existing adapter.

`update_plan` executes in the same batch as the other calls from the response.
Its successful result commits a durable plan entry, while its ordinary tool
result remains adjacent to the other results in canonical history.

### Presentation seam

The transport contract continues to accept durable plan entries. The
Conversation projection selects the latest revision and returns it as
`ConversationViewModel.currentPlan`; it does not emit a plan Transcript Block.
React components consume only that stable ViewModel.

## UI

The conversation surface follows the compact Codex plan pattern. A small
progress trigger sits immediately above the docked composer and opens an upward
popover containing the full plan. It is outside the transcript, consumes no
persistent horizontal space, and does not compete with the existing LiveDeck
sidebar. The card is intentionally quiet: no extra controls, no provider
details, and no duplicate activity for the `update_plan` tool.

## Regression seams

- A response containing `update_plan`, `bash`, and `list_environments` reaches
  the next Model Runtime invocation as one assistant Tool Round with three
  adjacent results.
- A reasoning-bearing Chat Completions assistant round encodes its reasoning in
  the adapter-owned wire field.
- The Conversation projection removes plan entries from transcript and exposes
  the latest revision as `currentPlan`.
- A terminal Run cannot leave the plan card spinning; a completed Run displays
  a fully completed plan.
