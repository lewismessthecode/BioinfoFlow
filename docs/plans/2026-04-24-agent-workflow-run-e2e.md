# Agent Workflow Run E2E Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add the remaining highest-value browser coverage by proving the Agent can use a project-scoped workflow and queue a run through the real approval flow.

**Architecture:** Reuse the existing deterministic Playwright agent runtime instead of real provider APIs, but drive the real `/agent/message` + SSE + approval + run creation stack. Register and bind a real workflow through the UI first, then let the deterministic test client call real `platform_*` tools so the browser test covers genuine product wiring instead of mocked SSE.

**Tech Stack:** Playwright, FastAPI agent runtime, deterministic `LLMClient` test mode, Next.js App Router, project/workflow/run service layer.

### Task 1: Add the failing agent workflow-run E2E

**Files:**
- Modify: `frontend/tests/e2e/pages/agent-page.ts`
- Modify: `frontend/tests/e2e/pages/workflows-page.ts`
- Create: `frontend/tests/e2e/agent-workflow-run.spec.ts`

**Step 1: Write the failing test**

Cover this user path:
- create project
- register local workflow from the real Workflows page
- add the workflow to the project
- open Agent
- ask the agent to run the project workflow
- approve the run
- verify the agent reports the queued run
- verify the Runs page shows the new run

**Step 2: Run only the new spec and verify RED**

Run: `cd frontend && bunx playwright test tests/e2e/agent-workflow-run.spec.ts --project=chromium`

Expected: FAIL because the deterministic test runtime does not yet know how to drive this workflow/run scenario, or because the UI contract is wrong.

### Task 2: Extend deterministic agent runtime support

**Files:**
- Modify: `backend/app/services/agent/runtime/llm_client.py`

**Step 1: Implement the smallest deterministic scenario**

Teach the Playwright-only test client to:
- detect the dedicated workflow-run prompt
- call `platform_workflow_project_list`
- parse the returned workflow id from the tool result
- call `platform_run_submit`
- return final assistant text after the approved tool completes

**Step 2: Keep the scope narrow**

Do not add generic fake agent behavior. Only support the exact scenario needed for the new E2E and keep it gated to `PYTEST_CURRENT_TEST == "playwright-e2e"`.

### Task 3: Verify and leave the remaining gap list honest

**Files:**
- Update: `docs/plans/2026-04-23-high-value-test-expansion.md` only if the remaining-gap summary changes materially

**Step 1: Run focused verification**

Run:
- `cd frontend && bunx playwright test tests/e2e/agent-workflow-run.spec.ts --project=chromium`
- `cd frontend && bunx playwright test tests/e2e/agent-first-analysis.spec.ts tests/e2e/workflow-run-path.spec.ts --project=chromium`
- `cd frontend && bun run test -- tests/integration/pages/agent-capabilities.test.tsx`

**Step 2: If a real bug appears, fix product code rather than weakening the test**

**Step 3: Report any still-open high-priority gaps explicitly**
