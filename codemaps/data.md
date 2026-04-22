# Data Codemap
<!-- Generated: 2026-04-17 | Files scanned: 18 models, 18 repos, 14 schemas | Token estimate: ~800 -->
**Last Updated:** 2026-04-17
**Entry Points:** `backend/app/models/`, `backend/alembic/versions/*.py`, `backend/app/schemas/`, `frontend/lib/types.ts`

## Architecture
```
Pydantic Schemas ↔ FastAPI ↔ Repositories ↔ SQLAlchemy Models ↔ SQLite
                        │
                        └─ Frontend types mirror API envelopes
```

## Path Contract v2 (migrations 0019–0021)
- `Project` no longer carries `workspace_path` or `data_roots`.
- New fields: `storage_mode` (`managed` | `external`), `external_root_path`, `workspace_id`, `created_by_user_id`.
- Run artifacts live under a unified `runs/<run_id>/` layout; the database is the source of truth for locations.
- `/storage` API + `storage_service.py` expose storage mode + external root CRUD.

## Database Tables (23 Alembic migrations)
- `projects` (name, description, storage_mode, external_root_path, workspace_id, user_id, created_by_user_id, is_default)
- `workflows` (source, engine, source_ref, entrypoint_relpath, bundle_kind, version, schema_json, submission_hint, weight, estimated_time)
- `docker_images` (name, tag, status, pull_failure_reason)
- `runs` (run_id, status, config, workspace, samples_count, tasks_total/completed)
- `conversations` (title, pinned, policy_mode, user_id)
- `messages` (role, type, content, metadata)
- `agent_traces` (type, payload)
- `agent_approvals` (tool_name, risk_level, status)
- `project_workflow_bindings` (project_id, workflow_id)
- `project_workflow_pins` (project_id, workflow_source, workflow_name, pinned_workflow_id)
- `scheduled_tasks` (priority, state, run_id, weight)
- `audit_logs` (action, entity, actor, payload)
- `batches` + `batch_runs` (batch processing)
- `notification_configs` (notification rules)
- `user_settings` (user_id, provider, model, preferences JSON)
- `workspaces` (name, mode, owner)
- `workspace_memberships` (workspace_id, user_id, role)

## ORM Models (backend/app/models, 18 files)
| Model | Table | Key Fields |
| --- | --- | --- |
| `Project` | projects | name, description, storage_mode, external_root_path, workspace_id, user_id, is_default |
| `Workflow` | workflows | source, engine, source_ref, entrypoint_relpath, bundle_kind, version, schema_json, submission_hint, weight |
| `Run` | runs | run_id, status, config, workspace, samples_count |
| `RunConfigHelper` | — | config parsing utilities (no table) |
| `DockerImage` | docker_images | name, tag, status, pull_failure_reason |
| `Conversation` | conversations | title, pinned, policy_mode, user_id |
| `Message` | messages | role, type, content, metadata |
| `AgentTrace` | agent_traces | type, payload |
| `AgentApproval` | agent_approvals | tool_name, risk_level, status |
| `ProjectWorkflowBinding` | project_workflow_bindings | project_id, workflow_id |
| `ProjectWorkflowPin` | project_workflow_pins | project_id, workflow_source, pinned_workflow_id |
| `ScheduledTask` | scheduled_tasks | priority, state, run_id, weight |
| `AuditLog` | audit_logs | action, entity, actor, payload |
| `Batch` + `BatchRun` | batches, batch_runs | batch lifecycle |
| `NotificationConfig` | notification_configs | trigger, destination, enabled |
| `UserSettings` | user_settings | user_id, provider, model, preferences |
| `Workspace` | workspaces | name, mode, owner |
| `WorkspaceMembership` | workspace_memberships | workspace_id, user_id, role |

