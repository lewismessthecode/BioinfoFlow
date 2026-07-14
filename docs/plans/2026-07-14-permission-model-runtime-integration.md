# Permission and Model Runtime Integration Plan

## Status

Completed and validated after integrating PR #125's runtime architecture into
PR #126's permission and durable tool-batch behavior.

## Goal

Integrate PR #126's versioned permission policy and durable tool-call batch
semantics into PR #125's provider-neutral model runtime and durable turn
ownership architecture without changing the user-visible permission contract.

## Canonical Architecture

- Keep PR #125's `ModelGateway`, Chat Completions/Responses codecs,
  continuation handling, `TurnOwnership`, `owner_token`, `resume_batch_token`,
  and owner-conditioned publication APIs.
- Do not restore the deleted legacy stream adapter.
- Do not retain PR #126's parallel `lease_owner_token`, heartbeat, or execution
  owner APIs.
- Keep PR #126's freshly resolved versioned permission context, target/resource
  revision checks, explicit durable tool-call batch table, atomic preparation,
  ordered barrier, action CAS, cancellation precedence, and single continuation
  claimant.
- Use transcript-derived tool-call batches only as a compatibility path for
  actions created before explicit batch rows existed.

## Migration Chain

The PR #126 migrations are rebased after PR #125's merged head:

```text
0044_llm_provider_wire_protocol
0045_agent_turn_owner_token
0046_agent_permission_policy
0047_agent_tool_call_batches
0048_agent_tool_batch_order
0049_agent_turn_tool_batch_sequence
```

No `lease_owner_token` migration or waiting-turn data rewrite is retained.
Existing `owner_token`, `resume_batch_token`, lease, and turn status values must
survive upgrades from `0045` to the new head.

## Integration Invariants

1. Every model iteration and tool execution resolves a fresh permission context.
2. One owner token is the sole authority for model, transcript, event, action,
   artifact, and batch publication.
3. Batch preparation locks session policy and turn ownership before publishing
   the assistant call group and action rows in one transaction.
4. Every tool call in an assistant group reaches a durable terminal result before
   one worker claims continuation.
5. Approval resume validates both the current unresolved explicit batch and PR
   #125's resume generation fence.
6. A stale worker cannot publish after ownership replacement; an unknown
   in-flight side effect remains a recovery/reconciliation case.
7. Responses continuation is discarded when repaired or normalized tool-call IDs
   no longer match the opaque provider continuation.

## Verification

- Preserve and run PR #125 model-runtime, Responses, transcript-context, and
  owned-publication fencing tests.
- Preserve and run PR #126 permission-context, approval idempotency, command-risk,
  durable batch, remote target, recovery, and UI tests.
- Test upgrade from `0045_agent_turn_owner_token` to head and downgrade back to
  `0045`, preserving PR #125 ownership state.
- Require one Alembic head, backend full tests/Ruff/contracts, frontend full
  tests/lint/i18n/dead-code/build, and final independent conflict review before
  pushing the merge commit.
