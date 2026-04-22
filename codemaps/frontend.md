# Frontend Codemap
<!-- Generated: 2026-04-17 | Files scanned: 294 | Token estimate: ~950 -->
**Last Updated:** 2026-04-17
**Entry Points:** `frontend/app/layout.tsx`, `frontend/app/(app)/layout.tsx`, `frontend/app/page.tsx`, `frontend/app/api/auth/[...all]/route.ts`, `frontend/middleware.ts`

## Architecture
```
Next.js App Router + next-intl (en, zh-CN)
   │
   ├─ Landing pages (marketing, 13 sections)
   ├─ App routes (dashboard, agent, runs, run detail, workflows, images, scheduler, settings)
   ├─ Demo route (guided tour)
   ├─ Auth API routes (Better Auth)
   └─ Middleware (cookie-based locale detection)

Client data flow:
UI → apiRequest (lib/api.ts) → FastAPI
UI → useEvents (SSE) → EventBus
UI → useAgentChat → message aggregation + commands
UI → useTerminalSession (WebSocket) → Terminal service
UI → useSidebarData / useLlmSettings → project + preferences state
```

## Routes (12 pages)
| Route | File | Notes |
| --- | --- | --- |
| `/` | `app/page.tsx` | Marketing landing page |
| `/auth` | `app/auth/page.tsx` | Auth UI (personal/team mode) |
| `/demo` | `app/(demo)/demo/page.tsx` | Guided demo experience |
| `/dashboard` | `app/(app)/dashboard/page.tsx` | Project/run statistics |
| `/agent` | `app/(app)/agent/page.tsx` | Agent chat + live deck |
| `/images` | `app/(app)/images/page.tsx` | Image inventory |
| `/runs` | `app/(app)/runs/page.tsx` | Run list + batch ops |
| `/runs/[runId]` | `app/(app)/runs/[runId]/page.tsx` | Run detail (logs, DAG, outputs, audit) |
| `/workflows` | `app/(app)/workflows/page.tsx` | Workflow catalog |
| `/workflows/[id]` | `app/(app)/workflows/[id]/page.tsx` | Workflow detail (params, tasks, source) |
| `/scheduler` | `app/(app)/scheduler/page.tsx` | Scheduler dashboard (queue, resources, slots) |
| `/settings` | `app/(app)/settings/page.tsx` | User preferences (LLM provider, model, storage) |

## Component Structure
```
components/
├── bioinfoflow/                      # Main app
│   ├── card/                         # CardBase, index
│   ├── chat/                         # ChatInput, MessageList, WelcomeScreen, QuickStartCards, ScrollToBottom, TypingIndicator
│   ├── dag/                          # DagPanel, DagNode, DagEdge, DagBackground, DagNodeDetail
│   ├── sidebar/                      # Sidebar, SidebarDrawer, ProjectSwitcher, ConversationList, ConversationItem, SidebarActions
│   ├── settings/                     # Settings subpanels (LLM, storage, profile)
│   ├── terminal/                     # TerminalDock, TerminalDockContext (xterm.js + WebSocket)
│   ├── breadcrumbs.tsx + breadcrumb-context.tsx
│   ├── chat-stream.tsx               # Main chat orchestrator
│   ├── command-palette.tsx           # Cmd+K palette
│   ├── connection-status.tsx         # Online/offline + SSE health
│   ├── create-project-dialog.tsx     # Project creation with storage mode
│   ├── directory-browser.tsx         # Host directory picker
│   ├── file-browser-dialog.tsx       # File selection dialog
│   ├── live-deck.tsx                 # Right panel (workspace/DAG/monitor tabs)
│   ├── logo.tsx
│   ├── markdown-renderer.tsx         # Markdown + syntax highlighting
│   ├── monitor-panel.tsx             # Live metrics/resources panel
│   ├── navbar.tsx                    # Top navigation
│   ├── project-context.tsx           # React Context for project state
│   ├── user-menu.tsx                 # Auth + profile menu
│   ├── welcome-card.tsx              # Onboarding card
│   ├── workspace-panel.tsx           # File browser
│   └── workspace-shell-context.tsx   # Shell/workspace coordination
├── landing/                          # Marketing sections (13 files)
├── ui/                               # Radix UI primitives (30 files)
└── auth/                             # Auth components (2 files)
```

