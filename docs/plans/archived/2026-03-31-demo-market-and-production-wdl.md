# Demo Market And Production WDL Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the ad-hoc demo module with a curated starter workflow catalog plus workflow market experience, and verify that a real production-style Deaf_20 WDL can be registered, parsed, and visualized through Bioinfoflow's existing workflow pipeline.

**Architecture:** Keep one backend catalog as the source of truth for bundled starter workflows and market metadata. Use it to seed default local workflows at startup, power the chat/demo quick-run API, and provide richer workflow-market data to the frontend. Validate the provided Deaf_20 WDL through the same `WorkflowService -> WorkflowValidator -> SchemaExtractor -> schema_json -> DAG UI` path used by any local workflow, adding compatibility fixes only where the current parser drops meaningful metadata or dependencies.

**Tech Stack:** FastAPI, async SQLAlchemy, Pydantic, miniwdl, Next.js App Router, React 19, Tailwind CSS 4, Vitest, pytest

### Task 1: Capture The Baseline WDL Compatibility

**Files:**
- Modify: `backend/tests/test_services/test_workflow_validator.py`
- Modify: `backend/tests/test_engine/test_wdl_adapter.py`
- Reference: `backend/app/services/workflow_validator.py`
- Reference: `backend/app/engine/adapters/wdl.py`

**Step 1: Write the failing test**

Add a production-shaped WDL fixture or inline sample that mirrors the supplied Deaf_20 workflow characteristics:
- workflow-level qualified input names like `Deaf_20.sequence_list`
- `scatter` blocks with downstream `call` dependencies
- task `runtime` blocks using `image`
- outputs referencing `${outdir}` style interpolation

Add assertions for:
- extracted workflow name is `Deaf_20`
- extracted inputs include `outdir` and `sequence_list`
- extracted tasks include `PREPARATION`, `SPLIT`, `FILTER`, `ALIGN`, `RESULT`
- extracted dependencies include `PREPARATION -> SPLIT`, `PREPARATION -> FILTER`, `SPLIT -> FILTER`, `FILTER -> ALIGN`, `ALIGN -> RESULT`

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_services/test_workflow_validator.py -k Deaf_20 -v`

Expected: FAIL because current parsing misses one or more dependencies, inputs, or task/runtime details for the production-style WDL.

**Step 3: Write minimal implementation**

Update WDL schema extraction/validation code to preserve the expected production-workflow metadata with the smallest possible change:
- prefer miniwdl-backed schema extraction when available
- improve fallback dependency extraction only if miniwdl output is incomplete
- make sure `runtime.image` is surfaced as task container metadata

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_services/test_workflow_validator.py -k Deaf_20 -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/tests/test_services/test_workflow_validator.py backend/tests/test_engine/test_wdl_adapter.py backend/app/services/workflow_validator.py backend/app/engine/adapters/wdl.py
git commit -m "test: cover production-style Deaf_20 WDL parsing"
```

### Task 2: Define The Curated Starter Workflow Catalog

**Files:**
- Modify: `backend/app/services/demo_catalog.py`
- Modify: `backend/app/schemas/demo.py`
- Modify: `backend/app/services/demo_service.py`
- Modify: `backend/tests/test_services/test_demo_service.py`
- Modify: `backend/tests/test_api/test_demos.py`
- Create: `demo/parabricks-wgs/main.nf`
- Create: `demo/parabricks-wgs/README.md`
- Create: `demo/deaf-20/Deaf_20.wdl`
- Create: `demo/deaf-20/inputs.json`
- Create: `demo/ecoli-qc/main.nf`
- Create: `demo/coronavirus-surveillance/main.nf`
- Modify: `demo/README.md`

**Step 1: Write the failing test**

Update backend tests to expect a new curated catalog shape instead of the legacy three-item featured demo list. Cover:
- 3-5 bundled starter workflows with clear scale bands (`large`, `medium`, `small`)
- a market/listing payload rich enough for frontend cards
- stable quick-run entries still exposed through `/api/v1/demos`
- startup seeding still creates the managed demo/starter projects intended for quick launch

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_services/test_demo_service.py tests/test_api/test_demos.py -v`

Expected: FAIL because the old catalog IDs, titles, and response shape no longer match.

**Step 3: Write minimal implementation**

Refactor the catalog into a clean starter-workflow definition set:
- remove obsolete demo entries and duplicate sample directories
- add curated workflows for Parabricks WGS, Deaf_20, E. coli QC, and coronavirus analysis
- store metadata needed for quick-run and market display in one place
- keep `/demos` functional for chat shortcuts, but have it serve the curated starter list
- preserve idempotent startup seeding and per-starter managed projects

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_services/test_demo_service.py tests/test_api/test_demos.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/demo_catalog.py backend/app/schemas/demo.py backend/app/services/demo_service.py backend/tests/test_services/test_demo_service.py backend/tests/test_api/test_demos.py demo
git commit -m "feat: replace legacy demos with curated starter workflows"
```

