# Plan Mode Design

## Goal

Make Plan and Act feel like one reliable mode switch: the selected mode applies
to the next new turn, Plan can use every operation that is deterministically
read-only, and approving a plan switches to Act and resumes the same turn
automatically. The UI should not expose synchronization states or require a
second message.

## First-principles constraints

- A mode determines capabilities for a model turn. It is not an independent
  workflow engine and does not need its own persistence model.
- The model-visible tool list and the executor's authorization decision must be
  derived from the same policy semantics.
- Plan permits investigation, not implementation. Operations that cannot be
  proven read-only are unavailable.
- Mode selection must be atomic with turn creation. A separate mode update
  request creates an avoidable race.
- Plan approval is the only mode transition allowed during an active turn.
- Existing session policy versions, actions, tool-call batches, events, and
  resume workers remain the durability and recovery mechanisms.
- The shared prompt prefix should remain stable. Mode-specific text and tools
  should be the smallest possible suffix.

## Reference lessons

- Codex models Plan as an explicit per-turn collaboration mode, keeps its base
  prompt stable, allows non-mutating investigation, separates clarification
  from checklist tracking, and renders the completed plan as structured output.
- pi's Plan extension disables write tools, preserves existing read tools,
  checks shell commands, restores the previous tool set on approval, and
  triggers the next agent iteration automatically.
- goose routes approvals by tool-request identity and treats approved,
  approval-required, and denied calls as distinct outcomes, avoiding ambiguous
  resume behavior.
- Hermes derives tool exposure from a central registry and avoids transient
  availability changes that make a previously advertised tool disappear.

BioinfoFlow should combine these invariants without copying their extra UI,
extension machinery, text-marker protocols, or auxiliary permission models.

## User experience

The composer continues to show only two choices: Plan and Act.

- Selecting a mode updates the chip immediately and performs no network request.
- Sending a new message includes the selected mode in the turn-creation request.
- The frontend keeps only `pendingMode: AgentMode | null`; the chip displays
  `pendingMode ?? session.mode`. A refresh clears the pending value only after
  the server reports the same mode, while switching sessions always clears it.
- While a turn is active, only the mode chip and its keyboard shortcut are
  disabled. Steering and queueing remain available. No pending-mode spinner,
  toast, confirmation dialog, or queued-mode indicator is added.
- Every immediate or queued submission captures the selected mode when the user
  submits it. A queued message cannot silently change mode because an earlier
  plan was approved before that message starts.
- A completed plan appears in the existing plan approval card.
- **Approve and act** atomically switches the session to Act and automatically
  resumes the same turn.
- **Keep planning** leaves the session in Plan and automatically resumes the
  same turn with the decision available to the model.
- After approval or session selection, the chip follows the authoritative
  session mode returned by the backend.

## Turn and mode contract

`AgentTurnCreate` gains an optional `mode: "plan" | "execution"` field.
Existing clients that omit it retain the session's current mode.

When `mode` is present, `create_turn_record()` adds the corresponding
`toolset_policy` to the existing `session_updates` passed to
`create_with_session_claim()`. The session policy update and turn claim therefore
commit together. The permission policy version changes only when the normalized
policy actually changes. The existing active-turn claim rejects concurrent
turn creation.

The composer no longer calls the session-mode PATCH endpoint. That endpoint is
retained for compatibility and administration, but a mode update is rejected
while the session has an active turn. This preserves the invariant for every
client, not only the web UI.

After a turn is created and the authoritative session reports the submitted
mode, the frontend clears `pendingMode`. A stale refresh cannot overwrite an
unsent local selection. A newly created session defaults to Act, matching the
existing backend default.

No mode column is added to the turn. The session policy is stable for the life
of a normal turn, and the existing permission policy version records relevant
changes. The one legal mid-turn transition is the existing `exit_plan_mode`
approval transaction, which updates the session before queuing resume.

## Tool exposure and execution

Plan exposure is derived rather than maintained as a second small product
allowlist:

1. Include every registered, model-visible tool whose specification is read
   risk and has no write scope.
2. Include `ask_user` and `exit_plan_mode` for the root orchestrator.
3. Include command-capable inspection tools such as local `bash` and remote
   execution in the model surface only when the selected target supports them.