## Key Modules
| Module | Purpose | Exports |
| --- | --- | --- |
| `lib/api.ts` | API helper + envelope parsing | `apiRequest`, `ApiError` |
| `lib/auth.ts` | Better Auth server | auth instance |
| `lib/auth-client.ts` | Better Auth client | `authClient` |
| `lib/auth-config.ts` | Auth mode/viewer config | `ViewerIdentity`, `buildAnonymousViewer` |
| `lib/auth-admin-guards.ts` | Route-level admin guards | guard helpers |
| `lib/auth-bootstrap.ts` | First-run auth setup | bootstrap helpers |
| `lib/types.ts` | TypeScript type definitions | all domain types |
| `lib/chat-utils.ts` + `chat-types.ts` | Message transform/parse | `mapAgentEvent`, `mapAgentMessage` |
| `lib/conversations.ts` + `recent-conversations.ts` | Local conversation storage + recency | helpers |
| `lib/conversation-export.ts` | Export transcripts | export helpers |
| `lib/format-utils.ts` | Date/duration/size formatting | formatters |
| `lib/schema-resolver.ts` | Workflow parameter schema resolution | `resolveSchema` |
| `lib/workflow-groups.ts` + `workflow-source-diff.ts` | Workflow organization + diff views | helpers |
| `lib/cookies.ts` | Cookie utilities | locale helpers |
| `lib/nav-routes.ts` | Navigation route definitions | route config |
| `lib/time-greeting.ts` | Time-based greeting | helper |
| `lib/demo/` | Demo-specific helpers | demo assets |
| `hooks/use-events.ts` | SSE subscription + reconnect | `useEvents` |
| `hooks/use-agent-chat.ts` | Chat state + commands | `useAgentChat` |
| `hooks/use-chat-scroll.ts` | Auto-scroll + user-scrolled detection | `useChatScroll` |
| `hooks/use-sidebar-data.ts` | Projects/conversations | `useSidebarData` |
| `hooks/use-terminal-session.ts` | Terminal WebSocket | `useTerminalSession` |
| `hooks/use-llm-settings.ts` | LLM provider/model prefs | `useLlmSettings` |
| `hooks/use-dag-positions.ts` | DAG node persistence | `useDagPositions` |
| `hooks/use-viewport-fit-height.ts` | Dynamic viewport height | `useViewportFitHeight` |
| `hooks/use-media-query.ts` | Responsive breakpoints | `useIsMobile` |
| `hooks/use-set-breadcrumb-detail.ts` | Page-level breadcrumb detail | `useSetBreadcrumbDetail` |

## i18n
- **Framework:** next-intl with cookie-based locale detection
- **Locales:** `en`, `zh-CN` (configured in `i18n/config.ts`)
- **Messages:** `messages/en.json`, `messages/zh-CN.json` (33 namespaces)
- **Middleware:** `middleware.ts` resolves locale from cookie → Accept-Language → default
- **Rule:** every new UI string must land in both files in the same commit.

## Tests
- **Unit:** Vitest + Testing Library (jsdom) — `tests/unit/`
- **Integration:** Vitest — `tests/integration/`
- **Smoke:** Vitest — `tests/smoke/`
- **App helper:** `renderAppPage` returns `{ ...renderResult, appTestState }` — never cache `appTestState` across tests.
- **Coverage:** 80% enforced via `@vitest/coverage-v8`

## External Dependencies
- Next.js 16, React 19, Radix UI
- Better Auth (v1.4.17)
- React Flow (DAG), Framer Motion
- Tailwind CSS 4, next-intl
- xterm.js 6 (terminal emulator)

## Related Areas
- [Architecture Codemap](architecture.md)
- [Backend Codemap](backend.md)
