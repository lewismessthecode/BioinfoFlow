# Codebase Modernization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or an equivalent isolated-agent
> workflow. Every phase must be validated and committed before the next phase.

**Goal:** Reduce change friction in Bioinfoflow through behavior-preserving,
reviewable refactors while keeping HTTP, CLI, persisted-data, frontend runtime,
and import compatibility stable.

**Architecture:** Work contract-first. Preserve existing public facades and
wire shapes, move implementation behind smaller focused modules, and delete
code only after static reachability and tests prove that it has no consumer.
This pull request implements the first modernization campaign; larger domain
decompositions remain explicitly sequenced follow-up work.

**Tech Stack:** FastAPI, SQLAlchemy async, Typer, pytest, Ruff, Next.js 16,
React 19, TypeScript, Vitest, Testing Library, Playwright, ESLint, and Knip.

---

## Baseline

Recorded before implementation on 2026-07-11 at
`337c04b3f55d10dc9c7600fa6aa37deccbf01418`:

- Backend uses CPython 3.13.11 and pytest 9.0.2. From `backend/`,
  `rtk uv run pytest` reported `1309 passed, 1 skipped`; `rtk uv run ruff check .`
  passed.
- Frontend uses Bun 1.3.6 and Vitest 4.0.18. From `frontend/`,
  `rtk bun run lint` and `rtk bun run test` passed. The test run emitted
  pre-existing React `act(...)` warnings and jsdom canvas-not-implemented
  warnings.
- From `frontend/`, `rtk bun run lint:dead-code` failed on exactly five unused
  exports.
- From `backend/`, `rtk uv run vulture app --min-confidence 80` reported no
  unused production symbols.

## Compatibility Invariants

The following must not change in this campaign:

- FastAPI remains mounted at `/api/v1`; route paths, methods, operation IDs,
  envelopes, SSE event names, and WebSocket URLs remain stable.
- Typer command names, options, arguments, defaults, output modes, and Click
  exit behavior remain stable.
- `AppRuntime`, `createDemoRuntime()`, `getDemoRuntimeSingleton()`,
  `AgentWorkbench`, `RunService`, `RunCompiler`, `RunLifecycleService`,
  `RunScheduler`, `LlmCatalogService`, `WDLAdapter`, and
  `AgentLoopController` remain public facades.
- Persisted `Run.config` aliases, scheduler compatibility fields, legacy output
  lookup, auth routing, local-storage keys, and frontend event semantics remain
  stable.
- No dependency upgrades, Alembic migrations, framework migrations, or schema
  redesigns are included.

## Campaign Phase Map

| Phase | Current behavior | Structural improvement | Validation gate |
| --- | --- | --- | --- |
| 0 | Compatibility behavior is spread across tests and implementation. | Record the implementation plan and stable behavior contract. | Markdown inspection and staged `rtk git diff --cached --check`. |
| 1 | API and CLI surfaces have strong tests but no deterministic drift artifact. | Add deterministic OpenAPI and Typer command-tree exporters with committed contracts. | Exporters pass in `--check` mode; API/CLI tests and Ruff pass. |
| 2 | Knip reports five exports with no consumers. | Remove only those proven-unused exports. | Knip, frontend lint, and frontend tests pass. |
| 3 | Tests patch three aliases that no longer control production execution. | Patch real collaborators and remove false compatibility aliases. | Focused run/image tests, full backend tests, and Ruff pass. |
| 4 | Three frontend loaders independently implement the same 500 ms minimum duration. | Extract one tested timing helper without changing the duration or loading behavior. | Red/green helper test plus dashboard, workflow, and run-page tests. |
| 5a | Managed-directory policy values are repeated across run and WDL code. | Introduce one focused policy definition without changing recognized keys. | Run compiler/lifecycle, helpers, WDL, and validator tests pass. |
| 5b | Recursive brace-glob expansion is duplicated. | Move the exact algorithm to a focused run helper. | Lifecycle/profile/helper tests pass. |
| 5c | CLI legacy-key detection is duplicated. | Share key detection while retaining caller-specific messages. | CLI run and batch tests pass. |
| 6 | The obsolete `AgentCoreChat` shell remains because the demo imports one useful turn renderer. | Extract the turn renderer, migrate the demo, then delete the unreferenced shell and hook. | Component/demo tests, Knip, lint, build, and optional `/demo` visual check pass. |
| 7 | `ContainerRegistryService` directly loads `Project` despite repository boundaries. | Add/use a repository lookup without changing transaction ownership. | Container registry service/API tests, full backend tests, and Ruff pass. |
| 8 | Three EventSource paths duplicate lifecycle mechanics with intentionally different semantics. | Add a configurable EventSource connection primitive; keep parsing and policy at call sites. | Fake-EventSource characterization tests, lint, full frontend tests, and build pass. |
| 9 | The campaign changes span independent backend/frontend contracts. | Run independent specification, code-quality, and final integration reviews; fix all critical/important findings. | Full backend/frontend verification, contract checks, build, and selected Playwright journeys pass. |