4. At execution time, allow those command-capable tools only when the existing
   deterministic command-risk analysis proves the concrete command read-only
   or low-risk with read-only effects. Redirects, mutations, hard-blocked
   commands, commands requiring approval, and unknown effects are denied
   directly; approval cannot bypass the Plan ceiling.
5. Exclude edit, write, workflow mutation, run submission, persistent todo
   mutation, and every operation whose effect is unknown.

Act keeps the existing execution capability surface and permission behavior.
Plan does not weaken approval policy; it adds a stricter no-side-effect ceiling.

Static Plan tools use one canonical policy helper for both model-visible and
host-callable surfaces. Dynamic command tools add the concrete-command guard
above. A newly received model tool call is checked against the model-visible
surface and current permission context exactly once before its action is
persisted.

Resuming an already persisted action checks its identity, current host-callable
surface, command risk, target, and permissions, but does not require that the
tool still be model-visible in the session's new mode. This is required for
`exit_plan_mode`: approval first switches the session to Act, then resumes the
persisted Plan action even though Act no longer advertises that tool. This uses
the existing action record rather than a tool snapshot.

If an independent authorization change invalidates an in-flight call, the call
becomes a normal structured tool failure that the model can recover from; it
must not terminate the whole turn with a generic registered-but-not-exposed
error.

## Prompt caching

- Keep the common system prompt and environment description unchanged between
  modes.
- Remove mode text from the middle of the environment block and append one
  short `Mode` section at the end of the assembled instructions.
- Build model tools in stable tiers: shared read-only tools first, interaction
  tools next, and Act-only tools last. Preserve deterministic order within each
  tier. The shared tool definitions must be byte-for-byte identical and have
  the same relative order in both modes.
- Do not duplicate the base prompt, inject the full plan repeatedly, or add a
  separate generated Plan system prompt.

This cannot make Plan and Act requests byte-identical because their tool
surfaces intentionally differ, but it maximizes their shared cacheable prefix
without compromising the capability boundary.

## Error and recovery behavior

- Concurrent new turns continue to return the existing conflict response.
- Ordinary mode PATCH requests during an active turn return a conflict response.
- Duplicate plan approvals remain idempotent through the existing action
  compare-and-set and policy-version transaction.
- A rejected plan leaves the policy unchanged and resumes the waiting turn.
- Resume workers always resolve a fresh permission context. After approval they
  therefore advertise Act tools; after rejection they continue to advertise
  Plan tools.
- A stale or denied tool call is persisted as a failed tool result and supplied
  to the model so the batch barrier can complete normally.

## TDD and acceptance tests

Backend tests will be written first for:

- turn creation applying `mode` and claiming the turn in one transaction;
- omitted mode preserving backward compatibility;
- ordinary mode updates being rejected during an active turn;
- Plan exposing all deterministic read tools while hiding mutation tools;
- Plan allowing read-only shell commands and denying mutating or unknown ones;
- target-aware remote read-only command behavior;
- a full runtime loop in which approving `exit_plan_mode` switches to Act,
  resumes the persisted action, and invokes the model again with Act tools;
- rejecting the plan preserving Plan before automatic resume;
- duplicate decisions remaining idempotent;
- exposure denial producing a recoverable tool result rather than a stopped
  turn.

Frontend tests will be written first for:

- selecting Plan or Act performing no mode PATCH;
- the selected mode being included in new-turn creation;
- the mode chip changing immediately without a loading state;
- a stale session refresh not overwriting an unsent local mode selection;
- clearing the pending selection after server confirmation or session switch;
- the chip and its keyboard shortcut being disabled during an active turn while
  steering and queueing remain available;
- queued submissions retaining the mode captured when they were submitted;
- session selection and plan approval refreshing the authoritative mode;
- no regression in steering, permission controls, or new-session creation.

Prompt construction tests will verify:

- the shared prompt prefix is unchanged across modes;
- only the short mode suffix differs;
- shared read tools retain identical definitions and relative order;
- Act-only tools follow the shared tools.

Required verification after implementation:

```bash
rtk uv run pytest
rtk uv run ruff check .
rtk bun run lint
rtk bun run lint:i18n
rtk bun run test
rtk git diff --check
```

## Out of scope

- Redesigning the composer or approval card.
- Adding a plan table, plan version history, plan editor, or separate plan API.
- Parsing numbered plan text into a second todo system.
- Replacing the existing permission classifier or action/batch resume model.
- Building provider-specific prompt-cache infrastructure.
