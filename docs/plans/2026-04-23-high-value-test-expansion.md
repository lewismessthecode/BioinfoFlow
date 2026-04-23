# High-Value Test Expansion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Raise confidence on the highest-value user journeys by adding targeted E2E, frontend unit/integration, and backend service tests, while fixing any real product defects those tests expose.

**Architecture:** Extend the current Playwright and Vitest suites around real project/workflow/run/provider flows instead of broad low-signal coverage. Follow TDD for each batch: add a focused failing test, confirm the failure is real, fix product code only when needed, then re-run the narrow suite before moving on.

**Tech Stack:** Playwright, Vitest, Testing Library, FastAPI pytest, async Python services, Next.js App Router, React 19.

## Progress Update

- Completed and committed:
  - High-value E2E for workspace project creation, workflow registration + run, run detail, and provider settings
  - Frontend hook/unit/integration coverage for runs, images, chat subcomponents, provider card, DAG affordances, workspace shell, settings flow, app layout coordination, and agent project-selection flow
  - Backend regression coverage for successful-run cleanup/log persistence fixes
  - Backend wrapper coverage for GPU, btop, Nextflow, and miniwdl compatibility services
- Real issues already found and fixed:
  - Successful runs were being cleaned up immediately, breaking run-detail main paths
  - Structured engine events were not persisted into `run.log`, leaving successful runs with empty logs
- Remaining high-value work after the original batches:
  - Agent first-analysis E2E
  - Workflow registration coverage for `nf-core` and GitHub sources through the real UI
  - Agent-driven workflow main paths and capability-boundary coverage around natural-language configure / generate / register / run behavior

### Task 1: Inventory-driven E2E expansion

**Files:**
- Modify: `frontend/tests/e2e/pages/app-nav.ts`
- Modify: `frontend/tests/e2e/pages/runs-page.ts`
- Modify: `frontend/tests/e2e/pages/workflows-page.ts`
- Create: `frontend/tests/e2e/pages/sidebar.ts`
- Create: `frontend/tests/e2e/workspace-project-flow.spec.ts`
- Create: `frontend/tests/e2e/workflow-run-path.spec.ts`
- Possibly modify: `frontend/tests/e2e/support/start-backend.mjs`
- Possibly modify: `frontend/tests/e2e/support/*.ts`

**Step 1: Write the failing workspace/project E2E**

Add a browser test that starts from an empty or clean workspace state, creates a project through the real sidebar/dialog flow, verifies the project appears in the sidebar, selects it, and asserts page context actually switches to that project.

**Step 2: Run only the new workspace/project spec and verify RED**

Run: `bunx playwright test tests/e2e/workspace-project-flow.spec.ts --project=chromium`

Expected: FAIL only if the main user path is broken or the test assumptions about the current UI are wrong. Do not weaken the assertion to fit stale UI.

**Step 3: Write the failing workflow registration + run E2E**

Add a browser test that registers a workflow from the real workflows page, binds or runs it from the project path, submits a run, and verifies the new run shows up on the Runs page.

**Step 4: Run only the new workflow/run spec and verify RED**

Run: `bunx playwright test tests/e2e/workflow-run-path.spec.ts --project=chromium`

Expected: FAIL with a product issue or missing test support, not with a selector typo.

**Step 5: Fix real E2E failures in product or support code**

If the new tests expose real defects, fix the product code or backend test support without adding compatibility for retired UI flows.

**Step 6: Re-run the new E2E specs until GREEN**

Run:
- `bunx playwright test tests/e2e/workspace-project-flow.spec.ts --project=chromium`
- `bunx playwright test tests/e2e/workflow-run-path.spec.ts --project=chromium`

**Step 7: Expand run-detail coverage if time remains in the same batch**

Prefer either a third E2E for run detail logs/outputs/DAG, or a strong integration test if the E2E setup cost is too high for this turn.

### Task 2: Hook-first frontend unit coverage

