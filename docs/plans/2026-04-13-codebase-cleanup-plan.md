# Codebase Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove dead exports and obvious redundant code surfaced by project static checks, while keeping behavior unchanged.

**Architecture:** This cleanup stays intentionally narrow. We only touch items with direct evidence from `knip` and `ruff`, plus one import-order simplification in the LLM runtime module so the code stays easier to read and lint.

**Tech Stack:** FastAPI, Python, Ruff, Next.js, TypeScript, Knip

### Task 1: Remove dead frontend exports

**Files:**
- Modify: `frontend/lib/demo/replay-engine.ts`
- Modify: `frontend/lib/types.ts`
- Test: `frontend/package.json`

**Step 1: Confirm the dead exports are unreferenced**

Run: `rg -n "totalDuration|SubmissionHintSamplesheetTab|SubmissionHintJsonTab|WizardStep" frontend`
Expected: Only type-local references remain.

**Step 2: Remove the unused exports**

- Delete `totalDuration` from `frontend/lib/demo/replay-engine.ts`.
- Inline the two submission tab types into `WorkflowSubmissionSpec` if they are not reused elsewhere.
- Remove `WizardStep` if it is not referenced.

**Step 3: Re-run dead code check**

Run: `bun run lint:dead-code`
Expected: The previous unused export/type findings disappear.

### Task 2: Fix backend static issues and simplify imports

**Files:**
- Modify: `backend/app/engine/schema_extractor.py`
- Modify: `backend/app/services/agent/runtime/llm_client.py`
- Modify: `backend/app/services/demo_service.py`
- Test: `backend/`

**Step 1: Remove truly unused imports**

- Delete the unused `re` import from `schema_extractor.py`.

**Step 2: Normalize top-level imports in `llm_client.py`**

- Keep all imports grouped at the top of the file.
- Move the compatibility alias assignments below the import section.

**Step 3: Fix missing type import in `demo_service.py`**

- Import `Project` if the annotation is meant to stay.
- Prefer the smallest change that satisfies type checking and linting.

**Step 4: Re-run backend lint**

Run: `uv run ruff check .`
Expected: The current `F401`, `E402`, and `F821` findings are gone.

### Task 3: Verify and record results

**Files:**
- Modify: `docs/plans/2026-04-13-codebase-cleanup-plan.md`

**Step 1: Run targeted verification**

Run: `cd frontend && bun run lint:dead-code`
Expected: Pass

Run: `cd backend && uv run ruff check .`
Expected: Pass

**Step 2: Summarize remaining cleanup opportunities**

- Note any larger simplifications discovered but intentionally deferred because they need behavioral review or broader testing.
