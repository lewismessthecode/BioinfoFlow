# Project Environment Prompt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require new BioinfoFlow agent sessions to inspect and reuse project environments and package managers, with `uv` and Bun as evidence-free defaults.

**Architecture:** Extend the existing provider-neutral stable system prompt and bump its immutable snapshot version. Strengthen the existing harness invariant test; do not add runtime detection, command rewriting, configuration, or UI.

**Tech Stack:** Python 3.13, pytest, Ruff, AgentCore prompt snapshots

---

### Task 1: Add the project environment contract

**Files:**
- Modify: `backend/tests/test_agent_core/test_harness_invariants.py`
- Modify: `backend/app/services/agent_core/context/system_prompt.py`

- [ ] **Step 1: Write the failing prompt invariant assertions**

Rename the v10 test to v11, expect the new snapshot ID, add the new section to
`required_sections`, and add these strings to `required_guidance`:

```python
"Never install project dependencies into the system Python",
"default to uv and a project-local `.venv`",
"default to Bun",
"Do not create a competing environment or lockfile",
"Use the selected manager consistently",
"`uv run` and `bun run`",
"report the environment and package manager used",
```

Update the session-creation assertion from `bioinfoflow-agent-v10` to
`bioinfoflow-agent-v11`.

- [ ] **Step 2: Run the focused test and verify RED**

Run from `backend/`:

```bash
rtk uv run pytest tests/test_agent_core/test_harness_invariants.py -q
```

Expected: FAIL because the default snapshot remains v10 and the prompt lacks
the new section and guidance.

- [ ] **Step 3: Implement the minimal stable prompt change**

Change:

```python
PROMPT_SNAPSHOT_ID = "bioinfoflow-agent-v11"
```

Add `## Project environments and package managers` before the existing
`## Bioinfoflow platform operations` section. The section must require
inspection before environment-dependent work, reuse established project
choices, prohibit system-Python installation by default, preserve explicit
user/project overrides, define `uv` plus `.venv` and Bun fallbacks, use the
selected manager consistently, prefer explicit runners, resolve conflicts
against the relevant project directory, and report the chosen environment.

- [ ] **Step 4: Run focused verification and verify GREEN**

Run from `backend/`:

```bash
rtk uv run pytest tests/test_agent_core/test_harness_invariants.py -q
rtk uv run ruff check app/services/agent_core/context/system_prompt.py tests/test_agent_core/test_harness_invariants.py
```

Expected: both commands PASS.

- [ ] **Step 5: Run broader verification**

Run from `backend/`:

```bash
rtk uv run pytest tests/test_agent_core -q
rtk uv run ruff check .
```

Then run from the repository root:

```bash
rtk git diff --check
```

Expected: all commands PASS.

- [ ] **Step 6: Review and commit the implementation**

Inspect the final diff for unrelated changes and commit:

```bash
rtk git add backend/app/services/agent_core/context/system_prompt.py backend/tests/test_agent_core/test_harness_invariants.py docs/plans/2026-07-27-project-environment-prompt-implementation.md
rtk git commit -m "fix: enforce project environment defaults"
```

- [ ] **Step 7: Publish and enable automerge**

Rebase onto the current remote default branch, rerun focused verification if
the rebase changes files, push the branch, create a ready PR titled
`fix: enforce project environment defaults`, and enable squash automerge.
