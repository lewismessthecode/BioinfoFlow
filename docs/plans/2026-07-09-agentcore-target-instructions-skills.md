# AgentCore Target, Instructions, And Skills Plan

## Goal

Implement AgentCore target-aware tool execution plus project instruction and
skills alignment, validate and commit each phase, run parallel review agents,
fix review findings, and open a PR.

## Architecture

The harness must treat the selected runtime target as a capability boundary, not
as prompt-only context. Tool registration remains global, but exposure and
execution become target-aware. Project instructions and skills are loaded as
progressive context sources and must respect the same target boundary.

## Parallel Execution

- Phase 1 worker owns backend execution target, tool exposure, executor checks,
  and remote tool default connection behavior.
- Phase 2 worker owns frontend runtime/composer target wiring and compatibility
  with existing remote metadata.
- Phase 3 worker owns project instruction discovery and context injection.
- Phase 4 worker owns skill discovery, parsing, precedence, and prompt budget.
- The controller integrates, validates, and commits one phase at a time.

## Phase 1: Execution Target Boundary

Backend sessions expose a normalized `execution_target` without requiring a
schema migration. `local` keeps current behavior. `remote_ssh` is derived from
the normalized field or legacy `metadata.remote_connection_id`.

`ToolsetExposure` accepts the target and filters tool schemas before model
calls. `remote_ssh` sessions expose remote tools and target-neutral tools only;
local shell, local files/search, and local platform tools are hidden. The
executor repeats the same check before dispatch so stale model contexts cannot
call a hidden local tool.

Remote tools may omit `connection_id` when exactly one session-selected remote
connection exists. Explicit mismatched connection ids remain rejected.

Validation:

```bash
cd backend && rtk uv run pytest tests/test_agent_remote_tools.py tests/test_agent_core/test_harness_invariants.py tests/test_api/test_agent_core_api.py -q
cd backend && rtk uv run ruff check .
```

Commit: `feat: add target-aware agent tool exposure`

## Phase 2: Frontend Target Wiring

The composer/runtime client sends a normalized execution target when a remote
connection is selected while preserving old sessions that only have
`metadata.remote_connection_id`. Environment UI should distinguish selected SSH
target from local platform execution and keep mode, permission, model, and
skills behavior unchanged.

Validation:

```bash
cd frontend && rtk bun run lint
cd frontend && rtk bun run test
cd frontend && rtk bun run lint:i18n
```

Run `lint:i18n` only if UI copy changes.

Commit: `feat: wire agent execution target in UI`

## Phase 3: Project Instructions

Add a project instruction resolver loaded after the stable system prompt and
before dynamic environment context. Local targets read from `settings.repo_root`.
Remote SSH targets use `remote_project_root` and a safe resolver seam; if live
remote reads are unavailable, cache a snapshot in session metadata and avoid
breaking turns.

Within each directory, choose the first non-empty file in this order:
`AGENTS.override.md`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`. Concatenate
root-to-current with source labels and a 32768 byte cap.

Validation:

```bash
cd backend && rtk uv run pytest tests/test_agent_core/test_context_compaction.py -q
cd backend && rtk uv run ruff check .
```

Commit: `feat: load project agent instructions`

## Phase 4: Skills Alignment

Skill discovery reads repo `.agents/skills/*/SKILL.md` plus the configured
skills root. Repo skills win when names collide. YAML frontmatter is preferred,
with the existing simple parser retained as a fallback.

Skill payloads include enough source/path metadata for debugging. Prompt skill
summaries have an 8000 character budget; explicitly active skills still inject
full bodies.

Validation:

```bash
cd backend && rtk uv run pytest tests/test_agent_core/test_skills_plugins.py tests/test_agent_core/test_context_compaction.py tests/test_api/test_agent_core_api.py -q
cd backend && rtk uv run ruff check .
```

Commit: `feat: align agent skills discovery`

## Final Review And PR

After all phases pass, run broad validation:

```bash
cd backend && rtk uv run pytest
cd backend && rtk uv run ruff check .
cd frontend && rtk bun run lint
cd frontend && rtk bun run test
```

Spawn parallel reviewers for execution-target security, instruction loading,
skills compatibility, and frontend compatibility. Fix all critical or important
findings, rerun relevant checks, commit fixes, rebase on `origin/main`, push,
and open a ready PR titled:

```text
feat: add target-aware AgentCore instructions and skills
```
