# API Reference

Base URL: `/api/v1`

## Response Contract

Most endpoints return an envelope:

- success: `{ "success": true, "data": ..., "meta": ... }`
- error: `{ "success": false, "error": { "code": "...", "message": "..." }, "meta": ... }`

Exceptions:

- server-sent events: `GET /events/stream`
- scheduler resource stream: `GET /scheduler/resources/stream`
- WebSockets: terminal and scheduler btop panels
- binary downloads: file and run output archives

OpenAPI remains the field-level source of truth: `GET /api/v1/openapi.json`

## Auth And Scope

- This repo does not expose first-party `/auth/*` login routes.
- Most business APIs require `get_current_user`.
- User and workspace scope are enforced server-side through `user.id` and `user.workspace_id`.
- Projects and conversations are workspace-scoped resources.
- Run detail/log/output access is owner-scoped through the parent project.

## Projects

- `GET /projects`
- `POST /projects`
- `GET /projects/default`
- `GET /projects/{project_id}`
- `PATCH /projects/{project_id}`
- `DELETE /projects/{project_id}`

Notes:

- `GET /projects/default` returns or creates the workspace default project.
- Project selection is the top-level scope for runs, files, agent conversations, and workflow bindings.

## Project Workflows

- `GET /projects/{project_id}/workflows`
- `POST /projects/{project_id}/workflows/{workflow_id}:bind`
- `DELETE /projects/{project_id}/workflows/{workflow_id}:unbind`
- `POST /projects/{project_id}/workflow-pins`

Notes:

- A workflow must be bound to a project before `/runs` can accept it.
- Binding is part of the canonical “register workflow -> enable for project -> submit run” flow.

## Workflows

- `GET /workflows`
- `POST /workflows/validate`
- `POST /workflows`
- `POST /workflows/local-bundle`
- `GET /workflows/{workflow_id}`
- `PATCH /workflows/{workflow_id}`
- `DELETE /workflows/{workflow_id}`
- `GET /workflows/{workflow_id}/dag`
- `GET /workflows/{workflow_id}/form-spec`
- `GET /workflows/{workflow_id}/source`

Notes:

- `POST /workflows/validate` validates source content before persistence.
- `POST /workflows/local-bundle` accepts a multipart upload of a local workflow directory plus a selected `entrypoint_relpath`.
- `GET /workflows/{workflow_id}/form-spec` is the frontend and agent source of truth for run input rendering.

## Runs

- `GET /runs`
- `POST /runs/uploads`
- `POST /runs`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/logs`
- `GET /runs/{run_id}/dag`
- `POST /runs/{run_id}/repair-dag`
- `POST /runs/repair-dags`
- `POST /runs/{run_id}/mock-dag-variants`
- `GET /runs/{run_id}/outputs`
- `GET /runs/{run_id}/outputs/download`
- `POST /runs/{run_id}/cancel`
- `POST /runs/{run_id}/resume`
- `POST /runs/{run_id}/retry`
- `POST /runs/{run_id}/cleanup`
- `GET /runs/{run_id}/audit`
- `DELETE /runs/{run_id}`

Canonical create contract:

```json
{
  "project_id": "uuid",
  "workflow_id": "uuid",
  "values": {
    "field_id": "value"
  },
  "options": {
    "profile": "docker",
    "max_retries": 1,
    "timeout_seconds": 3600
  }
}
```

Notes:

- `/runs/wizard` has been removed. All create flows should go through `POST /runs`.
- `POST /runs/uploads` accepts `multipart/form-data` with `project_id` and `file`, and returns a temporary `asset://run_upload/...` URI for runtime documents such as manifests.
- `values` are keyed by `GET /workflows/{workflow_id}/form-spec`.
- The backend resolves `asset://...` URIs, validates allowed roots, snapshots runtime documents marked by `materialize_to_run`, materializes table attachments, and compiles engine-ready params/inputs before queueing.
- create/resume/retry return `202`
- resume/retry create a new run record rather than mutating the original failed run

## Batch Runs

Prefix: `/runs/batch`

- `POST /runs/batch`
- `GET /runs/batch/{batch_id}`
- `POST /runs/batch/{batch_id}/cancel`

Batch items use the same envelope fields as `/runs`, but without `project_id` per row:

