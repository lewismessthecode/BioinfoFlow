# Demo Service, Legacy Dispatcher, and Workflow Validate Removal Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove DemoService, remove legacy dispatcher code paths, and remove the agent-side `workflow_validate` tool while preserving the five bundled workflow directories as test assets.

**Architecture:** The platform should expose one execution path: workflow registration plus canonical `POST /runs` backed by the persistent scheduler. Demo-specific quick-launch APIs and startup seeding will be removed, while the bundled workflow source directories remain on disk for tests and local registration. Agent runtime and Hermes prompts/tooling will stop advertising or invoking `workflow_validate`, relying on workflow metadata plus direct `submit_run` instead.

**Tech Stack:** FastAPI, async SQLAlchemy, Next.js 16, React 19, pytest, Vitest

### Task 1: Remove demo-facing API and UI behavior

**Files:**
- Modify: `backend/app/api/v1/router.py`
- Delete: `backend/app/api/v1/demos.py`
- Modify: `backend/app/api/v1/workflows.py`
- Delete: `backend/app/services/demo_service.py`
- Modify: `backend/app/services/demo_catalog.py`
- Modify: `backend/app/main.py`
- Modify: `frontend/components/bioinfoflow/command-palette.tsx`
- Modify: `frontend/hooks/use-sidebar-data.ts`
- Modify: `frontend/lib/types.ts`
- Delete or update: `backend/tests/test_api/test_demos.py`
- Delete or update: `backend/tests/test_api/test_demo_smoke.py`
- Delete or update: `backend/tests/test_services/test_demo_service.py`
- Modify: `frontend/tests/unit/components/command-palette.test.tsx`
- Modify: `frontend/tests/unit/hooks/use-sidebar-data.test.tsx`

**Step 1: Write the failing tests**

- Remove expectations for `/demos` and `/workflows/market`.
- Add/adjust frontend tests so command palette no longer loads demos and sidebar no longer prioritizes `Demo/` projects.
- Add/adjust backend tests so startup no longer seeds demo workflows.

**Step 2: Run the targeted tests and watch them fail**

Run:

```bash
cd backend && uv run pytest tests/test_api/test_demos.py tests/test_api/test_demo_smoke.py tests/test_services/test_demo_service.py -q
cd frontend && bun run test tests/unit/components/command-palette.test.tsx tests/unit/hooks/use-sidebar-data.test.tsx
```

**Step 3: Remove demo-specific production code**

- Remove demo router registration and `DemoService`.
- Remove `/workflows/market`.
- Trim `demo_catalog.py` down to the five preserved workflow specs used by tests and agent prompt examples.
- Stop startup seeding from `main.py`.
- Remove demo fetch/render logic from command palette.
- Remove `Demo/` project sorting special case.

**Step 4: Re-run the targeted tests**

Run the same backend and frontend commands and confirm green.

