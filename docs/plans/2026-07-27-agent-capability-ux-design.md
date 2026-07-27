# Agent Capability UX Design

## Problem

An Agent turn asked BioinfoFlow to register a workflow, bind it to a project,
submit a run, and report the failure cause. The normal execution toolset did not
expose the platform mutation tools required for that lifecycle. The model found
the development checkout through the inherited shell `PATH`, tried the editable
`bif` entrypoint, and repeatedly probed product source that the OS sandbox
correctly denied. The same turn guessed two skill names even though the configured
skill directory was empty because `skills.load` remained visible without an
authoritative skill index.

## First-principles boundary

The Agent needs capabilities that accomplish the user's platform goal. It does
not need BioinfoFlow implementation source, an editable developer CLI, or network
access to its own backend. BioinfoFlow platform tools are the single Agent-facing
control-plane interface. The OS sandbox remains the security boundary for local
processes; prompt and tool exposure should accurately describe the capabilities
inside that boundary.

## Design

### 1. Make normal execution operationally complete

The canonical execution policy includes the existing `bioinfo.read` and
`bioinfo.manage` capability bundles. Session creation, mode changes, and plan-mode
exit must all resolve `execution` to the same canonical policy. Read-only and
mutating platform tools retain their existing permission and approval behavior.

### 2. State the product-source boundary plainly

Local environment context tells the model that BioinfoFlow product source is not
part of the Agent workspace and that platform operations must use exposed
BioinfoFlow tools rather than `bif`. This is guidance, not a replacement for the
OS sandbox. No shell parser, localhost exception, alternate CLI package, or PATH
rewriting is introduced.

### 3. Advertise skills only when they exist

The model-visible `skills.load` schema is removed for a model iteration when the
configured registry is empty. When skills exist, their real names and summaries
continue to be injected into context. If a requested name is missing, the tool
error includes the currently available names so the model can recover without
guessing again.

## Non-goals

- Do not expose BioinfoFlow product source.
- Do not allow Agent shell access to the backend localhost API.
- Do not package or install a second Agent-specific `bif` CLI.
- Do not add shell-command parsing intended to detect every possible source probe.
- Do not change the OS sandbox or permission approval model.
- Do not add new UI controls or configuration switches.

## Verification

- Unit tests prove the canonical execution policy exposes workflow creation,
  project binding, run submission, and platform inspection tools.
- Service/API tests prove execution mode consistently persists the canonical
  capability policy.
- Context tests prove the product-source and `bif` guidance appears only for local
  targets.
- Tool exposure tests prove `skills.load` is absent for an empty registry and
  present for a non-empty registry.
- Skill-tool tests prove missing-name errors list real available skills.
- Run the focused AgentCore tests, the full AgentCore suite, Ruff, and diff checks.
