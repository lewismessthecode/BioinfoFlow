# Agent Tool Hard Deletion and Runtime Risk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permanently delete the retired Agent tool surface, replace brittle shell-risk fallthroughs with effect-based semantics, make Bubblewrap genuinely usable in Docker, and represent non-zero Bash exits as failures end to end.

**Architecture:** Registration is the sole source of truth for callable tools; retired names have no providers, implementations, aliases, or exposure filters. Shell parsing produces one semantic assessment consumed by risk and audit logic, while permission policy remains separate. Bubblewrap availability means a cached functional namespace probe succeeds. Tool implementations may report domain-level result failures through a generic hook so the executor persists and emits the correct lifecycle state.

**Tech Stack:** Python 3.12, FastAPI service layer, pytest, Bubblewrap, Docker Compose, TypeScript, React, Vitest.

---

## File map

- Delete retired Agent tool modules under `backend/app/services/agent_core/tools/attachments/`, `search/`, and `platform/images.py`.
- Narrow `backend/app/services/agent_core/tools/files/resources.py` to `write` and `edit` only.
- Make `providers.py`, package exports, `registry.py`, and `toolsets.py` express one callable surface without aliases or retired filters.
- Refactor semantics in `permissions/command_risk.py`; keep approval decisions in `permissions/policy.py`.
- Make `sandbox/process_sandbox.py` prove Bubblewrap usability and build the required user-namespace argv; make `docker-compose.yml` provide the required seccomp contract.
- Add a generic result-error hook in `tools/specs.py`/`tools/executor.py`; implement it for Bash in `tools/execution/shell.py`.
- Add a frontend historical-data guard in `frontend/lib/agent-runtime/tool-activity.ts` without adding a second status protocol.

### Task 1: Hard-delete retired tools and aliases

**Files:**
- Delete: `backend/app/services/agent_core/tools/attachments/__init__.py`
- Delete: `backend/app/services/agent_core/tools/attachments/resources.py`
- Delete: `backend/app/services/agent_core/tools/search/__init__.py`
- Delete: `backend/app/services/agent_core/tools/search/glob.py`
- Delete: `backend/app/services/agent_core/tools/search/grep.py`
- Delete: `backend/app/services/agent_core/tools/platform/images.py`
- Delete: `backend/tests/test_agent_core/test_attachment_tools.py`
- Delete: `backend/tests/test_agent_core/test_tools/test_file_patch.py`
- Delete: `backend/tests/test_agent_core/test_tools/test_search.py`
- Modify: `backend/app/services/agent_core/tools/files/resources.py`
- Modify: `backend/app/services/agent_core/tools/files/__init__.py`
- Modify: `backend/app/services/agent_core/tools/platform/__init__.py`
- Modify: `backend/app/services/agent_core/tools/providers.py`
- Modify: `backend/app/services/agent_core/tools/registry.py`
- Modify: `backend/app/services/agent_core/tools/toolsets.py`
- Test: `backend/tests/test_agent_core/test_toolsets.py`
- Test: `backend/tests/test_agent_core/test_harness_invariants.py`
- Test: `backend/tests/test_agent_core/test_tools/test_interaction.py`
- Test: `backend/tests/test_agent_core/test_tools/test_platform_resources.py`
- Test: `backend/tests/test_agent_core/test_tools/test_platform_capability_tools.py`

- [ ] **Step 1: Write failing registry tests**

  Add one canonical retired-name set and assert it is disjoint from
  `build_default_tool_registry().names()`. Replace alias compatibility assertions
  with `pytest.raises(NotFoundError, match="Agent tool not found")` for
  `files.write` and `files.edit`. Change the persisted historical action test to
  assert resume fails through the same unknown-tool path.

- [ ] **Step 2: Verify RED**

  Run from `backend/`:

  ```bash
  rtk uv run pytest tests/test_agent_core/test_toolsets.py tests/test_agent_core/test_harness_invariants.py tests/test_agent_core/test_tools/test_interaction.py -q
  ```

  Expected: failures show retired names remain registered and aliases still resolve.

