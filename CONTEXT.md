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
