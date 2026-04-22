# DAG Repair And Mock Runs Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add backend tooling to repair stale historical run DAG statuses from saved artifacts and generate mock run samples that exercise the DAG UI across multiple node states.

**Architecture:** Extend `RunService` with two focused capabilities: DAG repair for persisted runs and mock run cloning for UI inspection. Expose both through `runs` API endpoints and add a CLI repair script for bulk remediation outside the UI. Keep the implementation artifact-driven by reusing stored `dag`, `trace.tsv`, `dag.dot`, logs, and output directories.

**Tech Stack:** FastAPI, async SQLAlchemy, existing `RunService`, Nextflow trace parsing, pytest.

### Task 1: Add failing tests for DAG repair

**Files:**
- Modify: `backend/tests/test_api/test_runs.py`

**Step 1: Write the failing API test for single/batch DAG repair**

Add a test that:
- creates a completed run with a stored DAG whose nodes are all `pending`
- writes a valid `trace.tsv` containing `COMPLETED` task rows
- calls the new repair endpoint
- asserts the stored DAG is rewritten to `success`

**Step 2: Run the targeted test to verify it fails**

Run: `cd backend && uv run pytest tests/test_api/test_runs.py -k repair_dag -v`

Expected: FAIL because the endpoint and service method do not exist yet.

### Task 2: Add failing tests for mock DAG runs

**Files:**
- Modify: `backend/tests/test_api/test_runs.py`

**Step 1: Write the failing API test for mock DAG variants**

Add a test that:
- creates a source run with a valid DAG structure
- calls the new mock generation endpoint
- asserts several runs are created with expected node statuses
- asserts logs and output endpoints succeed for at least one mock run

**Step 2: Run the targeted test to verify it fails**

Run: `cd backend && uv run pytest tests/test_api/test_runs.py -k mock_dag -v`

Expected: FAIL because the endpoint and service method do not exist yet.

### Task 3: Implement DAG repair in `RunService`

**Files:**
- Modify: `backend/app/services/run_service.py`
- Modify: `backend/app/api/v1/runs.py`

**Step 1: Add a helper that resolves the best available base DAG**

Use the stored DAG if present. If empty, rebuild from `dag.dot` or workflow schema so repair can still proceed.

**Step 2: Add a helper that applies terminal statuses from `trace.tsv` and run outcome**

Rules:
- trace-driven statuses take precedence
- completed runs sweep remaining non-terminal nodes to `success`
- failed/cancelled runs only mark active nodes `failed`
- all terminal runs stop edge animation

**Step 3: Add `repair_run_dag()` and `repair_run_dags()` service methods**

Return structured per-run results including:
- `run_id`
- `status`
- `repaired`
- `reason`
- `node_status_counts`

**Step 4: Add single and batch API endpoints**

Expose:
- `POST /api/v1/runs/{run_id}/repair-dag`
- `POST /api/v1/runs/repair-dags`

### Task 4: Implement mock DAG sample generation

**Files:**
- Modify: `backend/app/services/run_service.py`
- Modify: `backend/app/api/v1/runs.py`

**Step 1: Add a helper that clones a source run into mock variants**

For each variant:
- reuse the DAG structure from a source run
- write a status pattern into node data
- create a log file
- create an output directory with placeholder files
- persist the run with a descriptive `run_id`

**Step 2: Add an API endpoint for sample creation**

Expose:
- `POST /api/v1/runs/{run_id}/mock-dag-variants`

Default variants:
- `pending`
- `queued`
- `running`
- `failed`

### Task 5: Add CLI repair script

**Files:**
- Create: `backend/scripts/repair_run_dags.py`

**Step 1: Implement a small CLI wrapper**

Support:
- `--run-id` repeated
- `--project-id`
- `--dry-run`

Print a compact summary of repaired and skipped runs.

### Task 6: Verify

**Files:**
- None

**Step 1: Run targeted backend tests**

Run:
- `cd backend && uv run pytest tests/test_api/test_runs.py -k repair_dag -v`
- `cd backend && uv run pytest tests/test_api/test_runs.py -k mock_dag -v`
- `cd backend && uv run pytest tests/test_api/test_runs.py -v`

**Step 2: Spot-check against the local demo data**

Run the repair endpoint on `run_baa211`, then request `/api/v1/runs/run_baa211/dag` and confirm nodes are no longer all `pending`.

**Step 3: Create mock variants from a real run**

Create variants from a completed demo run and confirm the created run detail pages load logs, outputs, and the modified DAG states.
