# Data Codemap

**Last Updated:** 2026-08-14

## Persistence Stack

- SQLAlchemy async with SQLite/aiosqlite
- Alembic migrations under `backend/alembic/versions/`
- Repository boundary under `backend/app/repositories/`
- Pydantic request/response contracts under `backend/app/schemas/` and service contract modules
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
| Agent Harness | Session, Run, Entry, Attachment, Artifact, and AgentToken |

## Agent Harness Data Contract

| Model | Table | Purpose |
| --- | --- | --- |
| `AgentHarnessSession` | `agent_sessions` | user/workspace/project binding, model/workspace/prompt snapshots, permission mode, command queue, and history revision |
| `AgentHarnessRun` | `agent_runs` | one active execution per session, phase, lease fence, draft, tool progress, checkpoint, usage, and termination state |
| `AgentHarnessEntry` | `agent_entries` | ordered durable history using `message`, `interaction_request`, `interaction_response`, `compaction`, or `notice` payloads |
| `AgentHarnessAttachment` | `agent_attachments` | uploaded file, folder, or image metadata and storage path |
| `AgentHarnessArtifact` | `agent_artifacts` | durable structured or file-backed Agent outputs |
| `AgentToken` | `agent_tokens` | hashed, expiring, revocable credential scoped to one user/workspace/session/run |

The old `agent_turns`, `agent_messages`, `agent_events`, `agent_actions`,
`agent_approvals`, `agent_tool_call_batches`, and `agent_memories` tables are not
current extension points. Migration `0059_complete_agent_harness` copies
committed conversation state into runs and entries, replaces the tables, and is
intentionally one-way.

## Repositories And Contracts

Current repositories cover projects, workflows, workflow runs, batches,
notifications, images, stats, audit records, workspaces, project workflow
relationships, container registries, Remote Connections, LLM state, Agent
Harness state, and Agent Tokens.

The Agent service contract uses strict command, snapshot, history-entry, and SSE
event models from `backend/app/services/agent_harness/contracts.py`. The durable
snapshot is authoritative; `backend/app/services/agent_harness/events.py`
provides only live fan-out.

## Migration Landmarks

The migration graph currently reaches `0059_complete_agent_harness`. Important
recent landmarks include:

- `0028`–`0030`: earlier Agent runtime contracts and cleanup
- `0031`–`0036`: LLM credentials/profile changes and legacy settings cleanup
- `0037`–`0042`: Remote Connections, remote projects, registries, run invariants, and stored connection credentials
- `0043`–`0053`: provider protocol, earlier Agent execution/permission/batch evolution, and jump hosts
- `0054`–`0057`: earlier attachments, steering, collaboration, readable project directories, and merge points
- `0058`: removal of the container-registry global default
- `0059`: one-way replacement of the earlier Agent tables with the complete Agent Harness schema plus `agent_tokens`

Use `uv run alembic heads`, `uv run alembic current`, and the migration files
for the authoritative graph; numeric prefixes are not a reliable file count
because earlier branches include merge points and repeated prefixes.