- [ ] **Step 3: Delete production compatibility code**

  Remove retired imports/instances from `default_tool_providers()`. Delete the
  retired modules. In `AgentToolRegistry.get`, use only `self._tools.get(name)`.
  Delete `_HISTORICAL_TOOL_ALIASES`, `_RETIRED_MODEL_TOOL_NAMES`,
  `_RETIRED_MODEL_TOOL_PREFIXES`, `_is_retired_model_tool`, and the final retired
  subtraction. Delete `ReadFileTool`, `ApplyPatchTool`, and patch-only helpers
  while preserving `WriteFileTool`, `EditFileTool`, and their write-path helper.

- [ ] **Step 4: Delete dedicated tests and narrow mixed tests**

  Remove tests whose subject no longer exists. In mixed platform tests, remove
  only Agent-side `images.*` cases and imports; retain product Image API/service
  tests outside Agent tools. Keep `grep`/`glob` strings that refer to legitimate
  Bash commands or generic historical transcript rendering rather than callable
  tool compatibility.

- [ ] **Step 5: Verify GREEN and dead-code absence**

  ```bash
  rtk uv run pytest tests/test_agent_core/test_toolsets.py tests/test_agent_core/test_harness_invariants.py tests/test_agent_core/test_tools/test_interaction.py tests/test_agent_core/test_tools/test_platform_resources.py tests/test_agent_core/test_tools/test_platform_capability_tools.py -q
  rtk rg -n 'files\.read|files\.apply_patch|attachments\.(read|search)|_HISTORICAL_TOOL_ALIASES|files\.write|files\.edit|name="(glob|grep)"|name="images\.' app/services/agent_core tests/test_agent_core
  ```

  Expected: tests pass; search returns only intentional negative regression data,
  historical display fixtures, or no matches—never registration, alias, export,
  implementation, or dedicated implementation tests.

- [ ] **Step 6: Commit**

  ```bash
  rtk git add -A
  rtk git commit -m "refactor: delete retired agent tools"
  ```

### Task 2: Unify semantic command-risk inference

**Files:**
- Modify: `backend/app/services/agent_core/permissions/command_risk.py`
- Test: `backend/tests/test_agent_core/test_command_risk.py`
- Test: `backend/tests/test_agent_core/test_permission_context.py`

- [ ] **Step 1: Add failing semantic introspection tests**

  Add table cases proving `python3 --version`, `python -V`, `node --version`, and
  trusted `--help` forms are `act_low` with read/introspection semantics. Add
  negative cases proving unknown `dangercli --version`, inline code, script
  operands, redirects, pipelines, substitutions, and compound commands cannot
  use the proof. Preserve critical hardline expectations.

- [ ] **Step 2: Verify RED**

  ```bash
  rtk uv run pytest tests/test_agent_core/test_command_risk.py -q
  ```

  Expected: `python3 --version` fails because it falls through to unknown
  executable `act_high` and effects do not describe read-only introspection.

- [ ] **Step 3: Introduce one semantic result**

  Add an internal immutable semantic value containing effects, confidence,
  reasons, paths, and hardline facts. Organize inspectors by behavior in this
  order: hardline; dynamic shell structure; write redirects; delete/process/
  privilege/network; code execution; proven introspection/read; unknown. Make
  `classify_command_level()` and `assess_command_risk()` consume the same
  semantics rather than independently calling `_classify_node()` and
  `_command_effects()`.

- [ ] **Step 4: Implement generic introspection proof**

  Use declarative trusted executable/family metadata. Accept only one simple
  node whose operands are exclusively version/help flags. Reject redirects,
  pipes, substitutions, inline-source flags, modules, scripts, stdin programs,
  and positional operands. Do not add a `python3`-specific branch.

- [ ] **Step 5: Verify GREEN and regression behavior**

  ```bash
  rtk uv run pytest tests/test_agent_core/test_command_risk.py tests/test_agent_core/test_permission_context.py -q
  ```

  Expected: all semantic and historical permission-context tests pass.

