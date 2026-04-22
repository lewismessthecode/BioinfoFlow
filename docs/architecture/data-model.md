# Data Model

## Core Tables

- `projects`: project metadata and workspace root.
- `workflows`: global workflow registry entries, engine/source metadata, and parsed schema JSON.
- `runs`: execution records keyed by `run_id`, with status, config, workspace, timing, task counters, and engine runtime fields.
- `docker_images`: tracked local/remote/pulling image inventory.
- `conversations`: project-scoped agent threads with `title`, `pinned`, and `policy_mode`.
- `messages`: persisted user/agent/system events for each conversation.
- `agent_traces`: observability payloads tied to conversation/message execution.
- `agent_approvals`: approval requests and resolutions for high-risk actions.
- `project_workflow_bindings`: project-enabled workflow versions.
- `project_workflow_pins`: per-project pinned workflow choice for a `(source, name)` group.
- `scheduled_tasks`: persistent scheduler queue entries for runs.
- `audit_logs`: action trail for run lifecycle and related operational hooks.
- `batches`: batch submission headers.
- `batch_runs`: join table from batches to individual runs.
- `notification_configs`: project-scoped webhook rules.

## Relationship Summary

- Project -> many Runs
- Project -> many Conversations
- Project -> many NotificationConfigs
- Project -> many Batches
- Workflow -> many Runs
- Project <-> Workflow through bindings and pins
- Conversation -> many Messages
- Conversation -> many AgentTraces
- Conversation -> many AgentApprovals
- Batch -> many BatchRuns -> one Run each
- Run -> zero or more ScheduledTasks over its lifecycle

## Important State Fields

- Run status: `pending`, `queued`, `running`, `completed`, `failed`, `cancelled`
- Scheduled task state: `queued`, `dispatched`, `completed`, `failed`, `cancelled`
- Scheduled task priority: `urgent`, `normal`, `low`
- Batch status: `pending`, `running`, `completed`, `partial`, `failed`, `cancelled`
- Workflow engine: `nextflow`, `wdl`
- Workflow source: `nf-core`, `github`, `local`
- Image status: `local`, `remote`, `pulling`
- Message role: `user`, `agent`, `system`
- Message type: `text`, `thinking`, `artifact`, `plan`, `status`, `completion`
- Notification trigger: `on_complete`, `on_failure`, `on_batch_complete`
- Notification channel: `webhook`
- Approval status: `pending`, `approved`, `rejected`

## Flexible Payload Columns

- `runs.config`: canonical execution payload, including params, inputs, config overrides, resolved runspec, retry policy, timeout, and runtime metadata such as PID.
- `messages.message_metadata`: structured plan/artifact/detail data emitted by the agent runtime.
- `agent_traces.payload`: raw observability events.
- `agent_approvals.payload`: proposed command, diff, run config, or similar approval context.
- `notification_configs.config`: webhook URL and optional headers.

## Migrations Present

- `0001_initial.py`
- `0002_agent_traces_and_conversation_fields.py`
- `0003_project_workflow_bindings_and_pins.py`
- `0004_agent_approvals_and_policy_mode.py`
- `0005_scheduled_tasks.py` (and `0005_workflow_launch_defaults.py`, a no-op placeholder for legacy DBs — Alembic multi-head)
- `0006_audit_logs_and_retry_delay.py`
- `0007_batches_and_notifications.py`

## Data Notes

- API responses use the standard `{ success, data, error, meta }` envelope except for streaming/binary endpoints.
- Primary keys are UUID-based; user-facing run and batch handles also have short IDs (`run_id`, `batch_id`).
- Frontend types in `frontend/lib/types.ts` mirror backend schema shape closely enough for compile-time API alignment.