## Repositories (backend/app/repositories, 18 repos)
| Repository | Model | Notes |
| --- | --- | --- |
| `BaseRepository[T]` | Generic | CRUD + cursor pagination |
| `ProjectRepository` | Project | |
| `WorkflowRepository` | Workflow | |
| `RunRepository` | Run | Status/project filtering |
| `ConversationRepository` | Conversation | |
| `MessageRepository` | Message | |
| `AgentTraceRepository` | AgentTrace | message_id filtering |
| `ApprovalRepository` | AgentApproval | Status queries |
| `ImageRepository` | DockerImage | |
| `ProjectWorkflowBindingRepository` | ProjectWorkflowBinding | Enable/disable |
| `ProjectWorkflowPinRepository` | ProjectWorkflowPin | Version pinning |
| `BatchRepository` | Batch | Batch lifecycle |
| `NotificationRepository` | NotificationConfig | CRUD + trigger queries |
| `StatsRepository` | — | Aggregated dashboard metrics |
| `AuditRepository` | AuditLog | Action history |
| `UserSettingsRepository` | UserSettings | Per-user preferences |
| `WorkspaceRepository` | Workspace + WorkspaceMembership | Unified workspace + team membership |

> Note: services must route DB queries through repositories — `session.execute()` in service code is forbidden (enforced 2026-04-04).

## API Schemas (backend/app/schemas, 14 files)
- `agent.py`: conversation/message/trace/approval payloads
- `common.py`: envelope + pagination
- `demo.py`: demo catalog + seed responses
- `file.py`: file scan/read/write/upload
- `image.py`: image read + pull
- `notification.py`: notification config CRUD
- `project.py`: project CRUD (storage_mode fields)
- `project_workflow.py`: workflow binding + pinning
- `run.py`: run lifecycle + retry/resume + batch
- `storage.py`: project storage backend + external roots (path contract v2)
- `system.py`: health + GPU metrics
- `terminal.py`: terminal session create/close
- `user_settings.py`: user preferences
- `workflow.py`: workflow registry

## Frontend Types (frontend/lib/types.ts)
- API envelope + meta types
- Core domain types: `Project`, `Workflow`, `Run`, `DockerImage` (Project includes `storageMode`, `externalRootPath`)
- Agent types: `AgentMessageRead`, `AgentConversationRead`, `AgentTraceResponse`
- SSE event shapes: `RunStatusEvent`, `RunLogEvent`, `RunDagEvent`, `ImageProgressEvent`
- Plan types: `PlanStep`, `ExecutionPlan`
- DAG types: `DagNode`, `DagEdge`, `DagData`
- Scheduler types: `SchedulerStatus`, `SystemResources`, slot shapes
- Batch types: `BatchStatus`, `Batch`, `BatchDetail`, `RetryPolicy`, `TaskPriority`
- Notification types: `NotificationTrigger`, `NotificationConfig`
- Terminal types: `TerminalSession`, `TerminalMessage`
- User settings: `UserSettings`, `LLMProvider`

## Alembic Migrations (23 revisions)
| # | Description |
|---|---|
| 0001 | Initial schema (projects, workflows, runs, images, conversations, messages) |
| 0002 | Agent traces + conversation fields |
| 0003 | Project workflow bindings + pins |
| 0004 | Agent approvals + policy mode |
| 0005 | Scheduled tasks + workflow launch defaults (two heads at this revision) |
| 0006 | Audit logs + retry delay |
| 0007 | Batches + notifications |
| 0008 | User IDs on projects + conversations |
| 0009 | User settings |
| 0010 | Submission hint on workflows |
| 0011 | Data roots on projects |
| 0012 | OpenRouter + Ollama settings |
| 0013 | Weight on workflows + tasks |
| 0014 | New provider API keys |
| 0015 | Provider credentials JSON |
| 0016 | Project `is_default` flag |
| 0017 | Image pull failures + workspace/team auth tables (two heads: `0017_image_pull_failures`, `0017_workspace_team_auth`) |
| 0018 | Merge heads (workspace/team auth + image pull failures) |
| 0019 | Project storage fields (`storage_mode`, `external_root_path`, `workspace_id`) |
| 0020 | Path contract v2 — unified run layout |
| 0021 | Remove `data_roots` from projects |

## External Dependencies
- SQLAlchemy async + aiosqlite, Alembic migrations, Pydantic v2.

## Related Areas
- [Backend Codemap](backend.md)
- [Frontend Codemap](frontend.md)