## Phase 0: Plan and Behavior Contract

**Files:**

- Create: `docs/plans/2026-07-11-codebase-modernization.md`
- Create: `docs/contracts/behavior-contracts.md`
- Modify: `.gitignore`

- [ ] Track the plan and contract directory through explicit `.gitignore`
  exceptions.
- [ ] Document the baseline, compatibility invariants, phase boundaries,
  rollback points, and separate migration backlog.
- [ ] Stage the files, then validate from the repository root with
  `rtk git diff --cached --check`.
- [ ] Commit with `docs: plan codebase modernization`.

## Phase 1: Deterministic API and CLI Contracts

**Files:**

- Create: `backend/scripts/export_openapi_contract.py`
- Create: `backend/scripts/export_cli_contract.py`
- Create: `backend/tests/scripts/test_contract_exporters.py`
- Create: `docs/contracts/openapi-v1.json`
- Create: `docs/contracts/cli-v1.json`

- [ ] Write failing exporter tests that require deterministic output and detect
  mismatched committed snapshots.
- [ ] Implement OpenAPI normalization without removing operation IDs or schema
  details.
- [ ] Implement recursive Typer command-tree export covering visible commands,
  parameters, defaults, and required arguments.
- [ ] Generate both committed contract files.
- [ ] From `backend/`, run:

  ```bash
  rtk uv run pytest tests/scripts/test_contract_exporters.py -q
  rtk uv run python scripts/export_openapi_contract.py --check ../docs/contracts/openapi-v1.json
  rtk uv run python scripts/export_cli_contract.py --check ../docs/contracts/cli-v1.json
  rtk uv run pytest tests/test_api tests/test_cli tests/test_schemas.py -q
  rtk uv run ruff check .
  rtk uv run pytest
  ```

- [ ] Commit with `test: capture api and cli behavior contracts`.

## Phase 2: Proven Frontend Dead Exports

**Files:**

- Modify: `frontend/components/bioinfoflow/agent-runtime/universal-file-renderer.tsx`
- Modify: `frontend/components/bioinfoflow/terminal/terminal-dock-context.tsx`
- Modify: `frontend/components/ui/card.tsx`

- [ ] Use the existing failing Knip output as the red check.
- [ ] Remove `fileKindLabel`, `useOptionalTerminalDock`, `CardHeader`,
  `CardTitle`, and `CardDescription` exports/definitions only.
- [ ] From `frontend/`, run `rtk bun run lint:dead-code`,
  `rtk bun run lint`, and `rtk bun run test`.
- [ ] Commit with `refactor: remove unused frontend exports`.

## Phase 3: False Backend Test Seams

**Files:**

- Modify: `backend/app/services/run_service.py`
- Modify: `backend/app/runtime/jobs.py`
- Modify: `backend/app/services/image_service.py`
- Modify: `backend/tests/test_services/test_run_service.py`
- Modify: `backend/tests/test_services/test_batch.py`
- Modify: `backend/tests/test_api/test_runs.py`
- Modify: `backend/tests/test_api/test_run_lifecycle.py`
- Modify: `backend/tests/test_api/test_batch_api.py`
- Modify: `backend/tests/test_api/test_images.py`
- Modify affected runtime recovery tests that patch
  `runtime_jobs.async_session_maker`.

