# BioinfoFlow domain glossary

## Agent Core

- **Turn**: one durable attempt by an agent session to process user input and
  reach a terminal result. A turn may pause for approval or resume after an
  action.
- **Capability decision**: the current decision about whether a tool is
  exposed, callable, or resumable for a turn action, given the session policy,
  role, execution target, execution scope, and assessed risk.
- **Permission context**: the fresh session state used to make a capability
  decision. It includes policy version, approval modes, target, scope, and
  effective execution facts.
- **Tool action**: one durable attempt to invoke a tool. It records its
  decision context and may wait for approval before it becomes terminal.
- **Tool-call batch**: the durable group of tool actions produced by one model
  response. The model may continue only after every action has one terminal
  result.
- **Turn ownership**: the worker generation currently allowed to publish
  durable state for a turn. Ownership is leased and can be replaced.
- **Execution target**: the local environment or one selected remote SSH
  environment in which a tool action operates.
- **Plan approval**: the user decision that allows the current plan interaction
  to transition into execution and resume its waiting turn.
- **Model resolution**: the ordered decision that turns turn/session model
  requests and catalog defaults into an executable model target, including
  credentials, transport policy, target revision, and fallback candidates.
