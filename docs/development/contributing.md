# Development Guide

## Repo Structure

- `backend/`: FastAPI API, scheduler, engine abstraction, agent runtime, models, migrations, tests
- `frontend/`: Next.js app, UI components, hooks, frontend tests
- `codemaps/`: implementation-aware architecture maps
- `docs/`: current documentation plus archive/history

## Common Commands

Backend:

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run ruff check .
uv run ruff format .
uv run pytest
```

Frontend:

```bash
cd frontend
bun install
bun run lint
bun run test
bun run test:coverage
```

## Testing Expectations

- Backend test coverage is concentrated in scheduler, engine, run lifecycle, and agent runtime suites.
- Frontend uses Vitest for unit/integration and Playwright for e2e coverage.
- Frontend coverage threshold is 80%.
- Prefer targeted tests for the touched subsystem before running full suites.

## Conventions

- API responses should follow the standard envelope unless the endpoint is explicitly stream/binary/raw.
- Agent tools should use the `BaseTool` abstraction plus `@register_tool`.
- Run execution changes should preserve the refactor-v3 seam:
  - `RunService` handles request/lifecycle rules
  - `RunScheduler` owns queue/retry/timeout/recovery/hooks
  - `ExecutionBackend` owns process execution
  - `EngineAdapter` owns engine-specific semantics
- Frontend routes, hooks, and types should stay aligned with backend contract changes.

## Documentation Maintenance

- Keep implementation docs factual; do not leave roadmap claims in active docs.
- Update docs in the same change that modifies the behavior they describe.
- Keep `docs/plans/` for active implementation plans only.
- Archive completed or superseded plans under `docs/archive/<date>-<label>/` instead of deleting them.
- Preserve archived docs when performing major rewrites so implementation history stays traceable.
