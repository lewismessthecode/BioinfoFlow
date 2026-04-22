# Codebase Cleanup Audit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove or update stale, dead, or misleading repository artifacts without breaking backend or frontend behavior.

**Architecture:** Use repository docs plus static analysis to identify low-risk cleanup candidates first, then verify with the existing backend and frontend test/lint gates. Favor removals only when a file is unreferenced or clearly superseded; otherwise update it to match the current implementation.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, Ruff, Next.js App Router, React, ESLint, Bun, Knip, Vulture

### Task 1: Establish Current Intent

**Files:**
- Modify: `README.md`
- Modify: `docs/README.md`
- Modify: `backend/README.md`
- Modify: `frontend/package.json`
- Modify: `backend/pyproject.toml`

**Step 1: Review current repository docs and package metadata**

Read the root, backend, and docs READMEs plus package manifests to capture the current workflow and declared tooling.

**Step 2: Record mismatches between docs/config and code**

List stale references, duplicate lockfile/tooling choices, and generic metadata that no longer match the repository.

### Task 2: Detect Dead or Outdated Artifacts

**Files:**
- Modify: `frontend/UI_UX_REDESIGN_PROGRESS.md`
- Modify: `CLAUDE.md`
- Modify: `frontend/package-lock.json`
- Modify: `backend/app/services/agent/tools/*.py`
- Modify: `frontend/**/*.ts`
- Modify: `frontend/**/*.tsx`

**Step 1: Run text and static analysis scans**

Use ripgrep, Knip, and Vulture to find unreferenced files, unused exports, legacy compatibility code, and outdated notes.

**Step 2: Confirm each candidate with usage checks**

Search imports/usages before removing anything. Keep compatibility paths that are still reached by production code or tests.

### Task 3: Apply Low-Risk Cleanup

**Files:**
- Modify: `CLAUDE.md`
- Modify: `frontend/package.json`
- Delete: `frontend/UI_UX_REDESIGN_PROGRESS.md`
- Delete: `frontend/package-lock.json`
- Modify: other files only where evidence shows stale or dead code

**Step 1: Remove or archive clearly dead files**

Delete files that are unreferenced progress artifacts or obsolete lockfiles that conflict with the active package manager.

**Step 2: Update stale guidance/config**

Refresh docs and metadata that are still useful but currently inaccurate.

**Step 3: Keep compatibility code unless analysis proves it is dead**

Do not delete legacy runtime code paths when tests or imports still depend on them.

### Task 4: Verify and Report

**Files:**
- Test: `backend/tests/`
- Test: `frontend/tests/`

**Step 1: Install dependencies needed for repo checks**

Run backend `uv sync` and frontend `bun install` in this worktree.

**Step 2: Run backend verification**

Run `uv run ruff check .`, `uv run pytest`, and `uv run vulture app tests` from `backend/`.

**Step 3: Run frontend verification**

Run `bun run lint`, and if available `bunx knip` with the repository config.

**Step 4: Summarize remaining gaps**

Report cleanup completed, unresolved stale areas, not-yet-implemented product gaps, and recommended next iterations.
