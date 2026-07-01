# Agent Code Blocks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make future Bioinfoflow agent replies render standard Markdown fenced code blocks as polished chat code blocks, and nudge the agent to emit fenced blocks for commands, logs, directory trees, scripts, and structured data.

**Architecture:** Keep Markdown parsing in the existing `MarkdownRenderer`. Improve the existing fenced-code path only; do not add broad heuristic detection for ordinary prose. Add stable prompt guidance in the agent-core system prompt so new and existing sessions receive the formatting fix through the prompt resolver.

**Tech Stack:** React 19, Next.js 16, `react-markdown`, `remark-gfm`, Shiki, Vitest, FastAPI/Python backend prompt tests.

---

### Task 1: Frontend Code Block Contract

**Files:**
- Modify: `frontend/components/bioinfoflow/markdown-renderer.tsx`
- Test: `frontend/tests/unit/components/markdown-renderer.test.tsx`

- [ ] **Step 1: Write the failing tests**

Add tests that render fenced Markdown and assert:
- one `data-testid="markdown-code-block"` container is produced;
- the language label is visible for fenced code;
- the code text preserves multiple lines and indentation;
- the block exposes a copy button that writes the raw code text to `navigator.clipboard.writeText`.

- [ ] **Step 2: Run the focused test to verify RED**

Run from `frontend/`:

```bash
rtk bun run test tests/unit/components/markdown-renderer.test.tsx
```

Expected: FAIL because either the test file is new or the copy button behavior is missing.

- [ ] **Step 3: Implement the minimal UI**

Update `CodeBlock` in `frontend/components/bioinfoflow/markdown-renderer.tsx` to keep the existing Shiki path, add an icon-only copy button with tooltip/accessible label, and ensure raw fallback and highlighted output both keep horizontal scrolling and full code text.

- [ ] **Step 4: Run the focused test to verify GREEN**

Run from `frontend/`:

```bash
rtk bun run test tests/unit/components/markdown-renderer.test.tsx
```

Expected: PASS.

### Task 2: Agent Output Formatting Guidance

**Files:**
- Modify: `backend/app/services/agent_core/context/system_prompt.py`
- Test: `backend/tests/test_agent_core/test_harness_invariants.py`

- [ ] **Step 1: Write the failing tests**

Add assertions that the default system prompt tells the agent to use fenced Markdown code blocks for multi-line commands, logs, directory trees, scripts, and JSON/YAML, and that it does not suggest front-end auto-detection.

- [ ] **Step 2: Run the focused backend test to verify RED**

Run from `backend/`:

```bash
rtk uv run pytest tests/test_agent_core/test_harness_invariants.py
```

Expected: FAIL because the new formatting guidance is not present yet.

- [ ] **Step 3: Add narrow prompt guidance**

Add a short "Response formatting" section to `_SYSTEM_PROMPT` in `backend/app/services/agent_core/context/system_prompt.py`. Require fenced Markdown blocks with a language tag such as `text`, `bash`, `json`, `yaml`, or `python` for multi-line preformatted output.

- [ ] **Step 4: Run the focused backend test to verify GREEN**

Run from `backend/`:

```bash
rtk uv run pytest tests/test_agent_core/test_harness_invariants.py
```

Expected: PASS.

### Task 3: Integration Verification

**Files:**
- Modify only if tests expose a small issue in Task 1 or Task 2.

- [ ] **Step 1: Run frontend checks**

Run from `frontend/`:

```bash
rtk bun run lint
rtk bun run test
```

- [ ] **Step 2: Run backend checks**

Run from `backend/`:

```bash
rtk uv run pytest tests/test_agent_core/test_harness_invariants.py
rtk uv run ruff check app/services/agent_core/context/system_prompt.py tests/test_agent_core/test_harness_invariants.py
```

- [ ] **Step 3: Review**

Dispatch parallel review agents against the final diff. Fix Critical and Important findings, then rerun the affected checks.