**Files:**
- Create: `frontend/tests/unit/hooks/use-runs-page.test.tsx`
- Create: `frontend/tests/unit/hooks/use-images-page.test.tsx`
- Possibly modify: `frontend/app/(app)/runs/use-runs-page.ts`
- Possibly modify: `frontend/app/(app)/images/use-images-page.ts`

**Step 1: Write failing `useRunsPage` tests for real state transitions**

Cover the highest-value logic only:
- URL/project scope synchronization
- run highlight auto-expand behavior
- detail artifact loading and terminal-status refresh
- run log event accumulation/truncation

**Step 2: Run only the new `useRunsPage` tests and verify RED**

Run: `bun run test -- tests/unit/hooks/use-runs-page.test.tsx`

**Step 3: Fix hook or page logic if the failures reveal product bugs**

Keep assertions strict. If behavior is wrong, repair the hook rather than relaxing the test.

**Step 4: Write failing `useImagesPage` tests for main logic**

Cover:
- docker unavailable retry path
- registry vs tarball submission behavior
- project-aware payloads
- refresh/focus behavior
- empty-state and filtering logic exposed by the hook

**Step 5: Run only the new `useImagesPage` tests and verify RED**

Run: `bun run test -- tests/unit/hooks/use-images-page.test.tsx`

**Step 6: Fix product logic and re-run to GREEN**

Run:
- `bun run test -- tests/unit/hooks/use-runs-page.test.tsx`
- `bun run test -- tests/unit/hooks/use-images-page.test.tsx`

### Task 3: Frontend integration and targeted component gaps

**Files:**
- Create: `frontend/tests/integration/components/workspace-shell-sidebar-context.test.tsx`
- Possibly create: `frontend/tests/integration/pages/settings-page-flow.test.tsx`
- Possibly create: `frontend/tests/unit/components/provider-card.test.tsx`
- Possibly create: `frontend/tests/unit/components/dag-header.test.tsx`
- Possibly create: `frontend/tests/unit/components/dag-node-detail.test.tsx`
- Possibly create: `frontend/tests/unit/lib/conversation-export.test.ts`
- Possibly create: `frontend/tests/unit/lib/time-greeting.test.ts`
- Possibly create: `frontend/tests/unit/lib/nav-routes.test.ts`
- Possibly create: `frontend/tests/unit/lib/format-utils.test.ts`
- Possibly create: `frontend/tests/unit/lib/storage-source-policy.test.ts`
- Possibly create: `frontend/tests/unit/lib/demo/replay-engine.test.ts`
- Possibly modify: `frontend/components/bioinfoflow/settings/provider-card.tsx`
- Possibly modify: `frontend/components/bioinfoflow/settings/settings-page-client.tsx`
- Possibly modify: `frontend/app/(app)/app-layout.tsx`
- Possibly modify: `frontend/hooks/use-sidebar-data.ts`

**Step 1: Add a failing workspace-shell integration test**

Verify the linked behavior for:
- create project
- switch project
- delete project
- select conversation
- active project / active conversation context propagation

**Step 2: Run the focused integration test and verify RED**

Run: `bun run test -- tests/integration/components/workspace-shell-sidebar-context.test.tsx`

**Step 3: Add provider/settings flow tests around save + test connection**

Assert both success and failure feedback paths without weakening the product contract.

**Step 4: Add the smallest useful component/unit gaps**

Prioritize `provider-card`, `dag-header`, `dag-node-detail`, and pure logic utilities that still have no tests.

**Step 5: Re-run only touched frontend suites**

Run the exact `bun run test -- ...` invocations for each new/changed frontend test file.

### Task 4: Backend service-wrapper coverage

**Files:**
- Create: `backend/tests/test_services/test_gpu_service.py`
- Create: `backend/tests/test_services/test_btop_service.py`
- Create: `backend/tests/test_services/test_nextflow_service.py`
- Create: `backend/tests/test_services/test_miniwdl_service.py`
- Possibly modify: `backend/app/services/gpu_service.py`
- Possibly modify: `backend/app/services/btop_service.py`
- Possibly modify: `backend/app/services/nextflow_service.py`
- Possibly modify: `backend/app/services/miniwdl_service.py`

