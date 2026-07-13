# Permission Policy Refactor Design

## Status

Accepted and implemented. Full backend/frontend verification, contract checks,
parallel final review, finding remediation, and the required `origin/main`
rebase have completed. Publication is the remaining release step.

## Problem

Bioinfoflow persists permission-mode changes, but an active agent loop keeps an
old SQLAlchemy session object and evaluates later tool calls with stale policy.
Because the ORM uses `expire_on_commit=False`, merely calling the repository
`get()` method again is not sufficient: the identity map can still return the
old row.

The visible symptom is amplified by three related design gaps:

- a model response containing several approval-gated tool calls creates several
  pending actions and can resume the model before every tool call has a result;
- approval decisions and action claims are not conditional state transitions,
  so concurrent requests or workers can enqueue or execute a side effect twice;
- local shell commands receive command-aware risk assessment and may run inside
  an OS sandbox, while `remote.exec` marks every command `act_high` and executes
  through SSH without a comparable confinement boundary.

The permission selector also presents a successful database update as if it
retroactively affected pending actions, has no local busy/error state, and calls
the bypass mode “Full access” without explaining the remaining hard blocks or
the weaker remote boundary.

## Goals

1. A permission update committed before a new action evaluation is immediately
   visible to that evaluation, including during an active turn.
2. Every action records the exact policy and target context used to evaluate it.
3. Every assistant tool-call batch obeys a barrier: each tool call gets exactly
   one terminal tool result before the model can continue.
4. Approval and execution transitions are idempotent across requests, workers,
   restarts, and duplicate queue delivery.
5. Local and remote commands use one command-risk vocabulary with target-aware
   adjustments and a small high-confidence catastrophic hard-deny floor.
6. The UI makes future-only versus pending-action effects explicit and provides
   reliable loading, error, accessibility, and target-boundary feedback.
7. Existing interaction tools such as user questions and plan approval remain
   explicitly interactive in every permission mode.

## Non-goals

- Building an OS-level sandbox on an arbitrary SSH host.
- Treating a remote working directory as a security boundary.
- Automatically approving user-input or plan-approval interactions.
- Adding permanent user-authored command rule management in this PR.
- Replacing SSH account, sudo, ACL, scheduler, or cluster-side security policy.

## Chosen Approach

Use a versioned, freshly resolved permission context at every authorization
boundary; persist tool-call batches as the continuation unit; use database
compare-and-set transitions for decisions and execution; and share command
semantics between local and remote tools through a target-aware assessor.

This is preferred over two narrower alternatives:

1. **Refresh only `permission_mode` in the loop.** This fixes the screenshot but
   leaves mixed old/new toolset and target fields, unmatched provider tool calls,
   duplicate execution, and misleading remote risk.
2. **Restart the turn whenever permissions change.** This avoids some stale
   state but discards model work, makes approvals brittle, and still does not
   provide durable batch recovery or correct remote policy.

## Permission Context

Add a focused `PermissionContextResolver` that performs a forced fresh read with
`populate_existing` or an equivalent explicit refresh. It resolves one immutable
snapshot containing:

- session id and monotonic `permission_policy_version`;
- permission and automation modes;
- toolset policy and role;
- execution target, selected connection, host identity, and effective roots;
- target boundary metadata such as `sandboxed`, `unsandboxed`, or `remote_ssh`.

Every field that can change authorization behavior—permission mode, automation
mode, toolset, role, or execution target—must increment the version in the same
transaction. The executor resolves this snapshot immediately before exposure
and risk evaluation so those decisions cannot mix fields from different policy
versions.

Each action stores `evaluated_policy_version` and a bounded policy snapshot. The
risk and decision events include that version. `updated_at` is not used as a
policy version because it is unsuitable for comparison and audit semantics.

The linearization rule is:

> After a policy update commits, every authorization evaluation that begins
> afterward uses the new policy. Running and terminal actions are unchanged.

Pending actions are not silently approved by a general mode change.

## Tool-call Batch Barrier

Persist each assistant tool-call response as a batch. Actions receive a
`tool_batch_id` and stable ordinal. The batch tracks whether it is evaluating,
waiting, ready to continue, continuing, or terminal.

Rules:

- every tool call produces exactly one completed, failed, rejected, or cancelled
  tool result;
- independent read-only calls may execute concurrently;
- approval-gated calls may wait independently, but resolving one action does not
  call the model while another action in the batch is unresolved;
- exactly one database-claimed continuation calls the model after the whole
  batch becomes terminal;
