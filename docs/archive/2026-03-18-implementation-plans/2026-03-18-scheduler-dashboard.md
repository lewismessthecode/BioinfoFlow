# Scheduler Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn the Scheduler page into a useful scheduler health dashboard that explains scheduler availability, queue pressure, refresh timing, and system resource constraints without requiring true real-time streaming.

**Architecture:** Extend the backend `/scheduler/status` and `/scheduler/resources` responses so the frontend can distinguish configured mode from actual runtime availability and can render clearer queue/resource summaries. Keep the frontend page client-rendered with interval polling, but make the page explicitly communicative: health banner, snapshot timestamp, operational summary, queue-state cards, resource gauges, and guidance text.

**Tech Stack:** FastAPI, async SQLAlchemy, Next.js App Router, React 19, next-intl, Vitest, pytest.

### Task 1: Define the richer scheduler API contract

**Files:**
- Modify: `backend/app/api/v1/scheduler.py`
- Modify: `backend/app/scheduler/scheduler.py`
- Test: `backend/tests/test_api/test_scheduler_api.py`

**Step 1: Write the failing backend tests**

Add tests asserting:
- `/scheduler/status` returns both configured and effective mode
- fallback-to-legacy exposes scheduler availability and reasoned health state
- `/scheduler/resources` includes snapshot metadata

**Step 2: Run the backend scheduler API tests to verify they fail**

Run: `uv run pytest tests/test_api/test_scheduler_api.py -q`

**Step 3: Implement minimal backend status/resource payload changes**

Return fields that let the UI answer:
- Was persistent scheduler configured?
- Is a scheduler instance actually running?
- Is resource monitoring enabled?
- When was the current resource snapshot captured?

**Step 4: Re-run the backend scheduler API tests**

Run: `uv run pytest tests/test_api/test_scheduler_api.py -q`

### Task 2: Update frontend types and page tests

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/tests/integration/pages/scheduler-page.test.tsx`

**Step 1: Write the failing frontend integration tests**

Add tests asserting the page:
- shows effective scheduler state and degraded/fallback messaging
- renders resource snapshot timestamp and auto-refresh context
- renders queue summary and explanatory guidance

**Step 2: Run the page test to verify it fails**

Run: `bun run test tests/integration/pages/scheduler-page.test.tsx`

**Step 3: Update the frontend types for the richer contract**

Add exact fields needed by the page and keep the shape aligned to the backend.

**Step 4: Re-run the page test to confirm the type-aligned mocks still fail only on missing UI**

Run: `bun run test tests/integration/pages/scheduler-page.test.tsx`

### Task 3: Implement the Scheduler dashboard UI

**Files:**
- Modify: `frontend/app/(app)/scheduler/page.tsx`
- Modify: `frontend/app/(app)/scheduler/components/resource-gauges.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`

**Step 1: Implement the top operational summary**

Render:
- effective scheduler badge
- configured mode
- worker count
- queue depth
- last refresh timestamp

**Step 2: Add a health / explanation panel**

Explain:
- persistent scheduler is active
- or fallback mode is in effect
- or scheduler resource checks are disabled/unavailable

**Step 3: Upgrade queue cards and task summary**

Show:
- queued, dispatched, completed, failed
- a short sentence for each metric
- a compact “what to do with this page” explanation

**Step 4: Upgrade system resource section**

Show:
- snapshot timestamp
- availability status
- CPU / memory / disk / GPU summary
- friendly cross-platform-compatible empty states when data is unavailable

**Step 5: Re-run the page tests**

Run: `bun run test tests/integration/pages/scheduler-page.test.tsx`

### Task 4: Verify no obvious backend/frontend regressions

**Files:**
- Test only

**Step 1: Run backend scheduler API tests**

Run: `uv run pytest tests/test_api/test_scheduler_api.py -q`

**Step 2: Run frontend scheduler page tests**

Run: `bun run test tests/integration/pages/scheduler-page.test.tsx`

**Step 3: Optionally run one nearby dashboard test if needed**

Only if the scheduler type change affects dashboard rendering.

**Step 4: Summarize changed files and test commands**

Include the final modified file list and exact verification commands.