### Task 2: Remove legacy dispatcher code paths

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/services/run_dispatch.py`
- Modify: `backend/app/services/run_compiler.py`
- Modify: `backend/app/services/run_service.py`
- Modify: `backend/app/services/run_lifecycle_service.py`
- Modify: `backend/app/api/v1/scheduler.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_services/test_run_dispatch.py`
- Modify: `backend/tests/test_api/test_scheduler_api.py`
- Modify: `backend/tests/test_auth/test_dependencies.py`
- Modify: `backend/tests/test_scheduler/test_scheduler.py`
- Modify: `backend/tests/test_api/test_workflow_form_spec.py`

**Step 1: Write the failing tests**

- Update dispatcher tests to expect only `SchedulerDispatcher`.
- Update app/scheduler API tests to remove `legacy` mode assumptions and fallback behavior.
- Update fixtures that pin `run_scheduler_mode="legacy"`.

**Step 2: Run the targeted tests and watch them fail**

Run:

```bash
cd backend && uv run pytest tests/test_services/test_run_dispatch.py tests/test_api/test_scheduler_api.py tests/test_auth/test_dependencies.py tests/test_scheduler/test_scheduler.py tests/test_api/test_workflow_form_spec.py -q
```

**Step 3: Remove legacy implementation**

- Delete `LegacyDispatcher`.
- Make `get_run_dispatcher()` require or default to scheduler-backed dispatch only.
- Remove `run_scheduler_mode` branches and startup fallback to legacy dispatch.
- Keep resource/storage failures explicit instead of silently downgrading execution.

**Step 4: Re-run the targeted tests**

Run the same backend command and confirm green.

### Task 3: Remove `workflow_validate` from agent and Hermes surfaces

**Files:**
- Modify: `backend/app/services/agent/tools/workflow_tools.py`
- Modify: `backend/app/services/agent/tools/__init__.py`
- Modify: `backend/app/services/agent/runtime/system_prompt.py`
- Modify: `backend/app/services/hermes_service/tool_bridge.py`
- Modify: `backend/app/services/hermes_service/system_prompt.py`
- Modify: `backend/tests/test_agent/test_tools/test_workflow_tools.py`
- Modify: `backend/tests/test_agent/test_runtime/test_dispatch.py`
- Modify: `backend/tests/test_services/test_hermes_runtime_bridge.py`

**Step 1: Write the failing tests**

- Update tool registration tests to assert `workflow_validate` is absent.
- Update Hermes runtime bridge and prompt tests to stop expecting the tool or prompt guidance.
- Add/adjust tests so canonical `submit_run` behavior still works without a separate validate tool.

**Step 2: Run the targeted tests and watch them fail**

Run:

```bash
cd backend && uv run pytest tests/test_agent/test_tools/test_workflow_tools.py tests/test_agent/test_runtime/test_dispatch.py tests/test_services/test_hermes_runtime_bridge.py -q
```

**Step 3: Remove the tool**

- Delete the `workflow_validate` tool implementation and bridge wrappers.
- Remove prompt instructions that require calling it before `submit_run`.
- Keep any reusable validation helpers that are still needed internally by `submit_run`.

**Step 4: Re-run the targeted tests**

Run the same backend command and confirm green.

### Task 4: Update documentation to match reality

**Files:**
- Modify: `docs/api/reference.md`
- Modify: `docs/cli/README.md`
- Modify: `docs/workflow-submission-guide.md`
- Modify: `docs/architecture/system.md`
- Modify: `docs/architecture/product-system-flow.html`

**Step 1: Write the failing documentation assertions if tests exist**

- Update or remove doc references to `/demos`, `/workflows/market`, `workflow_validate`, and legacy scheduler mode.

**Step 2: Edit docs**

- Describe the canonical run contract only.
- Describe the scheduler as the only execution path.
- Remove DemoService references.
- Keep the five workflow directories described as bundled test assets if needed.

### Task 5: Verification

**Files:**
- No code changes expected unless verification exposes gaps.

**Step 1: Run focused verification**

```bash
cd backend && uv run pytest tests/test_api/test_agent_api.py tests/test_api/test_agent_hermes_api.py tests/test_services/test_hermes_service.py tests/test_services/test_run_dispatch.py tests/test_api/test_scheduler_api.py tests/test_agent/test_runtime/test_dispatch.py tests/test_agent/test_tools/test_workflow_tools.py -q
cd frontend && bun run test tests/unit/components/command-palette.test.tsx tests/unit/hooks/use-sidebar-data.test.tsx tests/unit/hooks/use-agent-chat.test.tsx
```

**Step 2: Run lint/format on touched surfaces**

```bash
cd backend && uv run ruff format app tests && uv run ruff check app tests
cd frontend && bun run lint
```

**Step 3: Confirm preserved assets**

- Verify the following directories still exist and are unmodified unless tests require fixture tweaks:
  - `demo/rnaseq-quant-mini`
  - `demo/variant-fanout-mini`
  - `demo/flaky-retry-mini`
  - `demo/resource-stress-mini`
  - `demo/subworkflow-import-mini`
