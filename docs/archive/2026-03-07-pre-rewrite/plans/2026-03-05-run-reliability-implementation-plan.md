# Run Reliability Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce run failure rate by enforcing run preflight, safe resume semantics, unified payload construction, and deterministic recovery for stale queued/running runs.

**Architecture:** Centralize reliability logic in backend `RunService` and engine services. Step 1 adds strict preflight + resume contract + MiniWDL binary/path resilience. Step 2 introduces profile-driven payload builders consumed by Chat and Demo so all run entry points share one source of truth. Step 3 persists resolved input artifacts and adds stale-run recovery at startup.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Nextflow/MiniWDL adapters, Next.js frontend hook, pytest (+ pytest-asyncio).

---

## Task 1: Stop-bleeding reliability guardrails (Step 1)

**Files:**
- Modify: `backend/app/services/nextflow_service.py`
- Modify: `backend/app/services/run_service.py`
- Modify: `backend/app/services/miniwdl_service.py`
- Modify: `backend/app/api/v1/runs.py`
- Modify: `backend/tests/test_services/test_execution.py`
- Modify: `backend/tests/test_services/test_run_service.py`
- Modify: `backend/tests/test_api/test_runs.py`

**Step 1: Write failing tests (RED)**

Add/extend tests to fail against current behavior:

1. `test_nextflow_parse_output_extracts_bracketed_run_name`
```python
started = service._parse_output_line("Launching `demo/main.nf` [mighty_curie] - revision: abc")
assert started == {"event": "started", "run_name": "mighty_curie"}
```

2. `test_resume_run_requires_nextflow_and_valid_resume_token`
```python
with pytest.raises(ValueError, match="resume is only supported for nextflow"):
    await service.resume_run(wdl_failed_run.run_id)

with pytest.raises(ValueError, match="cannot be resumed"):
    await service.resume_run(nextflow_failed_without_run_name.run_id)
```

3. `test_create_run_preflight_rejects_missing_path_and_empty_glob`
```python
with pytest.raises(FileNotFoundError, match="param path not found"):
    await service.create_run(..., params={"samplesheet": "missing.csv"})

with pytest.raises(FileNotFoundError, match="param glob has no matches"):
    await service.create_run(..., params={"reads": "reads/*_{R1,R2}.fastq.gz"})
```

4. `test_miniwdl_service_emits_binary_not_found_event`
```python
service = MiniWDLService(miniwdl_bin="/definitely/missing/miniwdl")
events = [event async for event in service.run(config, str(workspace))]
assert events[-1]["event"] == "error"
assert "MiniWDL binary not found" in events[-1]["message"]
```

**Step 2: Run tests and verify failures**

Run:
```bash
cd backend && uv run pytest \
  tests/test_services/test_execution.py \
  tests/test_services/test_run_service.py \
  tests/test_api/test_runs.py -q
```

Expected: FAIL for each new test due current implementation gaps.

**Step 3: Minimal implementation (GREEN)**

- Fix Nextflow run-name parsing to prefer bracket token (`[run_name]`), fallback only when safe.
- Enforce resume contract in `RunService.resume_run`:
  - workflow engine must be `nextflow`
  - `nextflow_run_name` must exist and pass token validation
- Add `RunService` preflight for `create_run`:
  - binary availability for engine
  - workflow source path existence for local workflows
  - params path/glob checks for path-like keys (`input`, `reads`, `reference`, `samplesheet`, `fasta`, `fastq*`, `bam*`, etc.)
- Harden MiniWDL binary resolution:
  - resolve via `shutil.which`, absolute path, or `repo_root`-relative fallback
  - emit explicit error event when binary missing or launch fails
- Map preflight validation failures in `/runs` endpoint to `422 VALIDATION_ERROR`.

**Step 4: Re-run tests and verify pass**

Run same test command; expected PASS.

**Step 5: Commit**

```bash
git add backend/app/services/nextflow_service.py \
  backend/app/services/run_service.py \
  backend/app/services/miniwdl_service.py \
  backend/app/api/v1/runs.py \
  backend/tests/test_services/test_execution.py \
  backend/tests/test_services/test_run_service.py \
  backend/tests/test_api/test_runs.py
git commit -m "fix: add run preflight and safe resume contract"
```

---

## Task 2: Unify Chat/Demo/UI payload construction (Step 2)

**Files:**
- Create: `backend/app/services/run_profile_service.py`
- Modify: `backend/app/services/run_service.py`
- Modify: `backend/app/services/demo_service.py`
- Modify: `frontend/hooks/use-chat-stream.ts`
- Create/Modify tests:
  - `backend/tests/test_services/test_run_profile_service.py`
  - `backend/tests/test_services/test_run_service.py`
  - `backend/tests/test_services/test_demo_service.py`

