# Bioinfoflow Agent Platform Tools And Prompt V1

## Scope

- Expand AgentCore with thin Bioinfoflow platform tools for projects, project
  workflow bindings, workflows, images, runs, and scheduler evidence.
- Upgrade the stable Bioinfoflow agent system prompt to `bioinfoflow-agent-v5`.
- Improve tool argument normalization and make validation failures visible as
  structured failed actions.

## Non-Goals

- No frontend UI changes.
- No database schema changes.
- No over-packaged diagnosis, auto-repair, or planning tools. The agent should
  compose platform evidence tools directly.

## Tooling Plan

- Register new tools separately from exposure. The registry knows all tools;
  toolsets decide whether a session may see them.
- Keep read tools available in plan/default/execution modes.
- Keep mutating and destructive tools execution-only and permission-gated by
  existing risk policy.
- Use existing services and repositories directly, not HTTP, `bif`, shell, or
  ad hoc database access.
- Preserve workspace boundaries for project-scoped tools before calling lower
  level services.

## Prompt Plan

- Move the prompt snapshot to `bioinfoflow-agent-v5`.
- Make the stable prompt Bioinfoflow-specific:
  platform tools before shell for platform state, pre-submit checks, post-submit
  verification, exact IDs and field keys, JSON-object tool inputs, and
  evidence-based success claims.
- Keep dynamic state such as current project, cwd, exposed tools, and recent
  session events outside the stable prefix.

## Verification Plan

- Unit tests for tool registration, exposure, and platform read/mutation tools.
- Middleware tests for common argument coercion and validation failures.
- Prompt tests for v5 snapshot behavior and required operating rules.
- Cross-workspace tests for project-scoped binding tools.
- Backend checks:
  `rtk uv run pytest tests/test_agent_core tests/test_api/test_agent_core_api.py`
  and `rtk uv run ruff check .`.
