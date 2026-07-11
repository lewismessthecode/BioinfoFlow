# Managed Run Directory Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate the exact platform-managed run-directory key set without changing any caller-specific filtering or engine behavior.

**Architecture:** Add `app.services.run_input_policy` as the single owner of an immutable four-name set and a case-insensitive exact-name predicate. Callers continue to own whitespace normalization, qualified-name leaf extraction, internal-field checks, path classification, and WDL path absolutization.

**Tech Stack:** Python 3.12, pytest, Ruff.

---

### Task 1: Characterize the shared policy and caller boundaries

**Files:**

- Modify: `backend/tests/test_services/test_run_helpers.py`
- Modify: `backend/tests/test_services/test_run_compiler.py`
- Modify: `backend/tests/test_services/test_run_lifecycle_service.py`
- Modify: `backend/tests/test_engine/test_wdl_adapter.py`
- Modify: `backend/tests/test_services/test_workflow_validator.py`

- [x] Add a policy contract test that requires `MANAGED_RUN_DIRECTORY_NAMES` to be a `frozenset` equal to `{"outdir", "output_dir", "publish_dir", "work_dir"}` and exercises exact case-insensitive membership without accepting qualified or unknown names.
- [x] Add helper characterization proving all four managed names are excluded from path-like detection while an ordinary path key remains path-like.
- [x] Add compiler characterization proving only internal, unqualified managed names become workflow-qualified WDL inputs; non-internal, qualified, and unknown names remain excluded.
- [x] Add lifecycle characterization proving replay filtering strips whitespace and checks the qualified leaf while retaining ordinary values.
- [x] Add WDL adapter characterization proving relative managed-directory inputs, including qualified names, are absolutized while absolute, blank, non-string, and unmanaged values are unchanged.
- [x] Add validator characterization proving whitespace and case are normalized, but qualified and unknown names are not internal.
- [x] Run the focused tests and record the expected RED failure caused only by the absent shared policy module:

  ```bash
  rtk uv run pytest tests/test_services/test_run_compiler.py tests/test_services/test_run_lifecycle_service.py tests/test_services/test_run_helpers.py tests/test_engine/test_wdl_adapter.py tests/test_services/test_workflow_validator.py -q
  ```

### Task 2: Introduce the focused shared policy

**Files:**

- Create: `backend/app/services/run_input_policy.py`
- Modify: `backend/app/services/run_compiler.py`
- Modify: `backend/app/services/run_lifecycle_service.py`
- Modify: `backend/app/services/run_helpers.py`
- Modify: `backend/app/engine/adapters/wdl.py`
- Modify: `backend/app/services/validators/types.py`

- [x] Define `MANAGED_RUN_DIRECTORY_NAMES` as the exact immutable four-name set.
- [x] Define `is_managed_run_directory_name(name: str) -> bool` using the existing case-insensitive exact membership semantics only.
- [x] Replace the compiler's inline membership check while retaining internal-field filtering, trimming, and WDL qualification locally.
- [x] Replace lifecycle's local set while retaining object coercion, trimming, and qualified leaf extraction locally.
- [x] Replace helper membership while retaining `_mode`, URL/URI, and path-regex ordering locally.
- [x] Replace WDL adapter membership while retaining object coercion, trimming, qualified leaf extraction, and path absolutization locally.
- [x] Replace validator membership while retaining object coercion and trimming locally.
- [x] Run the focused tests and record GREEN output:

  ```bash
  rtk uv run pytest tests/test_services/test_run_compiler.py tests/test_services/test_run_lifecycle_service.py tests/test_services/test_run_helpers.py tests/test_engine/test_wdl_adapter.py tests/test_services/test_workflow_validator.py -q
  ```

### Task 3: Verify, self-review, and commit

**Files:**

- Review all files changed above.

- [x] Run Ruff:

  ```bash
  rtk uv run ruff check .
  ```

- [x] Run the full backend suite:

  ```bash
  rtk uv run pytest
  ```

- [x] Run whitespace and patch checks:

  ```bash
  rtk git diff --check
  ```

- [x] Inspect `rtk git diff --stat`, `rtk git diff`, and `rtk git status --short`; confirm no engine-specific transformation, key rename, or unrelated file change entered the patch.
- [x] Sync `origin/main` as required by `AGENTS.md`, re-run affected verification if the rebase changes the branch, then commit:

  ```bash
  rtk git fetch origin --prune
  rtk git rebase origin/main
  rtk git add backend/app/services/run_input_policy.py backend/app/services/run_compiler.py backend/app/services/run_lifecycle_service.py backend/app/services/run_helpers.py backend/app/engine/adapters/wdl.py backend/app/services/validators/types.py backend/tests/test_services/test_run_compiler.py backend/tests/test_services/test_run_lifecycle_service.py backend/tests/test_services/test_run_helpers.py backend/tests/test_engine/test_wdl_adapter.py backend/tests/test_services/test_workflow_validator.py docs/plans/2026-07-11-managed-directory-policy.md
  rtk git commit -m "refactor: centralize managed run directories"
  ```
