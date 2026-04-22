# Frontend Overview

## Stack

- Next.js 16 App Router
- React 19 + TypeScript
- next-intl for `en` and `zh-CN`
- Better Auth for frontend auth routes
- Tailwind CSS 4, Radix UI, React Flow, Framer Motion
- SSE through browser `EventSource`

## Route Map

- `/`: marketing landing page
- `/auth`: auth UI
- `/dashboard`: project and run stats
- `/agent`: conversational workspace
- `/images`: image inventory and pull/load flows
- `/runs`: run list
- `/runs/[runId]`: run detail, DAG, outputs, audit, notifications, batch context
- `/workflows`: workflow catalog
- `/workflows/[id]`: workflow detail and registration/run dialogs
- `/scheduler`: scheduler health dashboard

## App Shell

Shared `(app)` layout provides:

- `ProjectProvider` for active project/conversation state
- desktop sidebar plus mobile drawer
- top navbar
- keyboard shortcuts such as `Cmd/Ctrl+K` and sidebar toggles
- command palette and global toaster

The agent page adds a second resizable right panel (`LiveDeck`) for workspace, DAG, and monitor views.

## Client Data Flow

- `frontend/lib/api.ts` builds backend URLs, applies the envelope contract, and throws typed `ApiError`s.
- `useSidebarData` loads projects and conversations for the shell.
- `useChatStream` owns conversation restore, slash commands, optimistic user messages, demo prompts, cancellation, and SSE merge/dedup logic.
- `useDagPositions` persists local DAG layout state in `localStorage`.

## Realtime Model

`useEvents` subscribes to `/events/stream` with:

- required `project_id`
- optional `conversation_id`, `run_id`, `image_id`
- reconnect backoff from 1s up to 30s

Bound event names:

- `run.status`
- `run.log`
- `run.dag`
- `image.progress`
- `agent.thinking`
- `agent.plan`
- `agent.artifact`
- `agent.message`
- `agent.done`
- `agent.cancelled`

## Auth And i18n

- Better Auth is wired through `app/api/auth/[...all]/route.ts`.
- Locale selection flows through `frontend/middleware.ts` using cookie first, then `Accept-Language`, then default fallback.
- Backend APIs are not yet protected by frontend auth state, so auth currently improves frontend UX more than backend isolation.

## Testing And Build Notes

- Unit/integration coverage uses Vitest + Testing Library.
- E2E coverage uses Playwright.
- Coverage threshold is 80% via `@vitest/coverage-v8`.
- Frontend commands live in `frontend/package.json`: `dev`, `build`, `lint`, `test`, `test:coverage`.