- [ ] Add or adjust seam tests so they fail when tests patch an ineffective
  alias rather than the real injected collaborator.
- [ ] Remove patches of `run_service.task_runner` and
  `runtime_jobs.async_session_maker` where they do not influence production.
- [ ] Patch `image_service.background_tasks` directly where isolation is
  required.
- [ ] Delete `run_service.task_runner`, `runtime_jobs.async_session_maker`, and
  `image_service.task_runner` after repository-wide import checks.
- [ ] From `backend/`, run:

  ```bash
  rtk uv run pytest tests/test_services/test_phase0_seams.py tests/test_services/test_run_service.py tests/test_services/test_batch.py tests/test_api/test_runs.py tests/test_api/test_run_lifecycle.py tests/test_api/test_batch_api.py tests/test_api/test_images.py tests/test_runtime/test_run_recovery.py -q
  rtk uv run ruff check .
  rtk uv run pytest
  ```

- [ ] Commit with `refactor: remove obsolete backend test seams`.

## Phase 4: Shared Minimum-Duration Helper

**Files:**

- Create: `frontend/lib/minimum-duration.ts`
- Create: `frontend/tests/unit/lib/minimum-duration.test.ts`
- Modify: `frontend/app/(app)/dashboard/page.tsx`
- Modify: `frontend/app/(app)/workflows/page.tsx`
- Modify: `frontend/app/(app)/runs/use-runs-page.ts`

- [ ] Write fake-timer tests for fast success, slow success, immediate rejection
  with the original error, and the unchanged 500 ms minimum.
- [ ] Extract a helper used by all three callers without changing their loading
  or error semantics.
- [ ] From `frontend/`, run:

  ```bash
  rtk bun run test tests/unit/lib/minimum-duration.test.ts tests/integration/pages/dashboard-page.test.tsx tests/integration/pages/workflows-page-hub.test.tsx tests/integration/pages/workflows-page-project.test.tsx tests/integration/pages/workflows-page-scope.test.tsx tests/unit/hooks/use-runs-page.test.tsx
  rtk bun run lint
  rtk bun run test
  ```

- [ ] Commit with `refactor: share minimum loading duration`.

## Phase 5a: Managed-Directory Policy

**Files:**

- Create: `backend/app/services/run_input_policy.py`
- Modify: `backend/app/services/run_compiler.py`
- Modify: `backend/app/services/run_lifecycle_service.py`
- Modify: `backend/app/services/run_helpers.py`
- Modify: `backend/app/engine/adapters/wdl.py`
- Modify: `backend/app/engine/schema_extractor.py`
- Modify: `backend/app/services/validators/types.py`
- Modify focused run/WDL tests.

- [ ] Characterize the exact managed-directory key set and each caller's
  filtering behavior.
- [ ] Move only the shared key policy; keep engine-specific behavior at callers.
- [ ] From `backend/`, run:

  ```bash
  rtk uv run pytest tests/test_services/test_run_input_policy.py tests/test_services/test_run_compiler.py tests/test_services/test_run_lifecycle_service.py tests/test_services/test_run_helpers.py tests/test_engine/test_wdl_adapter.py tests/test_engine/test_schema_extractor.py tests/test_services/test_workflow_validator.py -q
  rtk uv run ruff check .
  rtk uv run pytest
  ```

- [ ] Commit with `refactor: centralize managed run directories`.

## Phase 5b: Shared Brace-Glob Expansion

**Files:**

- Modify: `backend/app/services/run_helpers.py`
- Modify: `backend/app/services/run_lifecycle_service.py`
- Modify: `backend/app/services/run_profile_service.py`
- Modify focused helper/lifecycle/profile tests.

- [ ] Add characterization tests for nested braces, multiple choices, malformed
  input, and patterns without braces.
- [ ] Move the exact recursive algorithm to `run_helpers.py` and delegate both
  callers.