### Task 3: Build The Workflow Market Frontend

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/constants/demos.ts`
- Modify: `frontend/hooks/use-chat-actions.ts`
- Modify: `frontend/components/bioinfoflow/demo-cards.tsx`
- Modify: `frontend/components/bioinfoflow/demo-dialog.tsx`
- Modify: `frontend/components/bioinfoflow/command-palette.tsx`
- Modify: `frontend/app/(app)/workflows/page.tsx`
- Modify: `frontend/app/(app)/workflows/components/hub-workflow-card.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`
- Test: `frontend/tests/unit/components/workflow-cards.test.tsx`
- Test: `frontend/tests/integration/pages/workflows-page-actions.test.tsx`

**Step 1: Write the failing test**

Add or update frontend tests so hub/workflow pages show a real market experience:
- starter workflows have richer cards and badges
- users can distinguish curated starters from ordinary registered workflows
- chat demo dialog shows the new starter workflows and action copy

**Step 2: Run test to verify it fails**

Run: `cd frontend && bun run test -- workflow-cards workflows-page-actions`

Expected: FAIL because the current UI only understands a minimal demo payload and generic hub cards.

**Step 3: Write minimal implementation**

Implement a distinctive but repo-consistent market treatment:
- elevate the hub view into a workflow market feel for bundled starters
- expose scale, engine, and starter messaging in cards/dialogs
- keep ordinary workflows usable without forcing the market treatment everywhere
- preserve quick-run behavior from chat and command palette

**Step 4: Run test to verify it passes**

Run: `cd frontend && bun run test -- workflow-cards workflows-page-actions`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/lib/types.ts frontend/constants/demos.ts frontend/hooks/use-chat-actions.ts frontend/components/bioinfoflow/demo-cards.tsx frontend/components/bioinfoflow/demo-dialog.tsx frontend/components/bioinfoflow/command-palette.tsx frontend/app/'(app)'/workflows/page.tsx frontend/app/'(app)'/workflows/components/hub-workflow-card.tsx frontend/messages/en.json frontend/messages/zh-CN.json frontend/tests/unit/components/workflow-cards.test.tsx frontend/tests/integration/pages/workflows-page-actions.test.tsx
git commit -m "feat: add curated workflow market experience"
```

### Task 4: Verify End-To-End Registration, Parsing, And DAG Visibility

**Files:**
- Reference: `backend/app/main.py`
- Reference: `backend/app/api/v1/workflows.py`
- Reference: `frontend/app/(app)/workflows/[id]/page.tsx`
- Modify: `docs/product-overview-zh.md`

**Step 1: Write the failing test**

If an API/service integration test is missing, add a backend test that registers the Deaf_20 WDL through the real workflow service and asserts:
- workflow is created successfully
- `schema_json` contains the expected tasks/dependencies
- no validation error is raised for the production-style input JSON naming

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_api/test_workflows.py -k deaf -v`

Expected: FAIL if the real registration path still disagrees with the lower-level validator behavior.

**Step 3: Write minimal implementation**

Patch any remaining registration-path gaps, then update product/docs copy to reflect that Bioinfoflow now ships with a bundled starter workflow market rather than having no market at all.

**Step 4: Run test to verify it passes**

Run:
- `cd backend && uv run pytest tests/test_api/test_workflows.py -k deaf -v`
- `cd backend && uv run pytest tests/test_services/test_demo_service.py tests/test_api/test_demos.py tests/test_services/test_workflow_validator.py tests/test_engine/test_wdl_adapter.py -v`
- `cd frontend && bun run test -- workflow-cards workflows-page-actions workflows-page-scope workflow-detail-page`

Expected: PASS

**Step 5: Commit**

```bash
git add docs/product-overview-zh.md backend/tests/test_api/test_workflows.py backend/app/main.py backend/app/api/v1/workflows.py frontend/app/'(app)'/workflows/'[id]'/page.tsx
git commit -m "feat: verify starter workflow market and Deaf_20 registration"
```
