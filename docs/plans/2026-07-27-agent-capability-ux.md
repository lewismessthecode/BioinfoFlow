# Agent Capability UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give normal execution sessions the BioinfoFlow lifecycle tools they need, clearly mark product source as unavailable, and stop advertising nonexistent skills.

**Architecture:** Keep one Agent-facing platform interface: the existing structured BioinfoFlow tools. Canonicalize execution-mode policy at session boundaries, add one local environment instruction, and filter `skills.load` from model-visible schemas when the configured registry is empty.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, pytest, Ruff

---

### Task 1: Canonical execution capabilities

**Files:**
- Modify: `backend/app/services/agent_core/tools/toolsets.py`
- Modify: `backend/app/services/agent_core/service.py`
- Modify: `backend/app/api/v1/agent.py`
- Test: `backend/tests/test_agent_core/test_toolsets.py`
- Test: `backend/tests/test_agent_core/test_harness_invariants.py`
- Test: `backend/tests/test_api/test_agent_core_api.py`

- [ ] **Step 1: Write failing policy tests**

Update the execution-toolset assertion so the canonical policy exposes at least
`workflows.create`, `projects.workflows.bind`, `runs.submit`, `runs.inspect`, and
`workflows.inspect`. Add assertions that a newly created session and an API-created
execution session persist:

```python
{
    "name": "execution",
    "capabilities": ["bioinfo.read", "bioinfo.manage"],
}
```

- [ ] **Step 2: Verify the tests fail for the missing capabilities**

Run:

```bash
rtk uv run pytest tests/test_agent_core/test_toolsets.py tests/test_agent_core/test_harness_invariants.py tests/test_api/test_agent_core_api.py -q
```

Expected: failures show that execution currently persists only `{"name": "execution"}` and does not expose platform mutation tools.

- [ ] **Step 3: Implement the minimal canonical policy**

Set `EXECUTION_TOOLSET_POLICY` to:

```python
EXECUTION_TOOLSET_POLICY = {
    "name": "execution",
    "capabilities": ["bioinfo.read", "bioinfo.manage"],
}
```

When API session creation or session mode updates select `execution`, use this
constant rather than reconstructing `{"name": "execution"}`. Preserve the
existing explicit policy paths used by tests, subagents, and compatibility callers.

- [ ] **Step 4: Verify the policy tests pass**

Run the command from Step 2. Expected: all selected tests pass.

- [ ] **Step 5: Commit the task**

```bash
rtk git add backend/app/services/agent_core/tools/toolsets.py backend/app/services/agent_core/service.py backend/app/api/v1/agent.py backend/tests/test_agent_core/test_toolsets.py backend/tests/test_agent_core/test_harness_invariants.py backend/tests/test_api/test_agent_core_api.py
rtk git commit -m "fix: expose platform lifecycle tools to agents"
```

### Task 2: Product-source boundary guidance

**Files:**
- Modify: `backend/app/services/agent_core/context/assembler.py`
- Test: `backend/tests/test_agent_core/test_project_instructions.py`

- [ ] **Step 1: Write failing local/remote context tests**

For a local session, assert the environment context contains:

```text
BioinfoFlow product source is not part of this workspace. Do not inspect it or invoke `bif`; use the exposed BioinfoFlow platform tools.
```

For a remote SSH target, assert that local product-source guidance is absent.

- [ ] **Step 2: Verify the tests fail because the guidance is missing**

Run:

```bash
rtk uv run pytest tests/test_agent_core/test_project_instructions.py -q
```

Expected: the new local assertion fails while existing context tests remain green.

- [ ] **Step 3: Add the minimal local environment line**

Append the exact guidance sentence inside the existing `if not remote_target`
environment block. Do not modify the stable system prompt or add source-path
details.

- [ ] **Step 4: Verify the context tests pass**

Run the command from Step 2. Expected: all tests pass.

- [ ] **Step 5: Commit the task**

```bash
rtk git add backend/app/services/agent_core/context/assembler.py backend/tests/test_agent_core/test_project_instructions.py
rtk git commit -m "fix: clarify the agent product-source boundary"
```

### Task 3: Truthful skill availability

**Files:**
- Modify: `backend/app/services/agent_core/core/loop.py`
- Modify: `backend/app/services/agent_core/tools/toolsets.py`
- Modify: `backend/app/services/agent_core/tools/skills/resources.py`
- Test: `backend/tests/test_agent_core/test_toolsets.py`
- Test: `backend/tests/test_agent_core/test_skills_plugins.py`
- Test: `backend/tests/test_agent_core/test_model_runtime_integration.py`

- [ ] **Step 1: Write failing skill-availability tests**

Add a toolset test for model-visible specs:

```python
assert "skills.load" not in {
    spec.name
    for spec in exposure.exposed_specs(
        policy={"name": "execution"},
        skills_available=False,
    )
}
```

Add the matching `skills_available=True` assertion. Add a runtime integration
test with an empty configured skill directory that captures the model invocation
and asserts `skills.load` is absent. Add a skill resource test showing a missing
name reports an installed skill name in the error text.

- [ ] **Step 2: Verify the tests fail for current unconditional exposure/error**

Run:

```bash
rtk uv run pytest tests/test_agent_core/test_toolsets.py tests/test_agent_core/test_skills_plugins.py tests/test_agent_core/test_model_runtime_integration.py -q
```

Expected: `exposed_specs` rejects the new argument or still returns
`skills.load`, and missing skill errors omit available names.

- [ ] **Step 3: Implement minimal model-visible filtering**

Add an optional keyword to `ToolsetExposure.exposed_specs`:

```python
skills_available: bool = True
```

After resolving names, discard `skills.load` when `skills_available` is false.
In the Agent loop, evaluate `bool(AgentSkillRegistry.from_default_roots().list())`
once per model iteration and pass it to `exposed_specs`. Do not alter callable
tool authorization or active-skill context assembly.

In `LoadSkillTool.run`, catch the missing-name error and re-raise it with either
`Available agent skills: <sorted names>` or `No agent skills are currently available.`

- [ ] **Step 4: Verify the focused skill tests pass**

Run the command from Step 2. Expected: all selected tests pass.

- [ ] **Step 5: Commit the task**

```bash
rtk git add backend/app/services/agent_core/core/loop.py backend/app/services/agent_core/tools/toolsets.py backend/app/services/agent_core/tools/skills/resources.py backend/tests/test_agent_core/test_toolsets.py backend/tests/test_agent_core/test_skills_plugins.py backend/tests/test_agent_core/test_model_runtime_integration.py
rtk git commit -m "fix: advertise only available agent skills"
```

### Task 4: Full verification and documentation check

**Files:**
- Verify: all files changed in Tasks 1-3
- Verify: `docs/plans/2026-07-27-agent-capability-ux-design.md`
- Verify: `docs/plans/2026-07-27-agent-capability-ux.md`

- [ ] **Step 1: Run the full AgentCore suite**

```bash
rtk uv run pytest tests/test_agent_core -q
```

Expected: all AgentCore tests pass.

- [ ] **Step 2: Run backend lint**

```bash
rtk uv run ruff check .
```

Expected: exit code 0.

- [ ] **Step 3: Check formatting and whitespace**

```bash
rtk git diff --check origin/main...HEAD
```

Expected: no output and exit code 0.

- [ ] **Step 4: Review the complete diff against the design**

```bash
rtk git diff --stat origin/main...HEAD
rtk git diff origin/main...HEAD
```

Confirm there is no localhost access, CLI packaging, shell parsing, sandbox
change, UI configuration, or unrelated refactor.