**Step 1: Write failing tests (RED)**

1. `test_profile_builder_for_viral_nextflow_resolves_samplesheet_reference_reads`
```python
spec = build_profiled_run_spec(...)
assert spec.params["samplesheet"] == "samplesheet.csv"
assert spec.params["reference"].startswith("ref/")
assert "reads" in spec.params
```

2. `test_demo_run_uses_profile_builder_not_hardcoded_params`
```python
run = await demo_service.run_demo("viral-mini-nf", ...)
# verify create_run called with profile-derived params from workspace scan
```

3. `test_chat_payload_builder_omits_hardcoded_reference`
```ts
expect(payload.params.reference).toBe(resolvedReferencePath)
expect(payload.params.reference).not.toBe("ref/reference.fasta")
```

**Step 2: Run tests and verify failures**

Run backend tests + frontend targeted test (if added):
```bash
cd backend && uv run pytest tests/test_services/test_run_profile_service.py tests/test_services/test_demo_service.py -q
cd ../frontend && bunx vitest path/to/chat-payload.test.ts
```

Expected: FAIL before implementation.

**Step 3: Minimal implementation (GREEN)**

- Implement `RunProfileService` as a single source of truth for profile defaults + auto-detection.
- Integrate into:
  - `RunService.create_run` (optional profile expansion before preflight)
  - `DemoService.run_demo`
  - Chat hook request generation (consume backend-derived resolved params or shared helper)
- Remove Chat hardcoded `reference: "ref/reference.fasta"` and brittle generic defaults.

**Step 4: Re-run tests and verify pass**

Run same commands; expected PASS.

**Step 5: Commit**

```bash
git add backend/app/services/run_profile_service.py \
  backend/app/services/run_service.py \
  backend/app/services/demo_service.py \
  frontend/hooks/use-chat-stream.ts \
  backend/tests/test_services/test_run_profile_service.py \
  backend/tests/test_services/test_run_service.py \
  backend/tests/test_services/test_demo_service.py
git commit -m "feat: unify run payload construction with profiles"
```

---

## Task 3: Resolved RunSpec persistence + stale run recovery (Step 3)

**Files:**
- Modify: `backend/app/services/run_service.py`
- Modify: `backend/app/runtime/jobs.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/repositories/run_repo.py` (if query helper needed)
- Add/Modify tests:
  - `backend/tests/test_services/test_run_service.py`
  - `backend/tests/test_runtime/test_run_recovery.py` (new)
  - `backend/tests/test_api/test_runs.py`

**Step 1: Write failing tests (RED)**

1. `test_create_run_persists_resolved_runspec_manifest`
```python
run = await service.create_run(...)
manifest = json.loads((archive_dir / "run.manifest.json").read_text())
assert manifest["resolved_inputs"]["params"]["samplesheet"].startswith("/")
assert manifest["resolved_inputs"]["files"]
```

2. `test_retry_uses_persisted_resolved_runspec_when_original_paths_changed`
```python
# delete original input file after first run creation
retried = await service.retry_run(original.run_id)
assert retried.config["resolved_runspec"]["params"]
```

3. `test_recover_stale_runs_marks_old_running_or_queued_as_failed`
```python
count = await recover_stale_runs(session, stale_after_minutes=15)
assert count == 2
assert updated_run.error_message.startswith("Run recovery")
```

**Step 2: Run tests and verify failures**

Run:
```bash
cd backend && uv run pytest \
  tests/test_services/test_run_service.py \
  tests/test_runtime/test_run_recovery.py \
  tests/test_api/test_runs.py -q
```

Expected: FAIL before implementation.

**Step 3: Minimal implementation (GREEN)**

- Persist `resolved_runspec` in both run archive and run `config` at enqueue time.
- Reuse resolved spec for retry/resume where safe.
- Add startup recovery sweep (lifespan): mark stale `queued/running` runs as `failed` with explicit reason and completion timestamps.

**Step 4: Re-run tests and verify pass**

Run same test command; expected PASS.

**Step 5: Commit**

```bash
git add backend/app/services/run_service.py \
  backend/app/runtime/jobs.py \
  backend/app/main.py \
  backend/app/repositories/run_repo.py \
  backend/tests/test_services/test_run_service.py \
  backend/tests/test_runtime/test_run_recovery.py \
  backend/tests/test_api/test_runs.py
git commit -m "feat: persist resolved runspec and recover stale runs"
```

---

## Final Verification

Run:
```bash
cd backend && uv run pytest
cd ../frontend && bun run lint
```

Expected: all checks pass.
