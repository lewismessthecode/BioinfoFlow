# Frontend Codemap

**Last Updated:** 2026-08-14

## Stack And Entrypoints

- Next.js 16 App Router, React 19, TypeScript, Tailwind CSS 4, Radix UI, next-intl, Better Auth, React Flow, and xterm.js.
- `frontend/app/layout.tsx`: root document and providers.
- `frontend/proxy.ts`: auth-aware routing and protected-route redirects.
- `frontend/app/(app)/layout.tsx`: authenticated application shell.
- `frontend/lib/runtime/`: backend request and streaming clients.

## Pages

Protected product routes include:

| Route | Purpose |
| --- | --- |
| `/dashboard` | readiness, statistics, scheduler summary, and recent activity |
| `/agent`, `/agent/[sessionId]` | Agent home and session workbench |
| `/workflows`, `/workflows/[id]` | workflow catalog, registration, detail, and run submission |
| `/runs`, `/runs/[runId]` | workflow-run list, logs, DAG, audit, notifications, and outputs |
| `/images` | image inventory, pulls, registry selection, and tar imports |
| `/connections` | Remote Connection CRUD, testing, and probes |
| `/scheduler` | queue, pressure, active runs, resources, and advanced details |
| `/settings` | account, appearance, AI providers, container registries, and members |

Top-level navigation definitions live in `frontend/lib/nav-routes.ts`. Settings
sections and role filtering live in `frontend/lib/settings-nav.ts`.

## Agent Frontend Status

The backend Agent Harness contract has been replaced in this refactor; this
codemap does **not** claim that the frontend Agent workbench has already been
fully migrated. Existing `frontend/lib/agent-core/`,
`frontend/lib/agent-runtime/`, `frontend/hooks/use-agent-runtime.ts`, and
`frontend/components/bioinfoflow/agent-runtime/` code may still contain retired
Turn, Action, approval, skill, toolset, filesystem, or `/stream` assumptions.
Those modules are migration inputs, not the source of truth for the new backend.

The frontend migration must consume this backend contract:

- REST resources: Session, Run, Entry, Attachment, and Artifact projections.
- Commands: `prompt`, `steer`, `follow_up`, `respond`, and `cancel` through `POST /agent/sessions/{session_id}/commands`.
- Authoritative state: `GET /agent/sessions/{session_id}/snapshot`.
- Live state: `GET /agent/sessions/{session_id}/events`, beginning with `snapshot`, then `run.updated`, `assistant.delta`, `tool.updated`, `interaction.requested`, and `entry.committed`.
- User interaction: `ask_user` questions and dangerous-command confirmations are represented by `interaction.requested`, then answered with a `respond` command.
- Files and outputs: attachment upload/preview/delete and artifact list/get/download endpoints under `/agent`.

The intended client architecture is one snapshot-plus-event reducer shared by
the workbench, sidebar, composer, transcript, tool progress, interaction, and
artifact views. The frontend should not recreate a second durable event model.

## Shared UI

- `components/bioinfoflow/sidebar/`: app navigation, projects, sessions, and settings shell.
- `components/bioinfoflow/dag/`: workflow-run DAG rendering.
- `components/bioinfoflow/terminal/`: local and remote terminal dock.
- `components/bioinfoflow/settings/`: providers, registries, members, and settings content.
- `components/ui/`: reusable primitives and icon adapter.

## Auth And Localization

Better Auth routes live under `app/api/auth/`; sign-in lives under `app/auth/`.
`personal`, `team`, and `dev` modes are resolved by `lib/auth-config.ts`.
User-facing strings must be present in both `messages/en.json` and
`messages/zh-CN.json`.