- [ ] **Step 6: Commit**

  ```bash
  rtk git add backend/app/services/agent_core/permissions/command_risk.py backend/tests/test_agent_core/test_command_risk.py backend/tests/test_agent_core/test_permission_context.py
  rtk git commit -m "refactor: derive shell risk from command effects"
  ```

### Task 3: Make Bubblewrap availability truthful in Docker

**Files:**
- Modify: `backend/app/services/agent_core/sandbox/process_sandbox.py`
- Modify: `docker-compose.yml`
- Modify: `docs/getting-started/docker.md`
- Test: `backend/tests/test_agent_core/test_sandbox.py`
- Test: `backend/tests/test_local_first_run.py`

- [ ] **Step 1: Add failing adapter and deployment tests**

  Assert Bubblewrap argv begins with `bwrap --unshare-user --uid 0 --gid 0`
  before mount operations. Add functional-probe tests for missing binary,
  successful probe, non-zero probe, and timeout. Add a Compose contract asserting
  `backend.security_opt == ["seccomp:unconfined"]`, `privileged` is absent/false,
  and `SYS_ADMIN` is not added.

- [ ] **Step 2: Verify RED**

  ```bash
  rtk uv run pytest tests/test_agent_core/test_sandbox.py tests/test_local_first_run.py -q
  ```

  Expected: argv and Compose contract fail; binary presence currently passes as
  availability without a namespace probe.

- [ ] **Step 3: Implement minimal namespace contract**

  Add the user-namespace flags to `BubblewrapAdapter.build_argv()`. Replace the
  binary-only availability check with a bounded, cached minimal namespace probe
  whose failure returns false. Keep `SandboxRunner` fail-closed. Add only
  `security_opt: ["seccomp:unconfined"]` to the backend service; do not add
  privileged mode or `SYS_ADMIN`.

- [ ] **Step 4: Update deployment documentation and verify GREEN**

  Document the required non-privileged namespace contract and the functional
  health check.

  ```bash
  rtk uv run pytest tests/test_agent_core/test_sandbox.py tests/test_local_first_run.py tests/test_dockerfile_packaging.py -q
  rtk docker compose config
  ```

  Expected: tests pass and rendered Compose contains seccomp unconfined while
  omitting privileged and `SYS_ADMIN`.

- [ ] **Step 5: Commit**

  ```bash
  rtk git add backend/app/services/agent_core/sandbox/process_sandbox.py backend/tests/test_agent_core/test_sandbox.py backend/tests/test_local_first_run.py docker-compose.yml docs/getting-started/docker.md
  rtk git commit -m "fix: make bubblewrap namespace setup usable"
  ```

### Task 4: Persist non-zero Bash exits as failures

**Files:**
- Modify: `backend/app/services/agent_core/tools/specs.py`
- Modify: `backend/app/services/agent_core/tools/executor.py`
- Modify: `backend/app/services/agent_core/tools/execution/shell.py`
- Test: `backend/tests/test_agent_core/test_tools/test_execution_shell.py`
- Test: `frontend/lib/agent-runtime/tool-activity.ts`
- Test: `frontend/tests/unit/lib/agent-runtime/tool-activity.test.ts`
- Test: `frontend/tests/unit/components/agent-transcript.test.tsx`

- [ ] **Step 1: Add failing backend lifecycle tests**

  Execute a deterministic non-zero command and assert failed status, preserved
  structured result, normalized error with exit code, `action.failed` rather
  than `action.completed`, and transcript `is_error == true`.

- [ ] **Step 2: Verify backend RED**

  ```bash
  rtk uv run pytest tests/test_agent_core/test_tools/test_execution_shell.py -q
  ```

  Expected: the action is currently persisted as completed.

- [ ] **Step 3: Add a generic result-semantic hook and implement Bash failure**

  Extend the `AgentTool` protocol with an optional/default result-validation
  contract that returns a normalized domain error or `None`. Invoke it after
  output-schema validation and before the completed transition. On a domain
  error, persist both result and error, emit `ACTION_FAILED`, and return a failed
  `ToolExecutionResult`. Implement the hook on `ExecuteShellTool` for
  `exit_code != 0`; do not hardcode `tool_name == "bash"` in the executor.