- interaction tools are exclusive barriers; if a provider emits an interaction
  alongside other calls, the remaining calls are deferred or cancelled with
  explicit results rather than executed behind the user's back;
- provider messages are never assembled with unmatched tool-call ids.

The database batch is the correctness source. In-process runner dictionaries are
only wake-up optimizations and may be lost on restart.

## Idempotent State Transitions and Recovery

Repositories provide conditional transitions such as:

```text
WAITING_DECISION -> REQUESTED or REJECTED
REQUESTED -> RUNNING
batch READY -> CONTINUING
```

Each transition is an atomic `UPDATE ... WHERE status = expected RETURNING ...`.
Duplicate identical decisions return the current result or a documented
conflict; they never enqueue twice. Only the worker that claims
`REQUESTED -> RUNNING` executes the tool.

Recovery works batch-first:

- any running action after lease loss requires failure/manual reconciliation;
- otherwise any waiting action leaves the batch waiting;
- otherwise requested actions are claimable;
- when all actions are terminal, one continuation is claimable.

The queue remains at-least-once. Database claims make effects and continuation
effectively once-only within the supported failure model.

## Pending-action Update Semantics

The session update API gains an explicit pending strategy:

- `future_only` is the default and updates policy for actions evaluated later;
- `approve_pending_tools` updates policy and approves eligible waiting tool
  actions in one service transaction.

The second strategy excludes user-input and plan-approval interactions. The
response includes the new policy version and counts of affected, excluded, and
already-resolved actions. Events record both the policy change and pending
reconciliation.

Tightening policy affects later evaluations immediately. Already running tools
are not represented as cancelled. Before a requested action becomes running, it
is rechecked against current hard blocks and protected-resource policy to avoid
executing an action whose safety floor changed while it waited.

## Command Risk Model

Introduce a target-aware command assessor instead of calling the existing shell
classifier directly from `remote.exec`.

The assessor accepts command semantics plus a target profile:

```text
command
target kind: local | remote_ssh | container
trust domain and identity
sandbox strength: enforced | declared | none
read/write roots
network and privilege metadata
connection id when remote
```

It returns the existing risk level for compatibility plus structured effect,
confidence, reasons, referenced paths, protected resources, target metadata,
and whether a boundary is actually enforced.

Shared command semantics cover reads, writes, deletion, network access,
privilege escalation, process control, redirects, pipelines, and wrappers.
Target adaptation then changes the result:

- local sandboxed reads inside allowed roots can remain read/low risk;
- local unsandboxed actions receive an explicit unconfined reason;
- SSH commands are constrained only by the remote Unix identity and server
  controls, not by `cd` to a remote root;
- remote root-relative structured tools remain preferred for file reads;
- unknown, variable, absolute-outside-root, or symlink-sensitive remote paths
  require approval rather than being treated as proven safe.

The catastrophic hard block remains deliberately small: high-confidence matches
for root/protected-system recursive destruction, block-device overwrite or
format, direct host shutdown/reboot, and fork-bomb equivalents are hard denied.
Detection must understand command positions, common wrappers, quoted root forms,
command separators, and shell wrappers without flagging data strings such as
`echo reboot`. Statically uncertain forms require approval; this classifier is
defense in depth, not an operating-system boundary.

Sensitive policy, credential, SSH, sudoers, and shell-startup writes are
protected resources. They force an explicit decision even when ordinary
approvals are bypassed. The agent must not be able to change its own policy file
and immediately escape the gate.

## Local and Remote Product Semantics

Permission mode controls approval behavior, not operating-system authority.

- **Local:** the UI reports the workspace or full-device sandbox boundary that
  is actually active.
- **Remote SSH:** the UI reports the selected host/account and states that the
  command executes with that account's remote privileges. A remote working root
  is a navigation default and policy signal, not confinement.

The same permission-mode enum is retained. Target differences are conveyed by
the resolved boundary, risk reasons, audit records, and contextual UI copy.

## UI Design

The permission control becomes an explicit asynchronous transaction:

- while changing, the trigger is busy, menu actions are disabled, and duplicate
  writes are prevented;
- success announces that the mode applies to later evaluations;
- failure restores the prior draft, local storage, and session value and shows
  a retryable control-local error;
- menu choices use radio semantics, expose the selected item, and announce
  changes through an accessible live region.

With no pending tool approvals, selection updates directly. When widening
permissions with pending tool approvals, a focused confirmation asks:

1. **Only update future operations** (default), or
2. **Update and approve the current waiting tool operations**, showing the exact
   count and exclusions.

