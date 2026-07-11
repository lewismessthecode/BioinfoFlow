# Data Codemap

**Last Updated:** 2026-07-11

## Persistence Stack

- SQLAlchemy async with SQLite/aiosqlite
- Alembic migrations under `backend/alembic/versions/`
- Repository boundary under `backend/app/repositories/`
- Pydantic request/response contracts under `backend/app/schemas/`
- Frontend API types under `frontend/lib/`

Services should use repositories instead of adding direct database queries.

## Current Model Domains

| Domain | Representative durable state |
| --- | --- |
| Workspaces and access | workspace metadata and audit records |
| Projects | managed, external-local, and remote projects; workflow bindings and pins |
| Workflows and runs | workflow registration, run configuration/lifecycle, batches, notifications, and images |
| Registries and connections | container registries and SSH Remote Connections with encrypted credential references |
| LLM configuration | provider catalog, credentials, model/profile configuration, and runtime strategy |
| AgentCore | sessions, turns, messages, persisted events, actions, artifacts, memory, execution state, skills/plugins, and targets |

The retired legacy conversation, message, trace, approval, Hermes-handle, and
user-settings tables were removed by later migrations. Do not build new features
against those old names.

## Repositories And Schemas

Current repositories cover projects, workflows, runs, batches, notifications,
images, stats, audit records, workspaces, project workflow relationships,
container registries, Remote Connections, LLM state, and AgentCore state.

Current schemas cover projects, project workflows, workflows, runs, files,
storage, images, forms, notifications, terminal/system data, container
registries, Remote Connections, LLM configuration, and AgentCore contracts.

## Migration Landmarks

The migration graph currently reaches the `0042` series. Important recent
landmarks include:

- `0028`–`0030`: AgentCore contracts, legacy agent-table removal, and harness runtime
- `0031`–`0036`: LLM credentials/profile changes and legacy settings cleanup
- `0037`–`0038`: Remote Connections and remote projects
- `0039`–`0040`: container registries and unique global default enforcement
- `0041`: run-module invariants
- `0042`: stored Remote Connection credentials

Use `uv run alembic heads`, `uv run alembic current`, and the migration files
for the authoritative graph; numeric prefixes are not a reliable file count
because earlier branches include merge points and repeated prefixes.