**Step 1: Write failing tests for command/env/path/error handling**

Focus on:
- command construction
- env forwarding
- path payloads
- adapter/backend delegation
- dependency-missing fallback behavior
- error surfacing

**Step 2: Run only the new backend service tests and verify RED**

Run:
- `uv run pytest tests/test_services/test_gpu_service.py -v`
- `uv run pytest tests/test_services/test_btop_service.py -v`
- `uv run pytest tests/test_services/test_nextflow_service.py -v`
- `uv run pytest tests/test_services/test_miniwdl_service.py -v`

**Step 3: Fix real backend issues without hiding failures**

If a wrapper drops config, paths, or errors, repair the service code directly.

**Step 4: Re-run the backend service tests to GREEN**

Use the same `uv run pytest ... -v` commands for the touched files.

### Task 5: Final verification and change summary

**Files:**
- Update: `docs/plans/2026-04-23-high-value-test-expansion.md` only if scope changes materially

**Step 1: Run all directly related verification commands**

At minimum:
- each new Playwright spec individually
- each touched Vitest file or a narrow grouped run
- each touched backend pytest file

**Step 2: Collect real issues found by tests**

List the issue, the failing evidence, the code fix, and the final passing verification.

**Step 3: Stop with explicit remaining high-priority gaps**

If time runs out, leave the next-best targets clearly identified instead of padding coverage with low-value tests.

### Task 6: Agent and workflow-source expansion

**Files:**
- Create: `frontend/tests/e2e/agent-first-analysis.spec.ts`
- Possibly create: `frontend/tests/e2e/agent-workflow-capabilities.spec.ts`
- Possibly modify: `frontend/tests/e2e/pages/agent-page.ts`
- Possibly modify: `frontend/tests/e2e/pages/workflows-page.ts`
- Possibly create: `frontend/tests/integration/pages/workflows-register-sources.test.tsx`
- Possibly create: `frontend/tests/integration/pages/agent-capabilities.test.tsx`
- Possibly modify: `frontend/components/bioinfoflow/chat-stream.tsx`
- Possibly modify: `frontend/app/(app)/workflows/components/workflow-register-dialog.tsx`
- Possibly modify: backend or test support only if the new tests expose real product issues

**Step 1: Write the failing Agent first-analysis E2E**

Cover the real first-user path:
- select a project
- open Agent
- submit the first analysis prompt
- verify the agent enters an active working state and the first assistant response / live workspace affordance appears

**Step 2: Run only the Agent first-analysis spec and verify RED**

Run: `bunx playwright test tests/e2e/agent-first-analysis.spec.ts --project=chromium`

Expected: FAIL only for a real product gap or a wrong assumption about the current UI.

**Step 3: Add source-specific workflow registration coverage**

Prefer a focused integration test first for:
- registering `nf-core` from the real register dialog state transitions
- registering GitHub workflows from the real dialog state transitions
- verifying the resulting payload and visible workflow list state

**Step 4: Add agent capability-path coverage without overfitting to LLM prose**

Test only stable, user-visible contracts:
- natural-language request can produce workflow-building activity
- generated/configured workflow can be registered or surfaced for registration
- run submission intent reaches the run path and is visible in Runs / live deck

Do not assert brittle model wording. Assert artifacts, cards, run creation, approval blocks, and state transitions.

**Step 5: Probe capability boundaries with deterministic fixtures**

Prefer integration or mocked-E2E coverage for boundaries such as:
- no selected project
- missing provider / execution approval path
- unsupported or ambiguous workflow-generation requests
- register/run actions that should surface approval or validation feedback instead of silently proceeding

**Step 6: Re-run only the touched agent/workflow suites**

At minimum:
- `bunx playwright test tests/e2e/agent-first-analysis.spec.ts --project=chromium`
- `bun run test -- tests/integration/pages/workflows-register-sources.test.tsx tests/integration/pages/agent-capabilities.test.tsx`

**Step 7: If tests expose real bugs, fix product code instead of weakening assertions**

Keep the new tests aligned to the current UI and product contract. Do not add compatibility for retired agent or workflow flows.