Approval cards disable both actions while submitting, retain errors on the card,
and allow retry without duplicate decisions. Remote cards display the target
host separately from risk. Permission descriptions state that critical actions
remain blocked and, for SSH, that the remote account and server policy remain
the true authority boundary.

All new copy is present in English and Simplified Chinese.

## API and Persistence Changes

Expected schema additions:

- `agent_sessions.permission_policy_version`;
- durable tool-call batch table or equivalent normalized batch model;
- `agent_actions.tool_batch_id` and `tool_call_ordinal`;
- `agent_actions.evaluated_policy_version` and bounded policy snapshot;
- conditional repository methods for action and batch transitions.

The session PATCH schema gains `pending_strategy`. Its response remains the
updated session plus policy/reconciliation metadata in a backward-compatible
response envelope. Action and event read models expose the audit fields needed
by the UI and diagnostics without exposing secrets.

## Delivery Phases

Each phase must pass its scoped verification before its Conventional Commit.

### Phase 1: Fresh, versioned policy evaluation

- migration and models for policy version/action policy audit;
- forced-fresh permission context resolver;
- executor integration and hot-update regression tests;
- no retroactive pending approval.

Commit: `fix: apply permission updates to active turns`

### Phase 2: Durable tool-call batch barrier

- persisted batch and action ordinals;
- barrier coordinator and provider transcript invariants;
- interaction exclusivity and restart-safe continuation.

Commit: `refactor: persist agent tool call barriers`

### Phase 3: Idempotent decisions, claims, and recovery

- database conditional transitions;
- batch-aware recovery and duplicate-delivery tests;
- explicit pending strategy service/API.

Commit: `fix: make agent approvals idempotent`

### Phase 4: Target-aware command risk

- shared command assessor and target profiles;
- dynamic `remote.exec` evaluation, hardline coverage, protected resources;
- local/remote audit and behavior matrix.

Commit: `refactor: unify command risk evaluation`

### Phase 5: Permission and approval UX

- transactional selector state and pending-strategy confirmation;
- card busy/error/target details;
- English/Chinese copy, accessibility, unit/integration tests;
- visual verification in `AUTH_MODE=dev` when services are available.

Commit: `feat: clarify agent permission controls`

### Phase 6: Documentation and final verification

- architecture/security/user documentation updates;
- backend and frontend verification matrices;
- review fixes are committed separately by concern when material.

Commit: `docs: document agent permission boundaries`

## Testing Strategy

Backend tests cover:

- two independent database sessions proving guarded-to-bypass and
  bypass-to-guarded changes affect the next action;
- a single coherent policy snapshot when target/toolset/role change;
- pending future-only behavior and interaction invariants;
- multi-call batches with read, approval, rejection, and failure combinations;
- exactly one continuation after concurrent decisions;
- duplicate approve and duplicate worker-claim races;
- restart and recovery states;
- target-by-mode command-risk matrices, hardline bypass spellings, protected
  paths, and audit persistence.

Frontend tests cover:

- successful, failed, overlapping, and stale-session permission updates;
- local rollback of draft and storage on failure;
- radio/busy/error accessibility behavior;
- pending strategy selection and exclusion of interaction actions;
- independent approval-card submission states;
- local and remote contextual copy and targets;
- English/Chinese locale parity.

Verification follows `AGENTS.md`: backend pytest and Ruff; frontend lint, tests,
i18n lint, and dead-code lint when refactoring exports. Database migrations are
applied in tests. Visual verification covers desktop and narrow layouts with
local/remote targets and zero, one, and several pending actions.

## Rollout and Compatibility

Existing sessions receive policy version `1`. Existing actions without batch
metadata remain readable and are handled by a compatibility recovery path until
they terminate. New turns always use batches. API clients that omit
`pending_strategy` receive `future_only` behavior.

Metrics and logs distinguish policy version, target kind, batch id, duplicate
decision/claim prevention, waiting duration, and continuation recovery. No raw
commands, credentials, or remote secrets are added to new logs beyond the
existing bounded/redacted action records.

## Security Boundary Statement

“Full access” means Bioinfoflow does not request ordinary risk approvals for the
selected target. High-confidence catastrophic matches remain hard denied, and
protected or indirect operations can still require explicit approval. It does
not grant new workspace/admin or SSH privileges and does not disable a configured
operating-system sandbox. Local OS enforcement or the remote account and server
policy is the true security boundary. The UI and documentation must use this
definition consistently.
