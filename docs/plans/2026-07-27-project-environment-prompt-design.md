# Project Environment Prompt Design

## Goal

Make the BioinfoFlow agent consistently reuse a project's established virtual
environment and package manager, while providing safe defaults when the project
has not established either choice.

## Problem

The provider-neutral system prompt tells the model to follow project
instructions, but it does not explicitly require environment discovery before
dependency installation or language-specific command execution. As a result,
an agent can install packages into the system Python, create a competing virtual
environment, or use a JavaScript package manager that conflicts with the
project's lockfile.

## Design

Keep the fix entirely in the stable system prompt. The agent already has shell
and search tools, so it can inspect the relevant directory without a new
environment detector, UI setting, or command-rewriting layer.

Add a `Project environments and package managers` section that requires the
agent to:

- inspect project instructions, manifests, lockfiles, package-manager metadata,
  and existing project-local environments before installing or running code;
- reuse the established environment and package manager without creating a
  competing environment or lockfile;
- avoid the system Python and unrelated global environments unless explicitly
  requested;
- follow explicit user and project instructions ahead of defaults;
- default to `uv` with a project-local `.venv` for Python when the project has
  no established manager;
- default to Bun for JavaScript and TypeScript when the project has no
  established manager;
- use the chosen manager consistently for dependency installation, scripts,
  tests, formatting, and lockfile updates;
- prefer explicit runners such as `uv run` and `bun run` because shell
  activation may not persist between tool calls;
- resolve conflicting environments or lockfiles against the directory that owns
  the task before making changes; and
- report the environment and package manager used after environment-dependent
  work.

The defaults do not migrate established Poetry, Conda, Pipenv, pip, npm, pnpm,
or Yarn projects.

## Prompt Snapshot Compatibility

Bump the default prompt snapshot from `bioinfoflow-agent-v10` to
`bioinfoflow-agent-v11`. Existing sessions continue using their stored prompt
verbatim, while new sessions receive the new contract.

## Verification

Extend the existing AgentCore harness invariant test to require the new section,
defaults, isolation rule, consistent-manager rule, explicit-runner guidance, and
final reporting requirement. Run the focused prompt tests, the full AgentCore
test directory, Ruff, and `git diff --check`.

## Non-goals

- No filesystem environment detector.
- No automatic shell-command rewriting.
- No package-manager installation.
- No frontend or settings UI.
- No migration of existing session prompt snapshots.
