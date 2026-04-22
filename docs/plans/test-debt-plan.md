# Test Debt Plan

**Created:** 2026-03-30
**Source:** Pruning report (`docs/reviews/prune-2026-03-30.md`)

## Current State

| Area | Source Files | Test Files | Coverage |
|------|-------------|------------|----------|
| Backend services | 23 | 12 | 52% |
| Backend API routes | 15 | 17 | Good (stats, notifications missing) |
| Frontend components | 47 | 7 unit + 5 integration | 26% |
| E2E flows | — | 0 | 0% |

## Priority 1: Backend Services (Critical Paths)

These services handle core functionality and have NO dedicated tests:

| Service | Lines | Risk | Why |
|---------|-------|------|-----|
| `file_service.py` | 8.6K | HIGH | File upload/download/management — data loss risk |
| `docker_service.py` | 5.6K | HIGH | Container lifecycle — can leak resources |
| `image_service.py` | 9.8K | HIGH | Docker image management — runtime errors |
| `run_dispatch.py` | 3.2K | HIGH | Run dispatching — affects all workflow execution |
| `run_archive.py` | 8.5K | MEDIUM | Run archival — data preservation |
| `run_helpers.py` | 11.3K | MEDIUM | Shared helpers — widely imported |
| `workflow_service.py` | 6.3K | MEDIUM | Workflow CRUD — tested via API tests partially |
| `project_workflow_service.py` | 7.6K | MEDIUM | Project-workflow bindings |
| `gpu_service.py` | 12.4K | LOW | GPU detection — environment-dependent |
| `project_service.py` | 1.5K | LOW | Simple CRUD — thin wrapper |
| `trace_parser.py` | 5.4K | LOW | Trace file parsing — read-only |
| `nextflow_service.py` | 3.1K | LOW | Nextflow integration — environment-dependent |
| `miniwdl_service.py` | 2.6K | LOW | MiniWDL integration — environment-dependent |

**Approach:** Start with HIGH risk services. Use the existing test patterns:
- `pytest` + `pytest-asyncio`
- `db_session` fixture from `conftest.py` (per-test in-memory SQLite)
- `async_client` for any API-adjacent testing
- Mock external dependencies (Docker SDK, filesystem) where needed

## Priority 2: Missing API Route Tests

| Route | Risk | Note |
|-------|------|------|
| `stats.py` | LOW | Aggregate queries, read-only |
| `notifications.py` | LOW | Service tested, but API layer untested |
| `events.py` | MEDIUM | SSE endpoint — needs async client test |

## Priority 3: Frontend Components

### Unit tests needed (high-impact components):

| Component | Why |
|-----------|-----|
| `chat-stream.tsx` | Core agent interaction UI |
| `command-palette.tsx` | User navigation — keyboard shortcuts |
| `sidebar/*.tsx` (6 files) | Primary navigation — affects every page |
| `navbar.tsx` | Global nav |
| `create-project-dialog.tsx` | User onboarding flow |
| `demo-dialog.tsx` | Demo flow entry point |
| `monitor-panel.tsx` | Run monitoring |
| `terminal/*.tsx` (3 files) | Terminal integration |

### Already tested (good):
- `background-card.tsx`, `dag-edge.tsx`, `dag-node.tsx`, `markdown-renderer.tsx`, `task-card.tsx`, `todo-card.tsx`, `workflow-cards`

### Low priority (simple/presentation-only):
- `logo.tsx`, `breadcrumbs.tsx`, `connection-status.tsx`, `onboarding-tooltip.tsx`, `thinking-block.tsx`

## Priority 4: E2E Tests

No E2E tests exist. Critical user flows that need coverage:

1. **Create project → Register workflow → Launch run → View results**
2. **Agent conversation → Tool execution → Approval workflow**
3. **Image pull → Workflow binding → Run with container**

**Suggested tool:** Playwright (already common in Next.js ecosystem)

## Execution Plan

| Sprint | Scope | Est. effort |
|--------|-------|-------------|
| 1 | Backend: file_service, docker_service, image_service, run_dispatch | 1 day |
| 2 | Backend: run_archive, run_helpers, workflow_service, project_workflow_service | 1 day |
| 3 | API: stats, notifications, events | 0.5 day |
| 4 | Frontend: chat-stream, command-palette, sidebar, create-project-dialog | 1 day |
| 5 | Frontend: remaining high-impact components | 1 day |
| 6 | E2E: set up Playwright, write critical path tests | 2 days |

## Conventions Reminder

- Backend: use `db_session` and `async_client` from `conftest.py`
- Frontend: use `renderAppPage()` from `tests/app-test-utils.tsx`
- Never share `appTestState` across tests
- 80% coverage threshold (enforced in frontend via `@vitest/coverage-v8`)
- TDD: write failing test first, then implement