- [ ] From `backend/`, run:

  ```bash
  rtk uv run pytest tests/test_services/test_run_helpers.py tests/test_services/test_run_lifecycle_service.py tests/test_services/test_run_profile_service.py -q
  rtk uv run ruff check .
  rtk uv run pytest
  ```

- [ ] Commit with `refactor: share brace glob expansion`.

## Phase 5c: Shared CLI Legacy-Key Detection

**Files:**

- Create: `backend/app/cli/run_spec.py`
- Modify: `backend/app/cli/commands/run.py`
- Modify: `backend/app/cli/commands/run_batch.py`
- Modify: `backend/tests/test_cli/test_cli_runs.py`

- [ ] Add tests proving identical key detection and unchanged single/batch error
  messages and exit code 2.
- [ ] Share only detection/constants; keep caller-specific message formatting.
- [ ] From `backend/`, run:

  ```bash
  rtk uv run pytest tests/test_cli/test_cli_runs.py -q
  rtk uv run ruff check .
  rtk uv run pytest
  ```

- [ ] Commit with `refactor: share legacy run key detection`.

## Phase 6: Retire the Obsolete Agent Chat Shell

**Files:**

- Create: `frontend/components/bioinfoflow/agent-core/agent-core-turn-block.tsx`
- Create: `frontend/tests/unit/components/agent-core-turn-block.test.tsx`
- Modify: `frontend/app/(demo)/demo/page.tsx`
- Delete, after reachability proof: obsolete chat shell/hook files and their
  shell-only tests.

- [ ] Move `AgentCoreTurnBlock` and its rendering helpers without changing its
  props or demo output.
- [ ] Migrate demo and focused tests to the new module.
- [ ] Confirm production has no remaining `AgentCoreChat` or old-hook consumer.
- [ ] Delete only unreachable shell code; keep shared AgentCore types/session
  APIs still used by sidebar, command palette, storage, and demo data.
- [ ] From `frontend/`, run:

  ```bash
  rtk bun run test tests/unit/components/agent-core-turn-block.test.tsx tests/unit/lib/demo/replay-engine.test.ts tests/unit/lib/runtime/demo-runtime.test.ts
  rtk bun run lint:dead-code
  rtk bun run lint
  rtk bun run test
  rtk bun run build
  ```

- [ ] Because the change touches `frontend/app/(demo)/demo/page.tsx`, run the
  local frontend and inspect `/demo` with the browser. Authentication bypass is
  not required for the public demo route; there is no dedicated Playwright demo
  spec in this repository.
- [ ] Commit extraction first. Delete the shell in a second commit only after
  the extracted renderer is green, so either commit is an independent rollback
  unit.

## Phase 7: Repository Boundary Repair

**Files:**

- Modify: `backend/app/repositories/project_repo.py`
- Modify: `backend/app/services/container_registry_service.py`
- Modify/add focused repository and service tests.

- [ ] Write a failing service test that requires project lookup through the
  repository collaborator.
- [ ] Add the narrow repository method and replace direct `session.get(Project)`.
- [ ] Keep commit/rollback behavior unchanged; unit-of-work redesign is out of
  scope.
- [ ] From `backend/`, run:

  ```bash
  rtk uv run pytest tests/test_services/test_container_registry_service.py tests/test_api/test_container_registries.py -q
  rtk uv run ruff check .
  rtk uv run pytest
  ```

- [ ] Commit with `refactor: route registry project access through repository`.

## Phase 8: Shared EventSource Lifecycle

**Files:**

- Create: `frontend/lib/runtime/event-source-connection.ts`
- Add/expand fake-EventSource tests for live runtime, AgentCore stream, and
  resource stream.
- Modify: `frontend/lib/runtime/live-runtime.ts`
- Modify: `frontend/lib/agent-runtime/event-stream.ts`
- Modify: `frontend/hooks/use-resource-stream.ts`

- [ ] Characterize exact URL, credentials, named/default event binding, cursor,
  reconnect predicate, source-closing policy, timer sequence, maximum backoff,
  invalid JSON handling, and cleanup for each consumer.