- [ ] **Step 4: Verify backend GREEN**

  ```bash
  rtk uv run pytest tests/test_agent_core/test_tools/test_execution_shell.py tests/test_agent_core/test_approval_idempotency.py -q
  ```

- [ ] **Step 5: Add failing frontend historical-event tests**

  Assert an `action.completed` event carrying `exit_code: 13` is normalized to
  failed, and the transcript renders `Failed`, stderr, and the exit code.

- [ ] **Step 6: Verify frontend RED**

  From `frontend/`:

  ```bash
  rtk bun install
  rtk bun run test --run tests/unit/lib/agent-runtime/tool-activity.test.ts tests/unit/components/agent-transcript.test.tsx
  ```

  Expected: status remains completed before the compatibility display guard.

- [ ] **Step 7: Add the narrow frontend guard and verify GREEN**

  In the activity reducer, if the normalized structured result contains a
  numeric non-zero exit code, derive `failed` regardless of a historical
  completed lifecycle event. Do not introduce aliases or rewrite stored events.

  ```bash
  rtk bun run test --run tests/unit/lib/agent-runtime/tool-activity.test.ts tests/unit/components/agent-transcript.test.tsx
  ```

- [ ] **Step 8: Commit**

  ```bash
  rtk git add backend/app/services/agent_core/tools/specs.py backend/app/services/agent_core/tools/executor.py backend/app/services/agent_core/tools/execution/shell.py backend/tests/test_agent_core/test_tools/test_execution_shell.py frontend/lib/agent-runtime/tool-activity.ts frontend/tests/unit/lib/agent-runtime/tool-activity.test.ts frontend/tests/unit/components/agent-transcript.test.tsx
  rtk git commit -m "fix: mark nonzero bash exits as failed"
  ```

### Task 5: Whole-change verification and documentation consistency

**Files:**
- Modify as required: `docs/architecture.md`
- Modify as required: `docs/contracts/behavior-contracts.md`
- Modify as required: `docs/reference/architecture.md`
- Modify as required: `docs/reference/glossary.md`
- Modify as required: `docs/security.md`

- [ ] **Step 1: Search for stale executable compatibility claims**

  Remove documentation that claims retired tools remain registered, callable,
  or available through aliases. Preserve references to product image management
  and legitimate Bash `grep`/glob operations.

- [ ] **Step 2: Run full backend verification**

  From `backend/`:

  ```bash
  rtk uv run pytest
  rtk uv run ruff check .
  ```

- [ ] **Step 3: Run full frontend verification**

  From `frontend/`:

  ```bash
  rtk bun run lint
  rtk bun run test
  rtk bun run lint:dead-code
  ```

- [ ] **Step 4: Run repository checks**

  From the repository root:

  ```bash
  rtk git diff --check
  rtk git status --short
  ```

- [ ] **Step 5: Commit final cleanup**

  ```bash
  rtk git add -A
  rtk git commit -m "docs: align agent runtime contracts"
  ```

### Task 6: Review, rebase, PR, and rebase auto-merge

- [ ] **Step 1: Run specification-compliance and code-quality reviews**

  Review each task against this plan, fix every Critical/Important issue, and
  re-review until approved. Then run a final whole-change review against the
  design document.

- [ ] **Step 2: Rebase onto current main and rerun affected verification**

  ```bash
  rtk git fetch origin --prune
  rtk git rebase origin/main
  ```

- [ ] **Step 3: Push and create the PR**

  ```bash
  rtk git push -u origin codex/remove-retired-agent-tools
  rtk gh pr create --title "refactor: delete retired agent tools and fix runtime semantics" --body-file <prepared-pr-body>
  ```

- [ ] **Step 4: Enable rebase auto-merge**

  ```bash
  rtk gh pr merge --auto --rebase <PR-number>
  ```

  If repository policy rejects rebase auto-merge, record the exact GitHub error
  and do not silently choose a different merge method.

