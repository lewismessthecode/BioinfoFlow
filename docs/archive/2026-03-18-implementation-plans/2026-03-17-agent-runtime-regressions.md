# Agent Runtime Regressions Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the runtime-v2 regressions that broke second-turn agent messages for Gemini/OpenAI and degraded plan-card metadata for demo workflow proposals.

**Architecture:** Keep the fix local to the runtime-v2 path. Update the LangChain adapter to avoid constructing invalid `AIMessage` objects for assistant history without tool calls, and restore rich plan metadata generation in the runtime loop so the frontend receives the same file/reference/sample details it relied on before the refactor.

**Tech Stack:** FastAPI, LangChain Core, pytest, TypeScript frontend consuming agent plan metadata

### Task 1: Reproduce and lock the LangChain history regression

**Files:**
- Modify: `backend/tests/test_agent/test_runtime/test_llm_client.py`
- Modify: `backend/app/services/agent/runtime/llm_client.py`

**Step 1: Write the failing test**

Add a regression test that feeds `_call_langchain()` an assistant history item containing only text blocks and verifies the call succeeds instead of raising a Pydantic validation error.

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_agent/test_runtime/test_llm_client.py -v`
Expected: FAIL with `ValidationError` for `AIMessage.tool_calls`

**Step 3: Write minimal implementation**

Construct `AIMessage` without a `tool_calls` argument when there are no tool calls in the assistant message history.

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_agent/test_runtime/test_llm_client.py -v`
Expected: PASS

### Task 2: Reproduce and lock the plan-card metadata regression

**Files:**
- Modify: `backend/tests/test_agent/test_runtime/test_loop.py`
- Modify: `backend/app/services/agent/runtime/loop.py`

**Step 1: Write the failing test**

Add a regression test that runs `agent_loop()` with a demo workflow proposal response and asserts the emitted `plan` event includes:
- workflow display name
- reference accession
- sample/resources summary
- input files with concrete demo paths

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_agent/test_runtime/test_loop.py -v`
Expected: FAIL because `metadata.files` is empty or missing expected paths/details

**Step 3: Write minimal implementation**

Restore rich plan metadata extraction in runtime-v2 by parsing the proposal text and enriching it with demo catalog data where possible.

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_agent/test_runtime/test_loop.py -v`
Expected: PASS

### Task 3: Verify the integrated fix

**Files:**
- Modify: `backend/tests/test_api/test_agent_api.py` if an end-to-end regression test is needed after the unit fixes

**Step 1: Run focused backend coverage**

Run: `cd backend && uv run pytest tests/test_agent/test_runtime/test_llm_client.py tests/test_agent/test_runtime/test_loop.py tests/test_api/test_agent_api.py -v`
Expected: PASS

**Step 2: Run broader relevant suites**

Run: `cd backend && uv run pytest tests/test_agent/test_runtime -v`
Expected: PASS

### Task 4: Finish the branch

**Files:**
- Review: `git diff -- backend/app/services/agent/runtime/llm_client.py backend/app/services/agent/runtime/loop.py backend/tests/test_agent/test_runtime/test_llm_client.py backend/tests/test_agent/test_runtime/test_loop.py`

**Step 1: Confirm verification evidence**

Run the focused test commands above and confirm they pass cleanly.

**Step 2: Commit**

Run:

```bash
git add docs/plans/2026-03-17-agent-runtime-regressions.md \
  backend/app/services/agent/runtime/llm_client.py \
  backend/app/services/agent/runtime/loop.py \
  backend/tests/test_agent/test_runtime/test_llm_client.py \
  backend/tests/test_agent/test_runtime/test_loop.py
git commit -m "fix: restore agent runtime follow-up turns"
```
