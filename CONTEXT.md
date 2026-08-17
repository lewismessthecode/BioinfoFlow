# BioinfoFlow Domain Glossary / BioinfoFlow 领域词典

## Current Agent Core

The terms below describe the implementation being replaced. Do not use them as
the target domain model for new Agent Harness work. The accepted target
vocabulary is maintained in
`docs/plans/2026-08-13-complete-agent-harness-rearchitecture.md`.

- **Conversation / 对话**: the durable product container for related user and
  agent work. It preserves semantic continuity independently of any model
  provider or agent harness.
- **Turn / 回合**: one user-meaningful unit of agent work inside a Conversation.
  A Turn may contain multiple engine runs, pause for decisions, and resume after
  actions without becoming a new Turn.
- **Tool Call / 工具调用意图**: a finalized agent request to use one capability
  with specific arguments. It records intent but does not mean that an external
  effect has been authorized or executed.
- **Tool Action / 工具动作**: one governed attempt to settle a Tool Call through
  authorization, optional approval, execution, and result recording.
- **Decision Request / 决策请求**: a durable question that suspends progress
  until an authorized actor resolves it.
- **Decision / 决策**: the immutable resolution of a Decision Request.
- **Approval / 审批**: a Decision whose subject is whether a governed action may
  proceed. Approval is not a synonym for authorization.
- **Artifact / 产物**: a user-addressable output produced or published by a Turn
  or Tool Action, such as a file, report, dataset, or structured result.
- **Capability decision**: the current decision about whether a tool is
  exposed, callable, or resumable for a turn action, given the session policy,
  role, execution target, execution scope, and assessed risk.
- **Permission context**: the fresh session state used to make a capability
  decision. It includes policy version, approval modes, target, scope, and
  effective execution facts.
- **Tool Round / 工具轮次**: the durable group of Tool Calls produced by one
  model response. The model may continue only after every Tool Call has one
  resolved result.
- **Execution claim**: the temporary, fenced right granted to one worker
  generation to advance and publish durable state for a Turn. The claim is
  lease-bounded and can be replaced.
- **Execution target**: the local environment or one selected remote SSH
  environment in which a tool action operates.
- **Plan approval**: an approval Decision that allows the current plan
  interaction to transition into execution and resume its waiting Turn.
- **Model resolution**: the ordered decision that turns turn/session model
  requests and catalog defaults into an executable model target, including
  credentials, transport policy, target revision, and fallback candidates.

## Stable Agent Conversation

**Presentation Contract / 呈现协议**:
The versioned, Harness-independent product language used to present one Agent
Conversation to clients. It contains only durable or explicitly public facts.
_Avoid_: Harness event schema, provider transcript

**Conversation View / 对话视图**:
The client-facing projection of a Conversation, including its current settings,
Transcript Blocks, and active work. It is derived from the Presentation Contract.
_Avoid_: Harness snapshot, renderer state

**Transcript Block / 对话记录块**:
A stable, ordered unit in the Conversation View, such as a message, reasoning
trace, activity group, interaction, artifact, notice, or run outcome.
_Avoid_: raw event, provider item

**Conversation Setting / 对话设置**:
A user-selected default for future Runs in one Conversation, such as model,
permission policy, or environment scope.
_Avoid_: session constant, composer-only preference

**Turn Execution Config / 执行配置快照**:
The immutable effective settings used by one started Run. Later Conversation
Setting changes do not alter it.
_Avoid_: current composer settings, mutable run settings

**Execution Environment / 执行环境**:
One authorized local or remote place where Agent tools may operate.
_Avoid_: host, node, workspace runtime

**Environment Scope / 环境范围**:
The set of Execution Environments visible to a Run. Auto resolves all authorized
environments; Manual resolves the user-selected subset.
_Avoid_: current machine, SSH selector value

**Reasoning Trace / 推理轨迹**:
Textual reasoning content explicitly returned by a model provider for display.
It does not include encrypted continuation state or imply access to private model
reasoning.
_Avoid_: complete chain of thought, encrypted reasoning

**Agent Trace View / Agent 轨迹视图**:
A Conversation-scoped, Harness-independent presentation of normalized System,
User, Context, Assistant, and Tool events in occurrence order, grouped by Turn.
_Avoid_: platform trace, Conversation transcript, Harness log

**Trace Event / 轨迹事件**:
One stable, ordered fact in an Agent Trace View, classified as System, User,
Context, Assistant, or Tool.
_Avoid_: provider event, log line, Transcript Block

**Raw Model Trace / 原始模型轨迹**:
The exact model request, model response, and Tool payload content associated with
a Trace Event for local inspection.
_Avoid_: Conversation View, public summary, normalized transcript

**Context Composition / 上下文构成**:
The token composition of one model request's context window, grouped by stable
source categories. It is not cumulative Turn usage or a token budget.
_Avoid_: usage progress, Run token total, cost meter

**Context Snapshot / 上下文快照**:
The complete ordered logical context submitted for one model request. Cached
prefix content remains part of the snapshot even when its computation is reused.
_Avoid_: Turn history, cache contents, cumulative usage

**Context Flow / 上下文流**:
The Conversation-wide append history showing how logical content enters and
evolves across successive Context Snapshots while preserving Turn order.
_Avoid_: Context Snapshot, cumulative billing usage, event timeline