```json
{
  "project_id": "uuid",
  "runs": [
    {
      "workflow_id": "uuid",
      "values": {
        "sample_id": "A"
      },
      "options": {
        "profile": "docker"
      }
    }
  ]
}
```

## Files

- `GET /files`
- `GET /files/read`
- `GET /files/download`
- `POST /files/write`
- `POST /files/upload`
- `POST /files/scan`
- `DELETE /files`

All file endpoints are scoped to the selected project workspace.

## Storage

- `GET /storage/sources`
- `GET /storage/browse`
- `GET /storage/read`
- `GET /storage/download`
- `POST /storage/upload`
- `POST /storage/scan`

Notes:

- Storage endpoints expose logical sources such as project data, deliveries, reference, database, and run results.
- `asset://...` URIs returned here are the same URIs accepted by run submission.

## Images

- `GET /images`
- `GET /images/{image_id}`
- `POST /images/pull`
- `POST /images/load`
- `DELETE /images/{image_id}`

Notes:

- Image pull/load state is streamed over `/events/stream` as `image.progress`.

## Events

- `GET /events/stream?project_id=...&conversation_id=...&run_id=...&image_id=...`

Current event names:

- `run.status`
- `run.log`
- `run.dag`
- `image.progress`
- `agent.message`
- `agent.text_delta`
- `agent.thinking`
- `agent.thinking_content`
- `agent.thinking_delta`
- `agent.plan`
- `agent.artifact`
- `agent.tool_call_start`
- `agent.tool_call_progress`
- `agent.tool_call_end`
- `agent.approval.requested`
- `agent.approval.resolved`
- `agent.done`
- `agent.cancelled`
- `agent.error`

## Agent

- `POST /agent/message`
- `POST /agent/conversations`
- `PATCH /agent/conversations/{conversation_id}`
- `PATCH /agent/conversations/{conversation_id}/move`
- `DELETE /agent/conversations/{conversation_id}`
- `GET /agent/conversations`
- `GET /agent/conversations/{conversation_id}`
- `POST /agent/conversations/{conversation_id}/cancel`
- `GET /agent/conversations/{conversation_id}/status`
- `GET /agent/conversations/{conversation_id}/trace`
- `POST /agent/approvals/{approval_id}/resolve`
- `GET /agent/approvals/{approval_id}`
- `GET /agent/conversations/{conversation_id}/approvals`
- `GET /agent/conversations/{conversation_id}/approvals/pending`

Notes:

- `POST /agent/message` can create a new conversation implicitly.
- `execution_policy` can now be staged on first message or explicit conversation creation.
- Conversation trace and update routes are access-controlled and should honor workspace ownership.

## Scheduler

- `GET /scheduler/status`
- `GET /scheduler/resources`
- `GET /scheduler/resources/stream`
- `WS /scheduler/btop/ws`

Notes:

- `/scheduler/status` reports configured mode, effective mode, queue state, and active runs.
- `/scheduler/resources/stream` is host-scoped SSE for live CPU / memory / disk / GPU snapshots.
- `/scheduler/btop/ws` is a websocket bridge for the advanced process panel and requires an authenticated session cookie when auth is enabled.

## Terminal

- `POST /terminal/sessions`
- `DELETE /terminal/sessions/{session_id}`
- `WS /terminal/sessions/{session_id}/ws`

Terminal sessions are scoped to a project workspace. The delete endpoint and websocket attachment both re-check project access. The WebSocket accepts JSON messages with `type` field: `input`, `resize`, `chdir`, `ping`.

## Notifications

- `POST /notifications`
- `GET /notifications`
- `DELETE /notifications/{notification_id}`

## User Settings And Providers

- `GET /user-settings`
- `PATCH /user-settings`
- `POST /user-settings/test/{provider}`
- `GET /user-settings/models`
- `GET /providers`

## Stats And System

- `GET /stats`
- `GET /system/ping`
- `GET /system/health`
- `GET /system/gpu`
- `GET /system/gpu/metrics`
- `GET /system/directories`

## Contract Notes

- Frontend request helpers live in `frontend/lib/api.ts`; envelope changes must be coordinated with frontend types and hooks.
- Run submission, batch submission, agent `submit_run`, and demo launch should all converge on the same `{project_id, workflow_id, values, options}` model.
