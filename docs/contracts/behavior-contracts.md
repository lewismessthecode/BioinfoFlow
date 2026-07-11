# Behavior Contracts for Refactoring

This document identifies Bioinfoflow behavior that modernization work must keep
stable. It is a refactoring contract, not a promise that every historical
compatibility path will exist forever; removals require a separate migration.

## HTTP API

- The FastAPI application is mounted at `/api/v1`.
- Interactive docs remain at `/api/v1/docs` and OpenAPI remains at
  `/api/v1/openapi.json`.
- Existing paths, HTTP methods, operation IDs, query/body names, aliases,
  status codes, and response envelopes remain stable.
- Successful responses use the existing `data` and optional `meta` envelope.
- Error responses retain the existing error code, message, details, request ID,
  and status behavior.
- AgentCore SSE, general event SSE, scheduler resource streams, and WebSocket
  paths retain their existing event names and frame shapes.

OpenAPI does not currently describe every response payload because routes do
not consistently declare `response_model`. Characterization tests remain the
authority for envelope and stream payload details.

Authoritative characterization coverage includes:

- `backend/tests/test_api/test_system_envelope.py`
- `backend/tests/test_api/test_errors.py`
- `backend/tests/test_api/test_scheduler_api.py`
- `backend/tests/test_api/test_events.py`
- `backend/tests/test_api/test_agent_core_api.py`

## CLI

- The public executable remains `bif`.
- Root command names, nested command names, options, aliases, arguments,
  defaults, and visible help remain stable.
- `--base-url`, project resolution, output mode, quiet/verbose behavior, and
  `NO_COLOR` handling remain stable.
- `handle_errors` continues to re-raise Click exceptions so usage errors exit
  with code 2.
- Single and batch run commands continue rejecting deprecated flat run keys
  with their current caller-specific messages.
- Deprecated config key `mode` continues to be discarded during config load.

Authoritative CLI coverage includes `backend/tests/test_cli/test_cli_smoke.py`,
`test_cli_config.py`, `test_cli_errors.py`, and `test_cli_runs.py`. The command
tree snapshot complements these tests; it does not replace output/error tests.

## Frontend Routes and Runtime

- Protected application routes remain under `frontend/app/(app)/`; auth routes
  remain under `frontend/app/auth/`.
- Root, demo, protected-layout, and auth redirect behavior remain stable.
- `AppRuntime` remains the live/demo transport facade with the existing request,
  API URL, WebSocket URL, and subscription signatures.
- `createDemoRuntime()` and `getDemoRuntimeSingleton()` remain stable exports.
- General live events retain credential use, named event bindings, reconnect
  behavior, and cleanup semantics.
- AgentCore event streaming retains its `after_seq` cursor behavior and its
  existing reconnect policy.
- Resource streaming retains its current credential and CLOSED-state behavior.
- Existing local-storage keys and build-time `NEXT_PUBLIC_*` behavior remain
  stable.

Authoritative frontend route/runtime coverage includes:

- `frontend/tests/unit/root-page.test.tsx`
- `frontend/tests/unit/protected-layout.test.tsx`
- `frontend/tests/unit/lib/nav-routes.test.ts`
- `frontend/tests/unit/hooks/use-events.test.ts`
- `frontend/tests/unit/lib/agent-runtime/event-stream.test.ts`
- EventSource characterization tests added by Phase 8.

## Runs and Workflow Execution

- `RunService` remains a thin facade over focused run services.
- `RunCompiler`, `RunLifecycleService`, `RunScheduler`, `WDLAdapter`, and the
  Nextflow adapter retain their public methods and behavior.
- Persisted versioned and flat legacy `Run.config` keys remain readable.
- Legacy configured output-directory lookup remains read-only compatibility;
  destructive cleanup stays limited to the canonical run layout.
- `BIOINFOFLOW_HOME` retains the identity-mount path invariant.
- WDL `glob()` handling remains relative to task working directories.
- Resume, retry, idempotency, lease, cancellation, timeout, and terminal-state
  ordering remain stable.

Authoritative coverage includes run compiler, lifecycle, service, API, archive,
engine, scheduler, migration, and model-invariant tests under `backend/tests/`.

## Scheduler

- Scheduler status retains compatibility fields including `run_id`, `weight`,
  and configured/effective concurrency information.
- Legacy fallback response/stream behavior remains unchanged.
- Compare-and-swap lease predicates and execution-attempt checks must not be
  weakened by extraction.

## AgentCore

- Session, turn, action, artifact, memory, skill, toolset, and stream routes
  retain their paths and wire shapes.
- `AgentLoopController.run_turn`, resume behavior, tool approvals, interaction
  waits, event ordering, token usage, prompt/model snapshots, and lease renewal
  remain stable.
- Tool names, schemas, risk levels, permission behavior, and artifact policies
  remain stable.
- Frontend `AgentWorkbench` remains the canonical production interface.
- Shared AgentCore types and session APIs used outside the obsolete chat shell
  remain supported.

Authoritative coverage includes `backend/tests/test_agent_core/`,
`backend/tests/test_api/test_agent_core_api.py`, and the frontend AgentWorkbench,
runtime reducer, transcript, and stream suites.

## Compatibility Imports

Compatibility wrappers and re-exports are not dead code merely because the
current production path delegates elsewhere. Their removal requires an explicit
import migration and reachability proof. Examples include:

- Nextflow and MiniWDL service wrappers.
- Workflow validator re-exports/delegates.
- Run service and runtime compatibility imports that still have real consumers.
- CLI client type re-exports.
- Request/schema aliases such as AgentCore `kind`, run `error_json`, workflow
  `schema_json`, and LLM `provider_metadata`.

Test-only aliases that do not influence production execution may be removed only
after tests patch the real collaborator and the full suite remains green.

## Verification Layers

Use the narrowest relevant layer while iterating, then the broader gate before
committing a phase:

```text
backend focused tests -> backend full pytest + Ruff
frontend focused tests -> lint + Knip + full Vitest + build
wire/import changes -> deterministic API/CLI contracts
visual layout changes -> Playwright or local AUTH_MODE=dev review
docs only -> Markdown inspection + git diff --check
```

The following require separate migration plans rather than ordinary refactors:

- Dependency or framework upgrades.
- HTTP, CLI, SSE, WebSocket, or persisted-data changes.
- Database migrations and transaction/unit-of-work redesign.
- Removal of compatibility wrappers or aliases with external consumers.
- Retry-policy, scheduler-mode, auth, execution-backend, or user-visible UX
  changes.
