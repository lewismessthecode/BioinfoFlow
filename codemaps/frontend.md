# Frontend Codemap

**Last Updated:** 2026-07-11

## Stack And Entrypoints

- Next.js 16 App Router, React 19, TypeScript, Tailwind CSS 4, Radix UI, next-intl, Better Auth, React Flow, and xterm.js.
- `frontend/app/layout.tsx`: root document and providers.
- `frontend/proxy.ts`: auth-aware routing and protected-route redirects.
- `frontend/app/(app)/layout.tsx`: authenticated application shell.
- `frontend/lib/runtime/`: backend request and streaming clients.

## Pages

There are 14 current `page.tsx` route files, including the public landing/demo
and auth routes plus these protected product routes:

| Route | Purpose |
| --- | --- |
| `/dashboard` | readiness, statistics, scheduler summary, and recent activity |
| `/agent`, `/agent/[sessionId]` | AgentCore home and durable session workbench |
| `/workflows`, `/workflows/[id]` | workflow catalog, registration, detail, and run submission |
| `/runs`, `/runs/[runId]` | run list, logs, DAG, audit, notifications, and outputs |
| `/images` | image inventory, pulls, registry selection, and tar imports |
| `/connections` | Remote Connection CRUD, testing, and probes |
| `/scheduler` | queue, pressure, active runs, resources, and advanced details |
| `/settings` | account, appearance, agent, AI providers, container registries, and members |

Top-level navigation definitions live in `frontend/lib/nav-routes.ts`. Settings
sections and role filtering live in `frontend/lib/settings-nav.ts`.

## AgentCore UI

- `components/bioinfoflow/agent-core/agent-core-chat.tsx`: session-level chat entry.
- `components/bioinfoflow/agent-runtime/`: workbench, composer, transcript, approvals, decisions, artifacts, files, progress, browser, and terminal-adjacent panels.
- `hooks/use-agent-core.ts` and `lib/agent-core/`: AgentCore state, API contracts, event handling, and helpers.

The removed legacy `useAgentChat`, `chat-stream`, conversation manager, and
LangGraph-oriented modules are not part of the current frontend architecture.

## Shared UI

- `components/bioinfoflow/sidebar/`: app navigation, projects, sessions, and settings shell.
- `components/bioinfoflow/dag/`: run DAG rendering.
- `components/bioinfoflow/terminal/`: local and remote terminal dock.
- `components/bioinfoflow/settings/`: providers, registries, members, and settings content.
- `components/ui/`: reusable primitives and icon adapter.

## Auth And Localization

Better Auth routes live under `app/api/auth/`; sign-in lives under `app/auth/`.
`personal`, `team`, and `dev` modes are resolved by `lib/auth-config.ts`.
User-facing strings must be present in both `messages/en.json` and
`messages/zh-CN.json`.
