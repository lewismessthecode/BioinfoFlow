# Provider-Agnostic Minimal Agent Harness Design

## Goal

Strengthen Bioinfoflow's AgentCore so weaker function-calling models and
provider-specific coding models follow the same task boundary, make bounded
progress, pause safely for approval, and resume without losing control state.

The design follows the common core shared by Codex, Claude Code, and Hermes
Agent while applying Occam's razor:

```text
agent = canonical transcript
      + bounded observe -> act -> verify loop
      + scoped tools
      + side-effect gate
      + durable resume
```

This change is provider-agnostic. OpenAI-only capabilities such as native tool
search, Programmatic Tool Calling, Responses API compaction, and assistant
`phase` metadata remain provider-adapter concerns rather than core loop
semantics.

## Problem Statement

The current runtime has the right broad layers, but several boundaries are not
enforced consistently:

- The stable system prompt identifies every task as local Bioinfoflow platform
  work and embeds a large platform workflow manual. This conflicts with active
  external-system skills and remote execution targets.
- Dynamic context always advertises the local repository and Bioinfoflow
  inventory, including during remote-only work.
- A model response can emit several tool calls, continue executing after one
  call pauses for approval, and leave tool-call IDs without corresponding tool
  results.
- Iteration, token, and no-progress state live in one Python invocation and
  reset after approvals, recovery, or provider fallback.
- No-progress counting advances on matching calls even while results change.

These defects explain the observed Phoenix task failure: the model alternated
between remote Phoenix resources and local Bioinfoflow workflows, accumulated
many approval-gated commands, and reported apparent tool/result confusion.

## Design Principles

### 1. One Canonical Transcript

The durable AgentCore transcript remains the source of truth. Provider request
messages are derived views. Every assistant tool call must have exactly one
subsequent outcome before another model request:

- completed tool result;
- failed or rejected tool result;
- pending approval for the one active boundary; or
- explicit deferred result when a preceding call paused the batch.

Provider-specific metadata is preserved transparently when present, but does
not become a provider-neutral control primitive.

### 2. One Bounded Turn Loop

The loop remains a small observe -> act -> verify controller. It terminates for
a named reason: final answer, waiting approval, interrupted, no progress,
budget exhausted, model failure, or tool failure.

Iteration and token usage are cumulative properties of the durable turn. An
approval resume, rejection resume, recovery, or model fallback continues the
same budget instead of creating a fresh one.

### 3. One Approval Boundary

A tool-call batch may cross at most one approval or user-input boundary.

Execution proceeds in provider order. Independent, non-interactive reads may
run concurrently. When the first call requires resume:

1. The pending action is persisted.
2. Remaining calls in the model batch are not executed and create no actions.
3. Each remaining call receives a structured deferred tool result so the
   transcript stays valid.
4. The turn stops in `waiting_approval`.
5. Resume completes the pending action and continues the same turn state.

This avoids a new multi-action approval coordinator and keeps the invariant
easy to test.

### 4. One Current Execution Target

The current session execution target is authoritative for:

- project instruction resolution;
- dynamic environment context;
- tool schema exposure; and
- executor revalidation.

Remote targets omit local repository paths and local Bioinfoflow platform
inventory. Local targets retain them. A stale approved action is still checked
against the current target before execution.

### 5. A Small Stable Prompt

The stable system prompt becomes provider-neutral and contains only durable
operating behavior:

- follow the latest user request and supplied target context;
- inspect the minimum necessary evidence;
- use the smallest sufficient dedicated tool, with shell as an escape hatch;
- make reasonable assumptions unless authority or irreversible choice is
  missing;
- persist through implementation and verification;
- do not repeat failed or evidence-free work;
- treat approval as authorization, not proof of success;
- verify mutations before claiming completion; and
- preserve unrelated user changes.

Bioinfoflow platform instructions, project instructions, active skills,
permissions, target information, and tool schemas remain dynamic context.

Project instruction files are rendered as labeled task context rather than
being blended into the stable identity. Active skill bodies remain explicit
turn guidance. The implementation will reuse current message and context
structures and will not introduce a new instruction DSL.

### 6. Scoped Existing Tools

Registration, exposure, and execution remain separate. This change reuses
`ToolsetExposure` and the existing execution-target filter.

The implementation does not add native or emulated tool search in this phase.
The selected execution target supplies the primary capability pack:

- local target: local files, search, shell, and Bioinfoflow platform tools;
- remote SSH target: remote file, directory, and command tools plus neutral
  interaction, skill, plugin, and web tools;
- worker role: read-only, non-interactive subset.

Explicit `allowed_tools` remains the narrow override. Skills do not silently
grant capabilities outside the target boundary.

## Components And Data Flow

### Turn Start Or Resume

1. Load the session, turn, current target, and persisted budget snapshot.
2. Resolve exposed tools from mode, role, target, and explicit allow-list.
3. Assemble the stable prompt plus relevant dynamic context.
4. Derive the provider request from the canonical transcript.

### Model And Tool Cycle