- [ ] Implement a configurable lifecycle primitive containing no domain parsing.
- [ ] Migrate one consumer at a time and keep all characterization tests green.
- [ ] From `frontend/`, run:

  ```bash
  rtk bun run test tests/unit/hooks/use-events.test.ts tests/unit/hooks/use-resource-stream.test.ts tests/unit/lib/agent-runtime/event-stream.test.ts
  rtk bun run lint
  rtk bun run lint:dead-code
  rtk bun run test
  rtk bun run build
  ```

- [ ] Commit with `refactor: share event source lifecycle`.

## Phase 9: Review, Integration, and PR

- [ ] Spawn independent backend, frontend, and contract reviewers against the
  complete Git range.
- [ ] Fix every Critical and Important finding and request re-review.
- [ ] From `backend/`, run:

  ```bash
  rtk uv run python scripts/export_openapi_contract.py --check ../docs/contracts/openapi-v1.json
  rtk uv run python scripts/export_cli_contract.py --check ../docs/contracts/cli-v1.json
  rtk uv run ruff check .
  rtk uv run pytest
  ```

- [ ] From `frontend/`, run:

  ```bash
  rtk bun run lint
  rtk bun run lint:i18n
  rtk bun run lint:dead-code
  rtk bun run test
  rtk bun run build
  ```

- [ ] When protected frontend/runtime files changed, from `frontend/` run:

  ```bash
  rtk bunx playwright test tests/e2e/core-navigation.spec.ts tests/e2e/agent-first-analysis.spec.ts tests/e2e/run-lifecycle.spec.ts
  ```

  The existing Playwright setup uses `AUTH_MODE=dev`.
- [ ] Phase 6 has no dedicated Playwright demo spec. When demo rendering files
  changed, perform the explicit `/demo` visual inspection required by Phase 6
  rather than referring to a nonexistent automated journey.
- [ ] Fetch and rebase on `origin/main`.
- [ ] After the rebase, rerun the exact complete backend, frontend, build,
  Playwright, and manual demo gates above before pushing.
- [ ] Push and open a draft or ready PR with a Conventional Commit title.

## Rollback Units

- Every phase commit is independently revertible and must leave the full
  applicable verification gate green.
- Generated OpenAPI/CLI contracts are committed with their exporter code; revert
  both together rather than regenerating from a partially reverted tree.
- Phase 6 extraction is committed before deletion. If migration fails, the demo
  can temporarily import the compatibility re-export while the extracted
  component remains available.
- Phase 8 migrates consumers one at a time in one phase commit only after all
  three characterization suites are green; if partial work fails, restore the
  original consumer implementation before committing.
- Rebase conflicts are resolved before the final complete gate. No push occurs
  from a partially verified rebase.

## Follow-up Refactor Program

These are intentionally separate follow-up plans/PRs after this campaign:

1. Split the 1,087-line Agent API router behind the same `/agent` router.
2. Split LLM provider/credential/model/profile/discovery collaborators behind
   `LlmCatalogService`.
3. Split WDL schema/dependency and output materialization behind `WDLAdapter`.
4. Split RunCompiler and RunLifecycleService after golden compile/replay fixtures.
5. Split RunScheduler after a lease/state-transition matrix and repeated race
   tests.
6. Split AgentLoopController after golden event-sequence fixtures.
7. Decompose AgentWorkbench, UniversalFileRenderer, settings presentation,
   transcript segments, and demo runtime behind their stable exports.

## Separate Migration Backlog

Do not hide these inside behavior-preserving refactors:

- Framework or dependency upgrades/pinning.
- API response-model, route, operation-ID, event, or CLI changes.
- Database/Alembic or persisted `Run.config` normalization.
- Unit-of-work transaction redesign.
- Removal of Nextflow/MiniWDL/validator/import compatibility modules.
- Scheduler legacy mode or `max_concurrency` removal.
- AgentCore legacy/current type and client unification.
- Authentication, local-storage key, retry-policy, execution-backend, or UX
  timing changes.
