# README And Docs Refresh Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Simplify the repo README quick start and move detailed user guidance into Bioinfoflow Docs.

**Architecture:** Keep README as the project front door: product summary, shortest Docker quick start, links, and local development commands. Put operational details, storage concepts, Parabricks examples, CLI usage, architecture, and security notes under `docs/`, with text checked against the current Docker Compose, backend config, startup lifecycle, and frontend auth implementation.

**Tech Stack:** Markdown docs, Docker Compose, FastAPI backend configuration, Next.js frontend auth/runtime configuration.

### Task 1: Confirm Startup Truth

**Files:**
- Read: `docker-compose.yml`
- Read: `.env.example`
- Read: `backend/app/config.py`
- Read: `backend/app/main.py`
- Read: `backend/app/path_layout.py`
- Read: `backend/scripts/docker-entrypoint.sh`
- Read: `frontend/lib/auth.ts`

**Steps:**
1. Verify Docker Compose defaults `BIOINFOFLOW_HOME` to `${PWD}/data`.
2. Verify backend code default `bioinfoflow_home = "data"` resolves against the repo root.
3. Verify backend startup calls `ensure_platform_layout()`.
4. Verify frontend auth creates the Better Auth database parent directory.
5. Record any remaining implementation/doc inconsistencies.

### Task 2: Simplify README

**Files:**
- Modify: `README.md`

**Steps:**
1. Keep product intro and preview.
2. Replace the current Quick Start with `cp .env.example .env`, edit required values, optional local default note, and `docker compose up -d --build`.
3. Remove the confusing manual `mkdir` step from the main path.
4. Keep the Local Development section.
5. Link detailed topics into `docs/`.

### Task 3: Add Bioinfoflow Docs Entry Points

**Files:**
- Modify: `docs/README.md`
- Create: `docs/getting-started/docker.md`
- Create: `docs/concepts/storage.md`
- Create: `docs/workflows/parabricks-wgs.md`
- Create: `docs/security.md`

**Steps:**
1. Make `docs/README.md` read like the Bioinfoflow Docs home page.
2. Document Docker startup from current Compose and startup code.
3. Document storage roots and asset URI concepts from `backend/app/config.py` and `backend/app/path_layout.py`.
4. Move Parabricks WGS guidance from README into docs.
5. Move security notes into docs.

### Task 4: Align Stale Existing Docs

**Files:**
- Modify: `.env.example`
- Modify: `RUNBOOK.md`
- Modify: `docs/operations/runbook.md`
- Modify: `backend/README.md`
- Modify: `docker-compose.yml`

**Steps:**
1. Replace stale `/srv/bioinfoflow` or `bpiper` defaults where the code now uses `${PWD}/data` for Compose and repo-local `data` for local dev.
2. Keep server/HPC examples as explicit optional values.
3. Avoid adding setup steps that conflict with `BIOINFOFLOW_HOME`.

### Task 5: Verify

**Commands:**
- `rg -n "bpiper|/srv/bioinfoflow|mkdir -p data/state data/projects data/sources/deliveries data/sources/reference|./data -> /srv" README.md .env.example RUNBOOK.md docs backend/README.md docker-compose.yml`
- `git diff --check`

**Expected:**
- No stale `bpiper` or `./data -> /srv` docs remain.
- `/srv/bioinfoflow` appears only as an explicit server example, not as a local Docker default.
- No markdown whitespace errors.
