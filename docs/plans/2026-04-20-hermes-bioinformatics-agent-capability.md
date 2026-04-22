# Hermes Bioinformatics Agent Capability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend the Hermes-native agent path so it can prepare a workflow for a project, preview and validate run configuration, execute a workflow, and summarize run results in a way that matches the product promise of a bioinformatics agent.

**Architecture:** Keep the Hermes integration centered in `backend/app/services/hermes_service/tool_bridge.py` and add a second-layer set of Bioinfoflow-native tools on top of existing services. Reuse existing project workflow, run preview, validation, run status/log/output archive services so the Hermes path stays thin and consistent with current REST behavior. Drive the work test-first in `backend/tests/test_services/test_hermes_runtime_bridge.py`.

**Tech Stack:** FastAPI backend, async SQLAlchemy/SQLite, Hermes SDK registry/toolsets, existing Bioinfoflow project workflow and run services, pytest.

### Task 1: Add failing tool-bridge tests

**Files:**
- Modify: `backend/tests/test_services/test_hermes_runtime_bridge.py`
- Reference: `backend/app/services/hermes_service/tool_bridge.py`

**Step 1: Write the failing tests**

Add tests for:
- `project_enable_workflow` binding a workflow to the active project
- `preview_run_profile` returning detected inputs and resolved params for a workspace
- `workflow_validate` reporting missing/invalid parameters without side effects
- `run_results_overview` returning run status, logs, artifacts, and output location
- Hermes registry exposure for the new tool names

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_services/test_hermes_runtime_bridge.py -q`

Expected: failures showing the new tool names/functions do not exist yet.

### Task 2: Implement Hermes-native workflow preparation and validation tools

**Files:**
- Modify: `backend/app/services/hermes_service/tool_bridge.py`
- Reference: `backend/app/services/project_workflow_service.py`
- Reference: `backend/app/services/run_submission_service.py`
- Reference: `backend/app/services/agent/tools/workflow_tools.py`

**Step 1: Implement minimal tool functions**

Add Hermes-native tool functions for:
- `project_enable_workflow`
- `preview_run_profile`
- `workflow_validate`

Each tool should:
- use `HermesToolRuntimeContext`
- return structured JSON with a `summary`
- reuse existing service logic instead of duplicating workflow business rules

**Step 2: Register the new tools**

Add schemas and registry wiring in `ensure_bioinfoflow_toolset_registered()`.

**Step 3: Run targeted tests**

Run: `uv run pytest tests/test_services/test_hermes_runtime_bridge.py -q -k "project_enable_workflow or preview_run_profile or workflow_validate"`

Expected: passing tests for the new tools.

### Task 3: Implement Hermes-native run results overview

**Files:**
- Modify: `backend/app/services/hermes_service/tool_bridge.py`
- Reference: `backend/app/services/run_service.py`
- Reference: `backend/app/services/run_archive.py`

**Step 1: Implement `run_results_overview`**

Return a structured payload that includes:
- run identity and status
- task progress/current task/error
- output directory if resolvable
- recent logs
- artifact listing summary

Keep the tool read-only and return a concise `summary`.

**Step 2: Register the tool**

Expose it in the Hermes `bioinfoflow` toolset registration list.

**Step 3: Run targeted tests**

Run: `uv run pytest tests/test_services/test_hermes_runtime_bridge.py -q -k "run_results_overview"`

Expected: passing tests showing the agent can narrate run results, not just fetch raw files.

### Task 4: Verify the expanded Hermes capability slice

**Files:**
- Modify if needed: `backend/tests/test_services/test_hermes_runtime_bridge.py`

**Step 1: Run the Hermes backend verification suite**

Run: `uv run pytest tests/test_services/test_hermes_service.py tests/test_api/test_agent_hermes_api.py tests/test_services/test_hermes_runtime_bridge.py -q`

Expected: full Hermes-targeted backend suite passes.

**Step 2: Run focused linting**

Run: `uv run ruff check app/services/hermes_service/tool_bridge.py tests/test_services/test_hermes_runtime_bridge.py`

Expected: no lint errors.

**Step 3: Commit**

```bash
git add docs/plans/2026-04-20-hermes-bioinformatics-agent-capability.md \
  backend/app/services/hermes_service/tool_bridge.py \
  backend/tests/test_services/test_hermes_runtime_bridge.py
git commit -m "feat: expand hermes bioinformatics workflow tools"
```