1. Consume and checkpoint one iteration.
2. Call the selected provider.
3. Persist assistant text/tool calls and provider metadata.
4. Execute safe reads, or stop at the first approval boundary.
5. Persist a result for every emitted tool-call ID.
6. Update cumulative token usage and progress signatures.
7. Continue, wait, or terminate with a named reason.

### Approval Resume

1. Revalidate the stored action against the current target and exposure.
2. Execute or record rejection.
3. Append the matching tool result.
4. Reload the same turn budget and continue.

## Error And Progress Handling

- Malformed tool input remains a structured failed tool result.
- An obvious argument correction is allowed once through existing prompt
  guidance and the overall turn budget.
- Repeated progress counts only when both tool-call signatures and result
  signatures are unchanged.
- Changing polling results reset the repeat count.
- Varied but unproductive exploration is bounded by the cumulative iteration
  budget; no semantic-progress classifier is introduced.
- Large-result policy remains a separate concern unless tests show it blocks
  the target behavior.

## Implementation Phases

### Phase 1: Durable Loop And Atomic Approval

- Restore iteration and token state from the turn.
- Checkpoint budget and usage after each model iteration.
- Preserve the budget across approvals, rejection, recovery, and fallback.
- Exclude interaction tools from concurrent read batches.
- Stop at the first pending action and close later tool calls with deferred
  results.
- Make no-progress counting call-and-result aware.

Phase validation:

```bash
cd backend
rtk uv run pytest tests/test_agent_core/test_harness_invariants.py \
  tests/test_agent_core/test_runtime_reliability.py -q
rtk uv run ruff check app/services/agent_core/core \
  tests/test_agent_core/test_harness_invariants.py \
  tests/test_agent_core/test_runtime_reliability.py
```

### Phase 2: Neutral Prompt And Target-Coherent Context

- Replace the domain-locked stable prompt with the compact neutral prompt.
- Keep Bioinfoflow platform operating guidance in target-specific dynamic
  context.
- Make the current session target win over stale turn metadata.
- Omit local paths and platform inventory for remote targets.
- Remove duplicated exposed-tool prose when provider schemas already carry the
  authoritative definitions.
- Add a Phoenix-like remote task regression fixture that proves the prompt and
  tool surface do not redirect the model to local platform operations.

Phase validation:

```bash
cd backend
rtk uv run pytest tests/test_agent_remote_tools.py \
  tests/test_agent_core/test_context_compaction.py \
  tests/test_agent_core/test_harness_invariants.py \
  tests/test_agent_core/test_project_instructions.py -q
rtk uv run ruff check app/services/agent_core/context \
  app/services/agent_core/tools/toolsets.py \
  tests/test_agent_remote_tools.py \
  tests/test_agent_core
```

## Completion Criteria

- No model request is built with unresolved prior tool-call IDs.
- A turn cannot exceed its configured iteration budget through approval or
  fallback resumes.
- Token usage and iteration count are monotonic across the complete turn.
- Changing poll results do not trigger no-progress prematurely.
- Remote target context contains no local working directory or local platform
  inventory, and local/platform tools are not exposed.
- The stable prompt is provider-neutral and substantially smaller than the
  current Bioinfoflow playbook.
- Existing local Bioinfoflow workflows retain their target-appropriate tools
  and dynamic operating guidance.
- Backend focused tests, full backend tests, and Ruff pass.
- Independent review agents find no unresolved critical or important issues.
- The branch is rebased on current `origin/main`, pushed, and opened as a PR.

### Final Review Decision: One Session Claim Column

Cross-worker tests proved that existing turn snapshots cannot serialize two
tool-free turns before either emits a tool call. The minimum durable correction
is one nullable `agent_sessions.active_turn_id` column with conditional updates.
It is not a new orchestration layer: the session claim protects transcript
ordering, while the existing turn lease protects execution ownership of the
same turn. Terminal stale claims may be replaced atomically; active or
approval-waiting claims may not. The lease's `claimed_at` value is also the
owner fence: renewals, checkpoints, and terminal writes must match it, and
recovery must respect an unexpired lease. Aggregate boundaries keep the first
user transcript atomic with turn creation and keep successful action state
atomic with its artifact and audit events.

## Explicit Non-Goals

- No planner DAG, WorkflowContract DSL, or semantic progress ontology.
- No new Phoenix-specific tool in this change.
- No provider-native tool-search or Programmatic Tool Calling abstraction.
- No plugin, memory, subagent, scheduler, or frontend redesign.
- No replacement of LiteLLM or migration to the Responses API.
- No new database table or migration unless implementation evidence proves the
  existing turn snapshots cannot safely persist the required state.

## References

- OpenAI Codex Prompting Guide:
  <https://developers.openai.com/cookbook/examples/gpt-5/codex_prompting_guide>
- OpenAI Using Tools:
  <https://developers.openai.com/api/docs/guides/tools>
- OpenAI Programmatic Tool Calling:
  <https://developers.openai.com/api/docs/guides/tools-programmatic-tool-calling>
- Claude Code, How Claude Code works:
  <https://code.claude.com/docs/en/how-claude-code-works>
- Hermes Agent architecture:
  <https://hermes-agent.nousresearch.com/docs/developer-guide/architecture>
