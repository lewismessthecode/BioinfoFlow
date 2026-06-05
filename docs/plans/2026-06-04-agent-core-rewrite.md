# BioInfoFlow AgentCore Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the legacy BioInfoFlow agent with a new AgentCore runtime that keeps Codex/Claude Code style harness capabilities while exposing BioInfoFlow projects, data, workflows, images, runs, logs, results, permissions, memory, skills, plugins, and LLM providers as typed, auditable platform capabilities.

**Architecture:** This is a destructive replacement, not a compatibility refactor. The new source of truth is `AgentSession`, `AgentTurn`, `AgentEvent`, `AgentAction`, `AgentArtifact`, and `AgentMemory`; all observable output is event-ledger-first, and all side effects are action-ledger-first. Provider/model catalog belongs to a platform-level `llm` module; bioinformatics intelligence belongs to deterministic domain services that AgentCore calls through typed tools.

**Tech Stack:** FastAPI, async SQLAlchemy, Alembic, Typer CLI, SSE, SQLite, Next.js App Router, React, Tailwind, Vitest, Playwright, pytest, ruff.

---

## Plan Persistence And Resume Contract

This file is the canonical local execution plan for the AgentCore rewrite. It incorporates the user requirements, the Claude Code plan at `/Users/lewisliu/.claude/plans/effort-radiant-cookie.md`, and the Codex implementation checkpoints recorded during this worktree session.

If context is compacted, the model is switched, or execution resumes in a different mode, continue from this file instead of reconstructing the plan from chat memory. The authoritative next step is the `Next Resume Point` section near the end of this document.

Current resume target:

- Continue on branch `codex/agent-core-rewrite`.
- Phase 9 frontend replacement is functionally complete.
- Phase 10 CLI migration is functionally complete.
- Phase 11 backend delegacy cleanup is functionally complete for production runtime paths: old `app.services.agent`, `app.services.hermes_service`, old conversation/message/approval/trace ORM/schema/repository files, old backend agent/Hermes tests, and Hermes startup lifecycle hooks have been removed or converted into guard/tombstone coverage.
- Phase 11 frontend legacy renderer cleanup, backend legacy/Hermes config cleanup, and old agent table drop migration are functionally complete.
- Final backend/frontend/migration/diff verification has passed and is recorded in `Final Verification Snapshot`.
- Final legacy-reference audit has passed with only guard, tombstone, and negative-test references remaining.
- The next resume task is git staging/commit handling, or optional hardening, not reconstructing the plan or reimplementing cleanup.

Do not treat old agent compatibility as a hidden requirement. Any old path that remains after this rewrite must be either deleted, isolated from production, or covered by a guard test proving it cannot be reintroduced.

## Non-Negotiable Principles

- This is a destructive replacement: do not keep old wire shape, do not migrate old agent history, do not run long-term dual runtimes, and do not patch the legacy runtime.
- `AgentCore` is the only production agent runtime when this plan is complete.
- Hermes is reference material only. New runtime code must not import or inherit from `app.services.hermes_service`.
- The legacy runtime is a deletion target. New production code must not import `app.services.agent`.
- `bif` remains a supported user-facing HTTP CLI, but AgentCore tools must not shell out to `bif`.
- AgentCore tools must not call BioInfoFlow's own FastAPI over HTTP. They call typed service/repository/domain boundaries in-process.
- All observable runtime output is written to `AgentEvent` before SSE/CLI/UI projection.
- Every side effect goes through `AgentAction`, including platform tools, workflow registration, run submit/cancel/retry, shell/code execution, memory writes, and config changes.
- Bioinformatics logic is deterministic-service-first. LLMs plan, explain, combine, repair, and generate, but parsing, preflight, diagnosis, validation, and result readers must be testable services.
- Provider/model catalog is platform-level under `llm`, not agent-private.

## Old Semantics To Remove

- `AgentConversation*`
- `AgentMessageRead`
- old `AgentEventData`
- old message metadata parts as source of truth
- mixed persistent/stream `AgentMessageType`
- `conversation.storage_backend`
- `hermes_session_id`
- `policy_mode`
- `execution_policy`
- `response_id`
- `assistant_message_id`
- coarse `approval_type`
- legacy/Hermes response handles
- old agent trace as source of truth

## New Public APIs

### Agent APIs

- `POST /api/v1/agent/sessions`
- `GET /api/v1/agent/sessions`
- `GET /api/v1/agent/sessions/{session_id}`
- `PATCH /api/v1/agent/sessions/{session_id}`
- `DELETE /api/v1/agent/sessions/{session_id}`
- `POST /api/v1/agent/sessions/{session_id}/turns`
- `GET /api/v1/agent/sessions/{session_id}/turns`
- `GET /api/v1/agent/turns/{turn_id}`
- `POST /api/v1/agent/turns/{turn_id}/cancel`
- `GET /api/v1/agent/sessions/{session_id}/stream?after_seq=`
- `GET /api/v1/agent/turns/{turn_id}/events?after_seq=`
- `POST /api/v1/agent/actions/{action_id}/decision`
- `GET /api/v1/agent/sessions/{session_id}/artifacts`
- `GET /api/v1/agent/turns/{turn_id}/artifacts`
- `GET /api/v1/agent/artifacts/{artifact_id}`

### LLM APIs

- `GET /api/v1/llm/providers`
- `POST /api/v1/llm/providers`
- `PATCH /api/v1/llm/providers/{provider_id}`
- `POST /api/v1/llm/providers/{provider_id}/test`
- `GET /api/v1/llm/models`
- `POST /api/v1/llm/models`
- `PATCH /api/v1/llm/models/{model_id}`
- `GET /api/v1/llm/model-profiles`
- `POST /api/v1/llm/model-profiles`
- `PATCH /api/v1/llm/model-profiles/{profile_id}`

### CLI APIs

The `bif` CLI stays HTTP-only and user-facing:

- `bif agent session create/list/show/delete`
- `bif agent send`
- `bif agent stream`
- `bif agent action approve/reject`
- `bif agent artifacts list/show/open`
- `bif agent events`

CLI streaming uses NDJSON. Non-interactive CLI calls that hit a required approval return a clear error envelope and non-zero exit code. CLI never bypasses the permission engine.

## New Core Models

### AgentSession

- `id`
- `project_id`
- `workspace_id`
- `user_id`
- `title`
- `role_profile`
- `permission_mode`
- `automation_mode`
- `default_model_profile_id`
- `status`
- `metadata`
- `created_at`
- `updated_at`

### AgentTurn

- `id`
- `session_id`
- `project_id`
- `workspace_id`
- `user_id`
- `input_text`
- `input_parts`
- `status`: `queued | running | waiting_user | waiting_approval | completed | failed | cancelled`
- `model_profile_snapshot`
- `final_text`
- `token_usage`
- `error_code`
- `error_message`
- `created_at`
- `started_at`
- `completed_at`

### AgentEvent

- `id`
- `session_id`
- `turn_id`
- `seq`
- `type`
- `payload`
- `visibility`: `user | internal | audit`
- `schema_version`
- `created_at`

Initial event types:

- `turn.created`
- `turn.started`
- `turn.completed`
- `turn.failed`
- `turn.cancelled`
- `assistant.text.delta`
- `assistant.text.completed`
- `assistant.thinking.delta`
- `assistant.thinking.summary`
- `plan.created`
- `plan.updated`
- `plan.step.started`
- `plan.step.completed`
- `plan.step.failed`
- `model.selected`
- `user_input.requested`
- `user_input.resolved`
- `action.requested`
- `action.risk_assessed`
- `action.waiting_decision`
- `action.decision_recorded`
- `action.started`
- `action.progress`
- `action.completed`
- `action.failed`
- `action.cancelled`
- `artifact.created`
- `memory.read`
- `memory.proposed`
- `memory.written`
- `memory.rejected`
- `audit.note`

### AgentAction

- `id`
- `session_id`
- `turn_id`
- `parent_action_id`
- `kind`: `tool | platform | shell | code | workflow | run | memory | config | subagent`
- `name`
- `input`
- `input_preview`
- `redacted_input`
- `risk_level`
- `risk_reasons`
- `read_scope`
- `write_scope`
- `affected_resources`
- `permission_decision`
- `status`
- `result`
- `error`
- `audit_summary`
- `rollback_hint`
- `artifact_policy`
- `created_at`
- `started_at`
- `completed_at`

### AgentArtifact

- `id`
- `session_id`
- `turn_id`
- `action_id`
- `type`: `script | report | output_dir | log_summary | run_summary | workflow_card | image_card | preflight_report | diagnosis | result_summary | plot | table | file_ref | run_ref | workflow_ref`
- `title`
- `summary`
- `payload`
- `file_path`
- `resource_ref`
- `created_at`

### AgentMemory

- `id`
- `scope`: `user | project | workflow | run | dataset | image | global`
- `type`: `project_convention | workflow_note | image_compatibility | run_lesson | error_playbook | analysis_template | validated_preset`
- `content`
- `source`
- `confidence`
- `status`: `proposed | accepted | rejected | disabled`
- `created_at`
- `updated_at`

### LlmProvider / LlmModel / LlmModelProfile

- `LlmProvider`: kind, base URL, API key reference, scope, enabled flag, test status.
- `LlmModel`: provider, model ID, display name, context length, max output tokens, tool/streaming/vision/JSON-schema/reasoning capabilities, default parameters, cost metadata.
- `LlmModelProfile`: task type, primary model, fallback models, reasoning budget, max tokens, cost ceiling, routing policy.

## Backend Module Layout

### AgentCore

```text
backend/app/services/agent_core/
  __init__.py
  service.py
  runtime.py
  schemas.py
  events.py
  ledger.py
  projections.py
  sessions.py
  turns.py
  actions.py
  artifacts.py
  context.py
  planner.py
  tools/
    specs.py
    registry.py
    dispatcher.py
    platform/
      projects.py
      data.py
      files.py
      reference_libraries.py
      workflows.py
      images.py
      runs.py
      results.py
      logs.py
      terminal.py
      users.py
      system_config.py
    bio/
      workflow_tools.py
      image_tools.py
      preflight_tools.py
      diagnosis_tools.py
      result_tools.py
      secondary_analysis_tools.py
    execution/
      shell.py
      code.py
      filesystem.py
  permissions/
    risk.py
    policy.py
    decisions.py
    audit.py
  sandbox/
    shell_session.py
    process_manager.py
    filesystem_policy.py
    limits.py
  memory/
    models.py
    store.py
    retrieval.py
    proposals.py
  skills/
    manifest.py
    loader.py
    registry.py
    builtin/
      fastq_qc.py
      rnaseq.py
      single_cell.py
      germline_wgs.py
      variant_annotation.py
      multiqc_summary.py
      failure_diagnosis.py
      workflow_authoring.py
  plugins/
    manifest.py
    loader.py
    registry.py
  subagents/
    runner.py
    research.py
    log_diagnosis.py
    workflow_validator.py
  evals/
    scenarios.py
    assertions.py
```

### Platform LLM Module

```text
backend/app/services/llm/
  __init__.py
  providers.py
  models.py
  profiles.py
  router.py
  testing.py
  clients/
    base.py
    openai.py
    anthropic.py
    gemini.py
    openrouter.py
    ollama.py
    vllm.py
    openai_compatible.py
```

AgentCore consumes `LlmModelProfile`; it does not own provider configuration.

### Bioinformatics Domain Services

```text
backend/app/services/bioinformatics/
  workflows/
    parse.py
    docs.py
    schema.py
    validate.py
    generate.py
  images/
    inspect.py
    software_probe.py
    compatibility.py
    cards.py
  preflight/
    service.py
    checks.py
    reports.py
  diagnosis/
    service.py
    log_extractors.py
    classifiers.py
  results/
    readers.py
    interpretation.py
    secondary_analysis.py
```

Agent tools call these services and turn their outputs into `AgentAction` and `AgentArtifact` records.

## Permission And Automation

Permission modes:

- `ask_each_action`: all act actions require approval.
- `guarded_auto`: default; read and low-risk act actions auto-run, high-risk actions ask.
- `bypass`: owner/admin or explicitly authorized only; still sandboxed and audited.

Automation modes:

- `advise_only`: analysis and suggestions only.
- `assisted`: semi-automatic; key actions require humans.
- `autonomous`: proactive planning and execution under permission, sandbox, quota, and audit constraints.

Risk levels:

- `read`
- `act_low`
- `act_high`
- `destructive`
- `external`
- `critical`

Risk engine input:

- action kind/name/input
- user role
- project/workspace permission
- read/write scope
- resource estimate
- data sensitivity
- external network target
- permission mode
- automation mode

Risk engine output:

- risk level
- reasons
- affected resources
- permission decision
- approval prompt
- redacted preview

## Platform Toolsets

Every tool declares input schema, output schema, risk, read scope, write scope, audit text, rollback hint, timeout, and artifact policy.

Projects/data/files:

- create/read/list projects
- find project data
- infer file type
- inspect sample sheets
- preview files
- manage reference libraries

Workflows:

- list/get/register/update workflows
- extract schema
- generate workflow card
- generate human docs
- generate AI structured docs
- validate/lint/dry-run
- version/pin/bind

Images:

- list/pull/status
- inspect local/registry image
- inspect Dockerfile/env/Git repo
- software probe
- Image Card
- workflow-image compatibility
- digest/tag/build metadata
- risk/validation status

Runs/logs/results:

- preview
- preflight
- submit
- status
- DAG
- stdout/stderr/logs
- cancel/retry/resume
- result listing
- result interpretation
- archive artifacts

Terminal/shell/code:

- controlled command execution
- command preview
- cwd/read/write scope
- timeout/output cap
- process handle/cancel
- stdout/stderr artifact
- generated script/report artifact registration

## Bioinformatics Domain Services

Workflow intelligence supports Nextflow, WDL, CWL, Snakemake, and internal YAML:

- parse task structure
- parse inputs/outputs
- detect dependencies
- detect images
- infer resource requirements
- read default config
- document applicable scenarios
- generate human documentation
- generate AI/system structured docs
- generate workflow cards and DAG cards

Workflow generation supports:

- Nextflow DSL2 modules/pipelines
- WDL
- bash wrappers
- Python/R scripts
- config templates
- test data examples

Workflow registration gate:

```text
generate draft
  -> validate/lint
  -> dry-run or parser validation
  -> minimal fixture test
  -> create artifact
  -> user approval
  -> register workflow
```

Image intelligence supports:

- registry/local image inspect
- Dockerfile/env/Git repo inspector
- software version probe
- entrypoint/cmd/env/resource hints
- digest/tag/build metadata
- workflow-image compatibility
- Image Card with source, risk, validation state

Preflight checks:

- FASTQ pairing
- sample name consistency
- file existence
- allowed paths
- reference genome/annotation/index compatibility
- workflow schema required params
- image availability
- CPU/memory/disk/GPU estimate
- scheduler queue/resources
- cost estimate
- permissions

`run_submit` must depend on passing preflight.

Run diagnosis reads:

- Nextflow trace/timeline/report
- work directory
- `.command.log` and `.command.err`
- WDL task logs
- scheduler events
- Docker exit code
- OOM/disk/permission/network/image errors

Run diagnosis outputs:

- failed task
- command/log evidence
- error category
- root cause
- fix suggestion
- retry/resume params

Result interpretation reads:

- MultiQC
- flagstat
- coverage
- VCF/GVCF summary
- annotation table
- count matrix
- differential expression results
- enrichment outputs
- HTML reports
- plots/images

Role-specific result summaries:

- Bioinformatics engineer: technical QC and evidence.
- Wet-lab user: sample qualification and biological meaning.
- Project manager: batch status and risks.
- Report writer: reportable key results.

## Memory, Skills, Plugins, Subagents

Structured memory types:

- project conventions
- workflow notes
- image compatibility
- run lessons
- error playbooks
- analysis templates
- validated presets

Memory rules:

- no free-form silent chat memory writes
- memory writes start as proposals
- important memory requires confirmation
- memory can be viewed, rejected, disabled, and deleted
- every memory has source, confidence, and scope

Skill manifests include:

- name/version
- trigger
- tool allowlist
- validation rules
- common failure patterns
- prompt snippets
- output templates
- examples

Plugin registry supports future extension of tools, permission policies, role profiles, providers, and workflow domains.

First-version subagents are read/analysis-only:

- research subagent
- log diagnosis subagent
- workflow validator subagent

Write operations return to the main agent and go through `AgentAction`.

## Frontend Replacement

Delete old dependencies:

- `AgentConversationRead`
- `AgentMessageRead`
- old `AgentEventData`
- old mixed persistent/stream message types
- message metadata parts as source of truth
- storage backend UI branches

New frontend models:

- AgentSession
- AgentTurn
- AgentEvent
- AgentAction
- AgentArtifact
- ActionDecision
- AgentMemory
- LlmProvider
- LlmModel
- LlmModelProfile

New UI areas:

- session sidebar
- turn timeline
- planning panel
- action timeline
- approval/user-question cards
- logs panel
- artifacts panel
- run diagnosis panel
- result summary panel
- memory proposals
- provider/model profile settings

Critical frontend files:

- `frontend/app/(app)/agent/page.tsx`
- `frontend/components/bioinfoflow/chat-stream.tsx`
- `frontend/hooks/use-agent-chat.ts`
- `frontend/lib/chat-types.ts`
- `frontend/lib/chat-utils.ts`
- `frontend/components/bioinfoflow/live-deck.tsx`
- `frontend/components/bioinfoflow/settings/settings-page-client.tsx`
- `frontend/components/bioinfoflow/settings/provider-card.tsx`
- `frontend/messages/en.json`
- `frontend/messages/zh-CN.json`

## Implementation Phases

### Phase 0: Plan, Branch, Baseline, Guard Rails

- [ ] Save this plan to `docs/plans/2026-06-04-agent-core-rewrite.md`.
- [ ] Create implementation branch `codex/agent-core-rewrite`.
- [ ] Run current agent/provider/workflow/run/image/frontend chat tests and record baseline.
- [ ] Add guard tests that reject new imports from `app.services.agent`.
- [ ] Add guard tests that reject new imports from `app.services.hermes_service`.
- [ ] Add guard tests that reject old `AgentConversation*`, old `execution_policy`, and Hermes handle references in new code.
- [ ] Add guard tests that reject Agent tool shell-outs to `bif`.
- [ ] Add guard tests that reject Agent tools HTTP-calling BioInfoFlow's own FastAPI backend.
- [ ] Commit Phase 0 with `test: guard agent core rewrite boundaries`.

Gate: guard tests define hard constraints against old design returning.

Verification:

```bash
cd backend && uv run pytest tests/test_agent_core/ -v
cd backend && uv run ruff check .
```

### Phase 1: DB Schema And API Contract

- [ ] Add agent core SQLAlchemy models for sessions, turns, events, actions, artifacts, and memories.
- [ ] Add platform LLM SQLAlchemy models for providers, models, and model profiles.
- [ ] Add repositories for agent core and LLM models.
- [ ] Add Alembic migrations that create new tables and remove or disable old agent tables/fields.
- [ ] Add `backend/app/schemas/agent_core.py`.
- [ ] Add `backend/app/schemas/llm.py`.
- [ ] Rewrite `/api/v1/agent.py` to expose session/turn/event/action/artifact APIs.
- [ ] Add `/api/v1/llm.py` and include it in the v1 router.
- [ ] Commit Phase 1 with `feat: add agent core schema and API contracts`.

Gate: API contract tests pass; old agent schemas are not production path.

Verification:

```bash
cd backend && uv run pytest tests/test_api/test_agent_core_api.py -v
cd backend && uv run pytest tests/test_api/test_llm_api.py -v
cd backend && uv run alembic upgrade head
cd backend && uv run ruff check .
```

### Phase 2: AgentCore Kernel

- [ ] Implement `backend/app/services/agent_core/`.
- [ ] Implement session lifecycle.
- [ ] Implement turn runner.
- [ ] Implement event ledger append/replay.
- [ ] Implement SSE stream with `after_seq`.
- [ ] Implement cancel.
- [ ] Implement no-tool chat with thinking/text stream.
- [ ] Record model snapshot and token usage.
- [ ] Commit Phase 2 with `feat: implement agent core event runtime`.

Gate: create session, send turn, stream, refresh restore, and cancel all work.

Verification:

```bash
cd backend && uv run pytest tests/test_agent_core/test_kernel.py -v
cd backend && uv run pytest tests/test_api/test_agent_core_api.py -v
cd backend && uv run ruff check .
```

### Phase 3: LLM Provider/Model Catalog

- [ ] Implement `backend/app/services/llm/`.
- [ ] Support OpenAI, Anthropic/Claude, Gemini, OpenRouter, Ollama, vLLM, and OpenAI-compatible providers.
- [ ] Support API key reference, base URL, model ID, context length, tool calling, streaming, JSON schema, reasoning, and default parameters.
- [ ] Implement provider test endpoint and service.
- [ ] Make AgentCore consume `LlmModelProfile`.
- [ ] Record model snapshot and fallback information on turns.
- [ ] Commit Phase 3 with `feat: add platform llm model catalog`.

Gate: API/UI can add, edit, test providers; turns record model snapshot and fallback information.

Verification:

```bash
cd backend && uv run pytest tests/test_services/test_llm_service.py -v
cd backend && uv run pytest tests/test_api/test_llm_api.py -v
cd backend && uv run ruff check .
```

### Phase 4: Action Ledger And Permission Engine

- [ ] Implement action lifecycle.
- [ ] Implement permission modes: `ask_each_action`, `guarded_auto`, `bypass`.
- [ ] Implement automation modes: `advise_only`, `assisted`, `autonomous`.
- [ ] Implement risk levels: `read`, `act_low`, `act_high`, `destructive`, `external`, `critical`.
- [ ] Implement approve/reject/modify decisions.
- [ ] Persist approval/action state so refresh restores correctly.
- [ ] Commit Phase 4 with `feat: add agent action permission ledger`.

Gate: all act operations enter action ledger; high-risk actions are controlled by permission engine.

Verification:

```bash
cd backend && uv run pytest tests/test_agent_core/test_actions.py -v
cd backend && uv run pytest tests/test_agent_core/test_permissions.py -v
cd backend && uv run pytest tests/test_api/test_agent_core_api.py -v
cd backend && uv run ruff check .
```

### Phase 5: Platform Tools

- [ ] Implement tools for projects.
- [ ] Implement tools for data, files, and reference libraries.
- [ ] Implement tools for workflows.
- [ ] Implement tools for images.
- [ ] Implement tools for runs.
- [ ] Implement tools for logs and results.
- [ ] Implement tools for terminal.
- [ ] Implement tools for users and system config.
- [ ] Ensure every tool declares schema, risk, scope, audit, rollback, timeout, and artifact policy.
- [ ] Ensure tools only call backend service/repository boundaries.
- [ ] Commit Phase 5 with `feat: add agent platform tool registry`.

Gate: platform writes are permission-controlled; no `bif` shell-out.

Verification:

```bash
cd backend && uv run pytest tests/test_agent_core/test_tools/ -v
cd backend && uv run pytest tests/test_agent_core/test_guardrails.py -v
cd backend && uv run ruff check .
```

### Phase 6: Bioinformatics Domain Services

- [ ] Implement workflow intelligence services.
- [ ] Implement image intelligence services.
- [ ] Implement preflight services.
- [ ] Implement run diagnosis services.
- [ ] Implement result interpretation services.
- [ ] Implement secondary analysis services.
- [ ] Add AgentCore tools that call these services.
- [ ] Ensure `run_submit` requires passing preflight.
- [ ] Commit Phase 6 with `feat: add bioinformatics agent services`.

Gate: preflight prevents bad runs; diagnosis/result interpretation has an evidence chain.

Verification:

```bash
cd backend && uv run pytest tests/test_services/test_bioinformatics/ -v
cd backend && uv run pytest tests/test_agent_core/test_tools/test_bio_tools.py -v
cd backend && uv run ruff check .
```

### Phase 7: Workflow Generation And Controlled Code Agent

- [ ] Generate Nextflow DSL2, WDL, bash wrappers, Python/R scripts, configs, and test data.
- [ ] Require validate/lint/dry-run/minimal fixture test before workflow registration.
- [ ] Implement shell/code/file-edit executors behind action ledger.
- [ ] Persist command preview, cwd, read/write scope, risk, approval, stdout/stderr, diff, and artifact registration.
- [ ] Block dangerous commands through permission engine and sandbox.
- [ ] Commit Phase 7 with `feat: add controlled code agent execution`.

Gate: unverified workflows cannot register; dangerous operations are blocked; execution artifacts are registered.

Verification:

```bash
cd backend && uv run pytest tests/test_agent_core/test_execution/ -v
cd backend && uv run pytest tests/test_services/test_bioinformatics/test_workflow_generation.py -v
cd backend && uv run ruff check .
```

### Phase 8: Memory, Skills, Plugins, Subagents

- [ ] Implement structured memory with proposal/confirmation flow.
- [ ] Implement skill manifests and loader.
- [ ] Implement plugin registry.
- [ ] Implement read-only/analysis subagents.
- [ ] Ensure write operations return to main agent through `AgentAction`.
- [ ] Commit Phase 8 with `feat: add agent memory skills and subagents`.

Gate: memory can be confirmed/deleted/disabled; subagents do not perform concurrent writes; skills/plugins are versioned.

Verification:

```bash
cd backend && uv run pytest tests/test_agent_core/test_memory.py -v
cd backend && uv run pytest tests/test_agent_core/test_skills.py -v
cd backend && uv run pytest tests/test_agent_core/test_subagents.py -v
cd backend && uv run ruff check .
```

### Phase 9: Frontend Replacement

- [ ] Replace old conversation/message/event dependencies.
- [ ] Implement session sidebar.
- [ ] Implement turn stream reducer.
- [ ] Implement planning panel.
- [ ] Implement action timeline.
- [ ] Implement approval/user-question cards.
- [ ] Implement logs, artifacts, diagnosis, result summary, memory, and provider UI.
- [ ] Update `messages/en.json`.
- [ ] Update `messages/zh-CN.json`.
- [ ] Commit Phase 9 with `feat: replace frontend agent experience`.

Gate: frontend no longer depends on old agent types; refresh restores full state.

Verification:

```bash
cd frontend && bun run lint
cd frontend && bun run lint:i18n
cd frontend && bun run test
cd frontend && bun run build
```

### Phase 10: CLI Migration

- [x] Migrate `bif agent` to new AgentCore APIs.
- [x] Add `session`, `send`, `stream`, `action`, `artifacts`, and `events` commands.
- [x] Use NDJSON for streaming.
- [x] Preserve JSON envelope, exit codes, and config/env precedence.
- [ ] Commit Phase 10 with `feat: migrate bif agent to agent core`.

Gate: CLI and frontend share APIs; old `/agent/message` is unused.

Verification:

```bash
cd backend && uv run pytest tests/test_cli/test_cli_agent.py -v
cd backend && uv run bif --help
cd backend && uv run bif agent --help
cd backend && uv run ruff check .
```

### Phase 11: Final Delegacy

- [x] Remove old `backend/app/services/agent/` production dependency.
- [x] Remove Hermes production bridge.
- [x] Delete old agent schemas/models/repos/tests or convert to deletion verification tests.
- [x] Delete old frontend types/render path.
- [x] Delete old config keys.
- [ ] Run full backend, frontend, CLI, E2E, and guard verification.
- [ ] Commit Phase 11 with `refactor: remove legacy agent runtime`.

Gate: backend, frontend, CLI, E2E, and guard tests pass; old runtime has no production path.

Verification:

```bash
cd backend && uv run pytest
cd backend && uv run ruff check .
cd backend && uv run ruff format . --check
cd frontend && bun run lint
cd frontend && bun run lint:i18n
cd frontend && bun run test
cd frontend && bun run build
```

## Critical Files

Replace/delete targets:

- `backend/app/services/agent/`
- `backend/app/services/hermes_service/`
- `backend/app/api/v1/agent.py` old routes
- `backend/app/schemas/agent.py` old schemas
- `backend/app/models/conversation.py` old agent semantics
- `backend/app/models/message.py` old agent semantics
- `backend/app/models/approval.py` old approval semantics
- `backend/app/models/agent_trace.py`
- `backend/app/models/agent_response_handle.py`
- `backend/app/models/agent_approval_handle.py`
- old frontend agent chat types/hooks/renderers

New/rewrite targets:

- `backend/app/services/agent_core/**`
- `backend/app/services/llm/**`
- `backend/app/services/bioinformatics/**`
- `backend/app/api/v1/agent.py`
- `backend/app/api/v1/llm.py`
- `backend/app/schemas/agent_core.py`
- `backend/app/schemas/llm.py`
- `backend/app/models/agent_core_*.py`
- `backend/app/models/llm_*.py`
- `backend/app/repositories/agent_core_*.py`
- `backend/app/repositories/llm_*.py`
- `backend/alembic/versions/*agent_core*`
- `backend/alembic/versions/*llm*`
- `backend/app/cli/commands/agent.py`
- `frontend/lib/agent-core/**`
- `frontend/hooks/use-agent-core.ts`
- `frontend/components/bioinfoflow/agent-core/**`
- `frontend/messages/en.json`
- `frontend/messages/zh-CN.json`
- `docs/plans/2026-06-04-agent-core-rewrite.md`

## Overall Test Plan

Backend contract tests:

- sessions
- turns
- stream replay
- cancel
- action decision
- artifacts
- LLM providers/models/profiles

Migration/guard tests:

- old tables/fields unavailable
- new code does not import legacy agent
- new code does not import Hermes
- new code does not reference old schema/type/policy
- tools do not call `bif`
- tools do not HTTP-call own backend

Kernel tests:

- event append-only
- seq ordering
- replay/idempotency
- turn projection
- cancel persistence
- model snapshot

Permission/action tests:

- permission modes
- automation modes
- risk classifier
- approve/reject/modify
- duplicate decision
- audit text

Platform tool tests:

- project/file/workflow/image/run/log/terminal/config tools
- auth scoping
- service boundary only
- artifacts generated

Bioinformatics tests:

- workflow parse/docs/schema
- image card
- preflight failure prevention
- workflow generation validation
- run diagnosis
- result summary

Frontend tests:

- session list
- turn streaming
- event reducer
- approval card
- action rendering
- artifact/result/memory/provider UI
- i18n

E2E tests:

- create project
- identify data
- register workflow
- preflight
- submit run
- diagnose failure
- interpret results
- generate script and register artifact
- add/test/select provider

## Final Completion Criteria

- Old agent runtime has no production path.
- Hermes bridge has no production path.
- Old agent history is not read by the new system.
- New Agent APIs are based on sessions, turns, events, actions, and artifacts.
- Frontend no longer depends on old conversation/message/event types.
- CLI uses new AgentCore endpoints and remains a supported user-facing client.
- AgentCore never depends on CLI.
- All platform actions enter `AgentAction` ledger.
- All observable outputs enter `AgentEvent` ledger.
- High-risk actions are controlled by permission engine.
- Provider/model/profile are configurable, testable, and auditable platform modules.
- Workflow/image/preflight/run diagnosis/result interpretation loop is usable.
- Memory/skills/plugins are structured, versioned, and auditable.

## Assumptions

- Old agent history data can be discarded.
- Breaking API/frontend/CLI replacement is allowed.
- `AgentCore` is the only production runtime.
- Hermes is reference material only, not a dependency.
- `bif` remains a user/script HTTP client, not an internal Agent executor.
- Provider/model catalog is platform-level, not agent-private.
- Bioinformatics business capabilities are deterministic services first; Agent accesses them through tools.

## Execution Checkpoint - 2026-06-04

This section preserves the handoff state after leaving plan mode. Treat it as the current source of truth for resuming implementation, alongside the phase checklist above.

### Current Branch And Worktree

- Branch: `codex/agent-core-rewrite`
- Worktree: `/Users/lewisliu/.codex/worktrees/987b/bioinfoflow`
- Main working copy also exists at `/Users/lewisliu/Dev/ACTIVE/bioinfoflow`
- User edits are present and must not be reverted:
  - `AGENTS.md`
  - `CLAUDE.md`

### Current Implementation State

The rewrite is deep into the destructive replacement path. The current AgentCore milestone implements Phase 0, Phase 1, Phase 2, Phase 4, Phase 5, Phase 6 initial, the Phase 7 controlled shell approval/artifact loop, the Phase 8 structured memory service/API/tool loop, the Phase 8 skills/plugins registry foundation, the Phase 8 read-only subagent boundary, Phase 9 frontend AgentCore replacement, Phase 10 CLI migration, and the backend half of Phase 11 final delegacy cleanup.

Implemented so far:

- Guard tests prevent new runtime code from importing `app.services.agent`.
- Guard tests prevent new runtime code from importing `app.services.hermes_service`.
- Guard tests prevent legacy concepts from returning as new runtime semantics, including `AgentConversation*`, `execution_policy`, and Hermes handles.
- Guard tests prevent AgentCore execution paths from shelling out to `bif`.
- Guard tests prevent AgentCore execution paths from HTTP-calling BioInfoFlow's own FastAPI.
- New AgentCore database/API contract:
  - `AgentSession`
  - `AgentTurn`
  - `AgentEvent`
  - `AgentAction`
  - `AgentArtifact`
- New platform-level LLM catalog database/API contract:
  - `LlmProvider`
  - `LlmModel`
  - `LlmModelProfile`
- Old `POST /api/v1/agent/message` returns `404`.
- New session/turn/event/artifact APIs work in tests.
- New LLM provider/model/profile CRUD and provider test contract work in tests.
- Minimal no-tool runtime writes ordered ledger events:
  - `turn.created`
  - `turn.started`
  - `assistant.thinking.summary`
  - `assistant.text.completed`
  - `turn.completed`
- Permission engine and action lifecycle are present:
  - permission modes: `ask_each_action`, `guarded_auto`, `bypass`
  - automation modes: `advise_only`, `assisted`, `autonomous`
  - risk levels: `read`, `act_low`, `act_high`, `destructive`, `external`, `critical`
  - action events: requested, risk assessed, waiting decision, decision recorded, started, completed, failed
- Tool ABI, registry, dispatcher, and platform read tools exist:
  - `projects.list`
  - `workflows.list`
  - `images.list`
  - `runs.list`
  - `runs.logs`
- Deterministic bioinformatics services and AgentCore tools exist:
  - `bio.workflow_card`
  - `bio.image_card`
  - `bio.run_preflight`
  - `bio.run_diagnosis`
  - `bio.result_interpretation`
- Controlled shell tool exists:
  - `execution.shell`
  - argv-only input
  - cwd constrained by `FilesystemPolicy`
  - blocks `bif`, `curl`, `docker`, `git`, `rm`, `scp`, `ssh`, `sudo`, `wget`
  - waits for approval under `guarded_auto`
  - executes safe commands under `bypass`
- Waiting tool actions can be resumed after approval:
  - `approve` executes the original action input
  - `modify` executes the modified action input and persists it on the same `AgentAction`
  - `reject` records a terminal rejected action
  - resumed execution reuses the same action ledger entry rather than creating a second action
- Shell execution output is registered as an artifact:
  - creates a `log_summary` `AgentArtifact`
  - stores command, cwd, exit code, stdout, and stderr in the artifact payload
  - writes an `artifact.created` event
  - links the artifact to the originating action
- Structured memory has a first complete backend loop:
  - `AgentMemoryService` lists, proposes, accepts, rejects, and disables structured memories
  - memory proposals default to `proposed`
  - accepted memories emit `memory.written`
  - rejected and disabled memories emit `memory.rejected`
  - memory reads from tools emit `memory.read`
  - memory writes through `memory.propose` run inside the action ledger
  - API supports proposal/list/accept/reject/disable
  - tools registered: `memory.list`, `memory.propose`
- Skills/plugins have a first registry foundation:
  - `AgentSkillRegistry` discovers versioned `SKILL.md` manifests
  - `AgentPluginRegistry` discovers versioned `.bioinfoflow-plugin/plugin.json` manifests
  - skill descriptions can be projected for prompt context
  - full skill bodies can be loaded on demand
  - tools registered: `skills.list`, `skills.load`, `plugins.list`
  - tools read from platform default registry roots and do not accept arbitrary model-provided filesystem roots
- Read-only subagents have a first policy boundary:
  - `ReadOnlySubagentRunner` accepts only read-only tools
  - write-capable tools are rejected before execution
  - subagent handoff contract states that write operations must return to the main agent action ledger
  - no concurrent write path is introduced
- Frontend AgentCore foundation exists:
  - new `frontend/lib/agent-core` types mirror session/turn/event/action/artifact/memory contracts
  - new `frontend/lib/agent-core/client.ts` calls session/turn/event/action/artifact/memory APIs
  - new `frontend/hooks/use-agent-core.ts` loads sessions, creates sessions, submits turns, and replays turn events
  - unit test asserts the new hook does not call legacy `/agent/message`
- Visible `/agent` page now uses AgentCore:
  - `frontend/components/bioinfoflow/agent-core/agent-core-chat.tsx` renders session status, turns, assistant final text, and event ledger
  - `frontend/app/(app)/agent/page.tsx` uses `AgentCoreChat` instead of legacy `ChatStream`
  - keyboard focus/new-session handles are preserved for the agent page
  - new AgentCore UI strings exist in both `en` and `zh-CN`
- Sidebar and command palette have been moved onto AgentCore session APIs:
  - sidebar data now loads AgentCore sessions rather than legacy conversations
  - command palette session navigation/search uses AgentCore sessions
  - project/sidebar item tests have been updated for the new session shape
  - scoped search confirms no `/agent/conversations`, `/agent/message`, `AgentConversationRead`, `AgentMessageRead`, `AgentEventData`, or `use-agent-chat` references remain in the migrated AgentCore page/sidebar/command-palette areas
- Phase 9 legacy frontend agent surface removal is now complete for the production app surface:
  - deleted `frontend/hooks/use-agent-chat.ts`
  - deleted `frontend/components/bioinfoflow/chat-stream.tsx`
  - deleted old ChatStream/useAgentChat/agent-capabilities tests that asserted `/agent/message`
  - deleted legacy `frontend/lib/conversations.ts`
  - deleted old execution-policy UI islands that depended on `ExecutionPolicy`
  - removed `AgentConversationRead`, `AgentConversationHistory`, `AgentMessageRead`, `AgentMessageResponse`, `AgentEventData`, `AgentMessageType`, and `ExecutionPolicy` from shared frontend types
  - removed legacy agent SSE subscription plumbing from `RuntimeEventSubscription`, `live-runtime`, `demo-runtime`, and `useEvents`
  - changed demo runtime agent seed data from legacy conversations to `AgentCoreSession`
  - changed demo runtime to serve `/agent/sessions`, `/agent/sessions/{session_id}/turns`, and `/agent/turns/{turn_id}/events`
  - changed demo runtime legacy `/agent/message` and `/agent/conversations*` routes into explicit `404` tombstones
  - renamed demo replay `agent.message` records to `agent.text.completed`
  - current legacy scan only finds expected tombstone/negative-test references to removed legacy routes
- Phase 10 CLI migration is complete for the current product surface:
  - `bif agent session create/list/show/delete`
  - `bif agent send --session`
  - `bif agent stream`
  - `bif agent turn list/show/cancel`
  - `bif agent action approve/reject/modify`
  - `bif agent artifacts list/show/open`
  - `bif agent events` now uses `--session`/`--turn` rather than `--conversation`
  - legacy `agent history`, `agent approvals`, `/agent/message`, `/agent/conversations`, and `--conversation` are removed from the CLI product surface
- Phase 11 backend delegacy cleanup is complete for production runtime paths:
  - provider registry moved from legacy `backend/app/services/agent/runtime/providers.py` to platform-level `backend/app/services/llm/providers.py`
  - `backend/app/api/v1/providers.py`, `backend/app/api/v1/user_settings.py`, and `backend/app/services/user_settings_service.py` now import provider resolution from `app.services.llm.providers`
  - Hermes startup lifecycle was removed from `backend/app/main.py`
  - deleted old `backend/app/services/agent/`
  - deleted old `backend/app/services/hermes_service/`
  - deleted old conversation/message/approval/trace/response-handle ORM, repository, and schema files
  - removed `Project.conversations`
  - deleted old backend agent/Hermes tests and removed the Hermes fixture from `backend/tests/conftest.py`
  - expanded guard tests now assert production code does not import `app.services.agent` or `app.services.hermes_service`, and that the old service directories do not exist
- Additional Phase 11 frontend/config/schema cleanup is complete for the current product surface:
  - demo replay now projects the existing recording into AgentCore turns/events rather than old SSE `ChatMessage` state
  - `frontend/app/(demo)/demo/page.tsx` renders `AgentCoreTurnBlock` instead of legacy `MessageList`
  - deleted old `frontend/lib/chat-types.ts`
  - deleted old `frontend/lib/chat-utils.ts`
  - deleted old `frontend/lib/conversation-export.ts`
  - deleted old `frontend/hooks/use-chat-scroll.ts`
  - deleted old `frontend/components/bioinfoflow/chat/message-list.tsx`
  - deleted old `frontend/components/bioinfoflow/chat/message-bubble.tsx`
  - deleted old `frontend/components/bioinfoflow/chat/parts/*`
  - deleted old chat renderer/export utility tests
  - backend settings no longer expose `agent_hermes_home`, `agent_hermes_state_db`, `agent_engine`, or `agent_hermes_max_concurrency`
  - startup logging now reports `agent_core` runtime settings instead of Hermes/legacy agent engine fields
  - migration `0029_drop_legacy_agent_tables` drops `agent_approval_handles`, `agent_response_handles`, `agent_approvals`, `agent_traces`, `messages`, and `conversations`
- Remaining Phase 11 work:
  - run final backend, frontend, CLI, guard, migration, and legacy-reference verification
  - update this plan with the final verification results
  - attempt a commit if sandbox git index permissions allow it

### Files Added Or Rewritten In Current Milestone

Plan:

- `docs/plans/2026-06-04-agent-core-rewrite.md`

Backend models and migration:

- `backend/app/models/agent_core.py`
- `backend/app/models/llm.py`
- `backend/alembic/versions/0028_agent_core_llm_contracts.py`
- `backend/app/models/__init__.py`

Repositories:

- `backend/app/repositories/agent_core_repo.py`
- `backend/app/repositories/llm_repo.py`
- `backend/app/repositories/__init__.py`

Schemas:

- `backend/app/schemas/agent_core.py`
- `backend/app/schemas/llm.py`

APIs:

- `backend/app/api/v1/agent.py`
- `backend/app/api/v1/llm.py`
- `backend/app/api/v1/router.py`

AgentCore runtime:

- `backend/app/services/agent_core/service.py`
- `backend/app/services/agent_core/runtime.py`
- `backend/app/services/agent_core/ledger.py`
- `backend/app/services/agent_core/events.py`
- `backend/app/services/agent_core/actions.py`
- `backend/app/services/agent_core/memory.py`
- `backend/app/services/agent_core/plugins.py`
- `backend/app/services/agent_core/skills.py`
- `backend/app/services/agent_core/subagents.py`
- `backend/app/services/agent_core/permissions/policy.py`
- `backend/app/services/agent_core/permissions/risk.py`
- `backend/app/services/agent_core/sandbox/filesystem_policy.py`
- `backend/app/services/agent_core/tools/specs.py`
- `backend/app/services/agent_core/tools/registry.py`
- `backend/app/services/agent_core/tools/dispatcher.py`
- `backend/app/services/agent_core/tools/memory/resources.py`
- `backend/app/services/agent_core/tools/skills/resources.py`
- `backend/app/services/agent_core/tools/platform/projects.py`
- `backend/app/services/agent_core/tools/platform/workflows.py`
- `backend/app/services/agent_core/tools/platform/images.py`
- `backend/app/services/agent_core/tools/platform/runs.py`
- `backend/app/services/agent_core/tools/bio/resources.py`
- `backend/app/services/agent_core/tools/execution/shell.py`

Platform LLM service:

- `backend/app/services/llm/catalog.py`

Deterministic bioinformatics services:

- `backend/app/services/bioinformatics/workflows/cards.py`
- `backend/app/services/bioinformatics/images/cards.py`
- `backend/app/services/bioinformatics/preflight/service.py`
- `backend/app/services/bioinformatics/diagnosis/service.py`
- `backend/app/services/bioinformatics/results/interpretation.py`

Tests:

- `backend/tests/test_agent_core/test_guardrails.py`
- `backend/tests/test_agent_core/test_kernel.py`
- `backend/tests/test_agent_core/test_memory.py`
- `backend/tests/test_agent_core/test_permissions.py`
- `backend/tests/test_agent_core/test_skills_plugins.py`
- `backend/tests/test_agent_core/test_subagents.py`
- `backend/tests/test_agent_core/test_actions.py`
- `backend/tests/test_agent_core/test_tools/test_platform_projects.py`
- `backend/tests/test_agent_core/test_tools/test_platform_resources.py`
- `backend/tests/test_agent_core/test_tools/test_bio_resources.py`
- `backend/tests/test_agent_core/test_tools/test_execution_shell.py`
- `backend/tests/test_api/test_agent_core_api.py`
- `backend/tests/test_api/test_llm_api.py`

Frontend AgentCore foundation:

- `frontend/lib/agent-core/types.ts`
- `frontend/lib/agent-core/client.ts`
- `frontend/lib/agent-core/index.ts`
- `frontend/lib/agent-core/session-storage.ts`
- `frontend/hooks/use-agent-core.ts`
- `frontend/components/bioinfoflow/agent-core/agent-core-chat.tsx`
- `frontend/app/(app)/agent/page.tsx`
- `frontend/hooks/use-sidebar-data.ts`
- `frontend/components/bioinfoflow/command-palette.tsx`
- `frontend/components/bioinfoflow/sidebar/conversation-item.tsx`
- `frontend/components/bioinfoflow/sidebar/project-list.tsx`
- `frontend/components/bioinfoflow/sidebar/project-item.tsx`
- `frontend/components/bioinfoflow/sidebar/sidebar.tsx`
- `frontend/messages/en.json`
- `frontend/messages/zh-CN.json`
- `frontend/tests/unit/hooks/use-agent-core.test.tsx`
- `frontend/tests/unit/hooks/use-sidebar-data.test.tsx`
- `frontend/tests/unit/components/command-palette.test.tsx`
- `frontend/tests/unit/components/agent-core-chat.test.tsx`
- `frontend/tests/unit/lib/runtime/demo-runtime.test.ts`
- `frontend/tests/unit/hooks/use-events.test.ts`
- `frontend/tests/unit/lib/demo/replay-engine.test.ts`
- `frontend/tests/integration/pages/agent-page.test.tsx`
- `frontend/tests/integration/components/workspace-shell-sidebar.test.tsx`
- `frontend/lib/demo/scenario.ts`
- `frontend/lib/demo/scenario-data.ts`
- `frontend/lib/demo/types.ts`
- `frontend/lib/demo/replay-engine.ts`
- `frontend/lib/runtime/demo-runtime.ts`
- `frontend/lib/runtime/live-runtime.ts`
- `frontend/lib/runtime/types.ts`
- `frontend/lib/types.ts`
- `frontend/tests/app-test-utils.tsx`

Frontend legacy files deleted:

- `frontend/hooks/use-agent-chat.ts`
- `frontend/components/bioinfoflow/chat-stream.tsx`
- `frontend/components/bioinfoflow/chat/bypass-banner.tsx`
- `frontend/components/bioinfoflow/chat/execution-mode-selector.tsx`
- `frontend/lib/conversations.ts`
- `frontend/tests/unit/hooks/use-agent-chat.test.tsx`
- `frontend/tests/unit/components/chat-stream.test.tsx`
- `frontend/tests/unit/components/execution-mode-selector.test.tsx`
- `frontend/tests/integration/pages/agent-capabilities.test.tsx`

### Verification Already Passed

Use `UV_CACHE_DIR=.uv-cache` from `backend/` to avoid sandbox cache writes outside the worktree.

```bash
cd backend
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_agent_core tests/test_api/test_agent_core_api.py tests/test_api/test_llm_api.py -v
UV_CACHE_DIR=.uv-cache uv run ruff check .
DATABASE_URL=sqlite+aiosqlite:////private/tmp/bioinfoflow-agent-core-shell.db UV_CACHE_DIR=.uv-cache uv run alembic upgrade head
```

Observed result:

- Targeted AgentCore/API suite: `38 passed`
- Ruff: passed
- Alembic upgrade from empty temporary SQLite database to head: passed

Additional Phase 7 shell approval/artifact verification passed:

```bash
cd backend
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_agent_core/test_tools/test_execution_shell.py -v
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_agent_core tests/test_api/test_agent_core_api.py tests/test_api/test_llm_api.py -v
UV_CACHE_DIR=.uv-cache uv run ruff check .
```

Observed result:

- Shell execution tool suite: `5 passed`
- Targeted AgentCore/API suite after resume/artifact work: `30 passed`
- Ruff: passed

Additional Phase 8 structured memory verification passed:

```bash
cd backend
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_agent_core/test_memory.py -v
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_api/test_agent_core_api.py::test_agent_core_memory_contract -v
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_agent_core tests/test_api/test_agent_core_api.py tests/test_api/test_llm_api.py -v
UV_CACHE_DIR=.uv-cache uv run ruff check .
```

Observed result:

- Structured memory service/tool suite: `2 passed`
- Structured memory API contract: `1 passed`
- Targeted AgentCore/API suite after memory work: `33 passed`
- Ruff: passed

Additional Phase 8 skills/plugins foundation verification passed:

```bash
cd backend
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_agent_core/test_skills_plugins.py -v
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_agent_core tests/test_api/test_agent_core_api.py tests/test_api/test_llm_api.py -v
UV_CACHE_DIR=.uv-cache uv run ruff check .
```

Observed result:

- Skills/plugins registry and tool suite: `3 passed`
- Targeted AgentCore/API suite after skills/plugins work: `36 passed`
- Ruff: passed

Additional Phase 8 read-only subagent boundary verification passed:

```bash
cd backend
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_agent_core/test_subagents.py -v
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_agent_core tests/test_api/test_agent_core_api.py tests/test_api/test_llm_api.py -v
UV_CACHE_DIR=.uv-cache uv run ruff check .
```

Observed result:

- Read-only subagent boundary suite: `2 passed`
- Targeted AgentCore/API suite after subagent work: `38 passed`
- Ruff: passed

Additional Phase 9 frontend AgentCore client/hook foundation verification passed:

```bash
cd frontend
TMPDIR=/private/tmp bun install
TMPDIR=/private/tmp bun run test tests/unit/hooks/use-agent-core.test.tsx
TMPDIR=/private/tmp bun run lint
```

Observed result:

- `bun install`: checked existing installs, no package changes
- `use-agent-core` hook suite: `1 passed`
- frontend lint: passed

Additional Phase 9 visible AgentCore page replacement verification passed:

```bash
cd frontend
TMPDIR=/private/tmp bun run test tests/unit/hooks/use-agent-core.test.tsx
TMPDIR=/private/tmp bun run lint
TMPDIR=/private/tmp bun run lint:i18n
```

Observed result:

- `use-agent-core` hook suite: `1 passed`
- frontend lint: passed
- i18n coverage: passed

Additional Phase 9 sidebar and command-palette migration verification passed:

```bash
cd frontend
TMPDIR=/private/tmp bun run test tests/unit/hooks/use-agent-core.test.tsx tests/unit/hooks/use-sidebar-data.test.tsx tests/unit/components/command-palette.test.tsx tests/unit/components/project-list.test.tsx tests/unit/components/sidebar.test.tsx tests/unit/components/conversation-item.test.tsx
TMPDIR=/private/tmp bun run lint
TMPDIR=/private/tmp bun run lint:i18n
rtk rg -n "/agent/conversations|/agent/message|AgentConversationRead|AgentMessageRead|AgentEventData|use-agent-chat" frontend/app/'(app)'/agent frontend/components/bioinfoflow/command-palette.tsx frontend/components/bioinfoflow/sidebar frontend/hooks/use-sidebar-data.ts frontend/hooks/use-agent-core.ts frontend/lib/agent-core
```

Observed result:

- Focused AgentCore/sidebar/command-palette frontend suites: `6 passed`, `20 tests passed`
- frontend lint: passed
- i18n coverage: passed
- scoped legacy-reference search: no matches in migrated areas

Note: the focused `use-sidebar-data` test currently emits React `act(...)` warnings while passing. Treat this as cleanup debt, not a blocker for the API migration.

Additional Phase 9 legacy frontend surface removal verification passed:

```bash
cd frontend
TMPDIR=/private/tmp bun run test tests/unit/components/agent-core-chat.test.tsx tests/unit/lib/runtime/demo-runtime.test.ts tests/unit/hooks/use-events.test.ts tests/unit/lib/demo/replay-engine.test.ts
TMPDIR=/private/tmp bun run test tests/integration/components/workspace-shell-sidebar.test.tsx tests/integration/pages/agent-page.test.tsx
TMPDIR=/private/tmp bun run test tests/unit/hooks/use-agent-core.test.tsx tests/unit/hooks/use-sidebar-data.test.tsx tests/unit/components/command-palette.test.tsx tests/unit/components/project-list.test.tsx tests/unit/components/sidebar.test.tsx tests/unit/components/conversation-item.test.tsx
TMPDIR=/private/tmp bun run lint
TMPDIR=/private/tmp bun run lint:i18n
TMPDIR=/private/tmp bun run test
rtk git diff --check
rtk rg -n "/agent/conversations|/agent/message|AgentConversationRead|AgentConversationHistory|AgentMessageRead|AgentMessageResponse|AgentEventData|AgentMessageType|ExecutionPolicy|storage_backend|execution_policy|response_id|assistant_message_id|onAgentEvent|agent\\.message" frontend
```

Observed result:

- AgentCore/demo runtime/useEvents/demo replay focused suites: `4 passed`, `11 tests passed`
- Workspace sidebar and agent page integration suites: `2 passed`, `7 tests passed`
- Existing AgentCore sidebar/command-palette focused suites: `6 passed`, `20 tests passed`
- frontend lint: passed
- i18n coverage: passed
- full frontend test suite: passed
- `rtk git diff --check`: passed
- legacy scan remaining matches are only explicit legacy-route tombstones in `frontend/lib/runtime/demo-runtime.ts` and negative assertions that the legacy routes are not used or return `404`

Additional Phase 9 AgentCore action/artifact/memory UI milestone verification passed:

```bash
cd frontend
TMPDIR=/private/tmp bun run test tests/unit/hooks/use-agent-core.test.tsx
TMPDIR=/private/tmp bun run test tests/unit/components/agent-core-chat.test.tsx
TMPDIR=/private/tmp bun run test tests/unit/lib/runtime/demo-runtime.test.ts
TMPDIR=/private/tmp bun run test tests/unit/hooks/use-agent-core.test.tsx tests/unit/components/agent-core-chat.test.tsx tests/unit/lib/runtime/demo-runtime.test.ts
TMPDIR=/private/tmp bun run lint
TMPDIR=/private/tmp bun run lint:i18n
TMPDIR=/private/tmp bun run test
```

Observed result:

- `use-agent-core` hook now loads turn artifacts, proposed memories, and dispatches action/memory decisions through AgentCore APIs: `2 passed`
- `AgentCoreChat` now renders action timeline, approval card, artifacts, and memory proposals: `5 passed`
- demo runtime now serves AgentCore artifact, memory, and action-decision endpoints: `3 passed`
- combined focused AgentCore frontend suites: `3 passed`, `10 tests passed`
- frontend lint: passed
- i18n coverage: passed
- full frontend test suite: passed

Files changed in this milestone:

- `frontend/hooks/use-agent-core.ts`
- `frontend/components/bioinfoflow/agent-core/agent-core-chat.tsx`
- `frontend/lib/agent-core/client.ts`
- `frontend/lib/runtime/demo-runtime.ts`
- `frontend/messages/en.json`
- `frontend/messages/zh-CN.json`
- `frontend/tests/unit/hooks/use-agent-core.test.tsx`
- `frontend/tests/unit/components/agent-core-chat.test.tsx`
- `frontend/tests/unit/lib/runtime/demo-runtime.test.ts`

Additional Phase 9 AgentCore user-input clarification UI milestone verification passed:

```bash
cd frontend
TMPDIR=/private/tmp bun run test tests/unit/components/agent-core-chat.test.tsx
TMPDIR=/private/tmp bun run test tests/unit/lib/runtime/demo-runtime.test.ts
TMPDIR=/private/tmp bun run test tests/unit/components/agent-core-chat.test.tsx tests/unit/lib/runtime/demo-runtime.test.ts
TMPDIR=/private/tmp bun run lint
TMPDIR=/private/tmp bun run lint:i18n
TMPDIR=/private/tmp bun run test
```

Observed result:

- `AgentCoreChat` now renders `user_input.requested` / `user_input.resolved` clarification cards from the event ledger: `6 passed`
- demo runtime now seeds resolved `user_input` events for the AgentCore demo turn: `3 passed`
- combined focused AgentCore clarification suites: `2 passed`, `9 tests passed`
- frontend lint: passed
- i18n coverage: passed
- full frontend test suite: passed

Files changed in this milestone:

- `frontend/components/bioinfoflow/agent-core/agent-core-chat.tsx`
- `frontend/lib/runtime/demo-runtime.ts`
- `frontend/messages/en.json`
- `frontend/messages/zh-CN.json`
- `frontend/tests/unit/components/agent-core-chat.test.tsx`
- `frontend/tests/unit/lib/runtime/demo-runtime.test.ts`

Additional Phase 9 platform LLM catalog settings UI milestone verification passed:

```bash
cd frontend
TMPDIR=/private/tmp bun run test tests/unit/components/settings-page.test.tsx
TMPDIR=/private/tmp bun run test tests/unit/lib/runtime/demo-runtime.test.ts
TMPDIR=/private/tmp bun run test tests/unit/components/settings-page.test.tsx tests/unit/lib/runtime/demo-runtime.test.ts
TMPDIR=/private/tmp bun run lint
TMPDIR=/private/tmp bun run lint:i18n
TMPDIR=/private/tmp bun run test
```

Observed result:

- settings providers section now renders platform `/llm/*` catalog data, including providers, models, model profiles, provider test, and provider create: `7 passed`
- demo runtime now serves platform LLM catalog endpoints: `4 passed`
- combined focused LLM settings/demo suites: `2 passed`, `11 tests passed`
- frontend lint: passed
- i18n coverage: passed
- full frontend test suite: passed

Files changed in this milestone:

- `frontend/lib/llm/types.ts`
- `frontend/lib/llm/client.ts`
- `frontend/lib/llm/index.ts`
- `frontend/hooks/use-llm-catalog.ts`
- `frontend/components/bioinfoflow/settings/llm-catalog-panel.tsx`
- `frontend/components/bioinfoflow/settings/settings-page-client.tsx`
- `frontend/lib/runtime/demo-runtime.ts`
- `frontend/messages/en.json`
- `frontend/messages/zh-CN.json`
- `frontend/tests/unit/components/settings-page.test.tsx`
- `frontend/tests/unit/lib/runtime/demo-runtime.test.ts`

Additional Phase 10 CLI migration verification passed:

```bash
cd backend
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_cli/test_cli_agent.py -v
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_cli/test_cli_events.py::TestEventsStream tests/test_cli/test_cli_smoke.py::TestHelp::test_agent_help -v
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_cli -v
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_agent_core tests/test_api/test_agent_core_api.py tests/test_api/test_llm_api.py tests/test_cli -v
UV_CACHE_DIR=.uv-cache uv run ruff check .
```

Observed result:

- `bif agent` now exposes AgentCore `session`, `send`, `stream`, `turn`, `action`, `artifacts`, and `events` commands.
- `bif agent send` uses `POST /agent/sessions/{session_id}/turns`; when no session is provided it creates `POST /agent/sessions` first.
- `bif agent stream` uses `GET /agent/sessions/{session_id}/stream` and emits NDJSON in JSON mode.
- `bif agent action approve|reject|modify` uses `POST /agent/actions/{action_id}/decision`.
- `bif agent artifacts list|show|open` uses AgentCore artifact endpoints.
- Legacy `agent history`, `agent approvals`, `--conversation`, `/agent/message`, and `/agent/conversations` are removed from the CLI product surface.
- focused AgentCore CLI tests: `20 passed`
- focused AgentCore/events/smoke CLI tests: `26 passed`
- full CLI test suite: `250 passed`
- combined AgentCore/API/CLI suite: `288 passed`
- backend ruff: passed

Files changed in this milestone:

- `backend/app/cli/commands/agent.py`
- `backend/app/cli/commands/events.py`
- `backend/app/cli/main.py`
- `backend/app/cli/commands/agent_approvals.py` deleted
- `backend/tests/test_cli/test_cli_agent.py`
- `backend/tests/test_cli/test_cli_events.py`
- `backend/tests/test_cli/test_cli_smoke.py`
- `docs/plans/2026-06-04-agent-core-rewrite.md`

Additional Phase 11 backend delegacy cleanup verification passed:

```bash
cd backend
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_agent_core/test_guardrails.py tests/test_api/test_workspace_sharing.py tests/test_api/test_errors.py tests/test_models.py -v
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_cli/test_cli_events.py::TestEventsStream tests/test_api/test_workspace_sharing.py::test_event_stream_rejects_workspace_access_for_system_owned_project tests/test_agent_core/test_guardrails.py -v
UV_CACHE_DIR=.uv-cache uv run ruff check app/models app/repositories app/schemas app/main.py app/api/v1/providers.py app/api/v1/user_settings.py app/services/user_settings_service.py app/services/llm/providers.py tests/test_agent_core/test_guardrails.py tests/test_api/test_workspace_sharing.py tests/test_api/test_errors.py tests/test_models.py
UV_CACHE_DIR=.uv-cache uv run ruff check app/runtime/events.py app/api/v1/events.py tests/test_cli/test_cli_events.py tests/test_agent_core/test_guardrails.py
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_agent_core tests/test_api tests/test_services tests/test_cli tests/test_models.py -v
UV_CACHE_DIR=.uv-cache uv run ruff check .
```

Observed result:

- focused Phase 11 backend guard/workspace/errors/model suites: `23 passed`
- focused events/workspace/guard suites: `12 passed`
- scoped ruff checks for deleted legacy runtime imports and event migrations: passed
- broad backend AgentCore/API/services/CLI/model suite: `701 passed`
- backend ruff: passed

Files changed in this milestone:

- `backend/app/services/llm/providers.py`
- `backend/app/api/v1/providers.py`
- `backend/app/api/v1/user_settings.py`
- `backend/app/services/user_settings_service.py`
- `backend/app/main.py`
- `backend/app/models/__init__.py`
- `backend/app/models/project.py`
- `backend/app/repositories/__init__.py`
- `backend/app/api/v1/events.py`
- `backend/app/runtime/events.py`
- `backend/tests/test_agent_core/test_guardrails.py`
- `backend/tests/conftest.py`
- `backend/tests/test_api/test_scheduler_api.py`
- `backend/tests/test_api/test_workspace_sharing.py`
- `backend/tests/test_api/test_errors.py`
- `backend/tests/test_models.py`
- `backend/app/services/agent/` deleted
- `backend/app/services/hermes_service/` deleted
- old agent/Hermes backend ORM, repository, schema, and test files deleted

Additional Phase 11 frontend legacy renderer cleanup verification passed:

```bash
cd frontend
TMPDIR=/private/tmp bun run test tests/unit/lib/demo/replay-engine.test.ts tests/unit/components/agent-core-chat.test.tsx tests/unit/lib/runtime/demo-runtime.test.ts
rg -n "chat-types|chat-utils|conversation-export|use-chat-scroll|message-bubble|message-list|components/bioinfoflow/chat/parts|ApprovalPart|ChatMessage|SSEEvent|AgentChatStatus|approval_type|sendAgentMessage|AgentConversation|AgentMessage|AgentEventData|ExecutionPolicy" frontend --glob '!node_modules/**' --glob '!coverage/**'
```

Observed result:

- focused demo replay / AgentCore chat / demo runtime suites: `13 passed`
- legacy frontend renderer/type/export reference scan: no matches
- remaining `/agent/message` and `/agent/conversations` references are legacy-route tombstones or negative tests proving those paths are not used

Files changed in this milestone:

- `frontend/components/bioinfoflow/agent-core/agent-core-chat.tsx`
- `frontend/app/(demo)/demo/page.tsx`
- `frontend/lib/demo/types.ts`
- `frontend/lib/demo/replay-engine.ts`
- `frontend/lib/demo/demo-context.tsx`
- `frontend/scripts/check-i18n-coverage.mjs`
- `frontend/hooks/use-llm-settings.ts`
- old legacy chat renderer/export/hook files deleted
- old legacy chat renderer/export tests deleted

Additional Phase 11 backend config and schema cleanup verification passed:

```bash
cd backend
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_auth/test_config_defaults.py tests/test_startup_logging.py tests/test_migrations/test_legacy_scheduler_bridge.py -v
UV_CACHE_DIR=.uv-cache uv run ruff check app/config.py app/startup_logging.py tests/test_auth/test_config_defaults.py tests/test_startup_logging.py tests/test_migrations/test_legacy_scheduler_bridge.py alembic/versions/0029_drop_legacy_agent_tables.py
mkdir -p /private/tmp/bioinfoflow-agentcore-migration/state
rm -f /private/tmp/bioinfoflow-agentcore-migration/state/test.db
UV_CACHE_DIR=.uv-cache BIOINFOFLOW_HOME=/private/tmp/bioinfoflow-agentcore-migration DATABASE_URL=sqlite+aiosqlite:////private/tmp/bioinfoflow-agentcore-migration/state/test.db uv run alembic upgrade head
sqlite3 /private/tmp/bioinfoflow-agentcore-migration/state/test.db "select name from sqlite_master where type='table' and name in ('conversations','messages','agent_traces','agent_approvals','agent_response_handles','agent_approval_handles','agent_sessions','agent_turns','agent_events') order by name;"
```

Observed result:

- config/startup/migration focused tests: `10 passed, 1 skipped`
- scoped backend ruff: passed
- temporary SQLite full Alembic upgrade to head: passed
- post-upgrade table audit returned only `agent_events`, `agent_sessions`, and `agent_turns`; old `conversations`, `messages`, trace, approval, and Hermes handle tables were absent

Files changed in this milestone:

- `backend/app/config.py`
- `backend/app/startup_logging.py`
- `backend/tests/test_auth/test_config_defaults.py`
- `backend/tests/test_startup_logging.py`
- `backend/alembic/versions/0029_drop_legacy_agent_tables.py`
- `backend/tests/test_migrations/test_legacy_scheduler_bridge.py`

### Final Verification Snapshot

Final verification for the current AgentCore replacement state has passed.

```bash
cd backend
rtk env UV_CACHE_DIR=.uv-cache uv run pytest
rtk env UV_CACHE_DIR=.uv-cache uv run ruff check .
rtk env UV_CACHE_DIR=.uv-cache uv run ruff format --check app/config.py app/startup_logging.py tests/test_auth/test_config_defaults.py tests/test_startup_logging.py tests/test_migrations/test_legacy_scheduler_bridge.py alembic/versions/0029_drop_legacy_agent_tables.py
```

Observed result:

- full backend test suite: `951 passed, 1 skipped`
- backend ruff: passed
- scoped backend format check for Phase 11 config/startup/migration files: passed

```bash
cd frontend
rtk env TMPDIR=/private/tmp bun run lint
rtk env TMPDIR=/private/tmp bun run lint:i18n
rtk env TMPDIR=/private/tmp bun run build
rtk env TMPDIR=/private/tmp bun run test
```

Observed result:

- frontend lint: passed
- frontend i18n lint: passed
- frontend production build: passed after replacing `next/font/google` with a local CSS font fallback
- full frontend test suite: passed after hardening `frontend/lib/celebrations.ts` so disconnected canvases stop animation and async draw loops do not read a stale global `window`

```bash
rtk mkdir -p /private/tmp/bioinfoflow-agentcore-migration/state
rtk rm -f /private/tmp/bioinfoflow-agentcore-migration/state/test.db
cd backend
rtk env UV_CACHE_DIR=.uv-cache BIOINFOFLOW_HOME=/private/tmp/bioinfoflow-agentcore-migration DATABASE_URL=sqlite+aiosqlite:////private/tmp/bioinfoflow-agentcore-migration/state/test.db uv run alembic upgrade head
rtk sqlite3 /private/tmp/bioinfoflow-agentcore-migration/state/test.db "select name from sqlite_master where type='table' and name in ('conversations','messages','agent_traces','agent_approvals','agent_response_handles','agent_approval_handles','agent_sessions','agent_turns','agent_events') order by name;"
```

Observed result:

- temporary SQLite full Alembic upgrade to head: passed
- table audit returned only `agent_events`, `agent_sessions`, and `agent_turns`
- old `conversations`, `messages`, `agent_traces`, `agent_approvals`, `agent_response_handles`, and `agent_approval_handles` tables are absent after migration

```bash
rtk bash -lc 'git diff --check'
```

Observed result:

- whitespace check: passed
- note: direct `rtk git diff --check` may return code 2 with no output under the RTK wrapper; use the `rtk bash -lc 'git diff --check'` form for this repository

Final legacy-reference audit:

```bash
rtk bash -lc 'rtk rg -n -P "app\\.services\\.agent(?!_core)|app\\.services\\.hermes_service|AgentConversation|AgentMessageRead|AgentEventData|execution_policy|policy_mode|hermes_session_id|agent_engine|agent_hermes_home|agent_hermes_state_db|agent_hermes_max_concurrency|chat-types|chat-utils|conversation-export|use-chat-scroll|message-bubble|message-list|approval_type" backend/app backend/tests frontend --glob "!docs/**" --glob "!node_modules/**" --glob "!coverage/**" || true'
rtk bash -lc 'rtk rg -n "/agent/message|/agent/conversations|agent history|agent approvals|--conversation|agent_approvals" backend/app backend/tests frontend --glob "!docs/**" --glob "!node_modules/**" --glob "!coverage/**" || true'
```

Observed result:

- old runtime import scan has no production matches for `app.services.agent` or `app.services.hermes_service`
- remaining semantic-name matches are guard tests in `backend/tests/test_agent_core/test_guardrails.py` and config tombstone assertions in `backend/tests/test_auth/test_config_defaults.py`
- old route/CLI scan remaining matches are demo-runtime `404` tombstones, negative frontend/backend tests proving the old endpoints are not called, and migration guard assertions proving `agent_approvals` is removed

### Current Git Constraint

Current changes are mostly staged, but commit may be blocked by sandbox permissions:

```text
fatal: Unable to create '/Users/lewisliu/Dev/ACTIVE/bioinfoflow/.git/worktrees/bioinfoflow9/index.lock': Operation not permitted
```

The same blocker was observed again after the Phase 7 approval/artifact milestone:

```bash
rtk git add -f docs/plans/2026-06-04-agent-core-rewrite.md backend/app/services/agent_core/events.py backend/app/services/agent_core/service.py backend/app/services/agent_core/tools/dispatcher.py backend/app/services/agent_core/sandbox backend/app/services/agent_core/tools/execution backend/tests/test_agent_core/test_tools/test_execution_shell.py
rtk git commit -m "feat: add agent core approval resume artifacts"
```

Both commands failed while trying to create the worktree index lock:

```text
fatal: Unable to create '/Users/lewisliu/Dev/ACTIVE/bioinfoflow/.git/worktrees/bioinfoflow9/index.lock': Operation not permitted
```

The same blocker was observed again after the Phase 8 structured memory milestone:

```bash
rtk git add -f docs/plans/2026-06-04-agent-core-rewrite.md backend/alembic/versions/0028_agent_core_llm_contracts.py backend/app/api/v1/agent.py backend/app/api/v1/llm.py backend/app/api/v1/router.py backend/app/models/__init__.py backend/app/models/agent_core.py backend/app/models/llm.py backend/app/repositories/__init__.py backend/app/repositories/agent_core_repo.py backend/app/repositories/llm_repo.py backend/app/schemas/agent_core.py backend/app/schemas/llm.py backend/app/services/agent_core backend/app/services/bioinformatics backend/app/services/llm backend/tests/test_agent_core backend/tests/test_api/test_agent_core_api.py backend/tests/test_api/test_llm_api.py
rtk git commit -m "feat: add agent core structured memory"
```

Both commands failed while trying to create the worktree index lock:

```text
fatal: Unable to create '/Users/lewisliu/Dev/ACTIVE/bioinfoflow/.git/worktrees/bioinfoflow9/index.lock': Operation not permitted
```

The same blocker was observed again after the Phase 8 skills/plugins foundation milestone:

```bash
rtk git add -f backend/app/services/agent_core/skills.py backend/app/services/agent_core/plugins.py backend/app/services/agent_core/tools/skills backend/tests/test_agent_core/test_skills_plugins.py docs/plans/2026-06-04-agent-core-rewrite.md
rtk git commit -m "feat: add agent core skills plugin registry"
```

Both commands failed while trying to create the worktree index lock:

```text
fatal: Unable to create '/Users/lewisliu/Dev/ACTIVE/bioinfoflow/.git/worktrees/bioinfoflow9/index.lock': Operation not permitted
```

The same blocker was observed again after the Phase 8 read-only subagent boundary milestone:

```bash
rtk git add -f backend/app/services/agent_core/subagents.py backend/tests/test_agent_core/test_subagents.py docs/plans/2026-06-04-agent-core-rewrite.md
rtk git commit -m "feat: add agent core read-only subagents"
```

Both commands failed while trying to create the worktree index lock:

```text
fatal: Unable to create '/Users/lewisliu/Dev/ACTIVE/bioinfoflow/.git/worktrees/bioinfoflow9/index.lock': Operation not permitted
```

The same blocker was observed again after the Phase 9 frontend AgentCore client/hook foundation milestone:

```bash
rtk git add -f frontend/lib/agent-core frontend/hooks/use-agent-core.ts frontend/tests/unit/hooks/use-agent-core.test.tsx docs/plans/2026-06-04-agent-core-rewrite.md
rtk git commit -m "feat: add frontend agent core client"
```

Both commands failed while trying to create the worktree index lock:

```text
fatal: Unable to create '/Users/lewisliu/Dev/ACTIVE/bioinfoflow/.git/worktrees/bioinfoflow9/index.lock': Operation not permitted
```

The same blocker was observed again after the Phase 9 visible AgentCore page replacement milestone:

```bash
rtk git add -f frontend/app/'(app)'/agent/page.tsx frontend/components/bioinfoflow/agent-core frontend/messages/en.json frontend/messages/zh-CN.json docs/plans/2026-06-04-agent-core-rewrite.md
rtk git commit -m "feat: replace agent page with agent core surface"
```

Both commands failed while trying to create the worktree index lock:

```text
fatal: Unable to create '/Users/lewisliu/Dev/ACTIVE/bioinfoflow/.git/worktrees/bioinfoflow9/index.lock': Operation not permitted
```

The same blocker was observed again after the Phase 9 legacy frontend surface removal milestone:

```bash
rtk git add -f docs/plans/2026-06-04-agent-core-rewrite.md frontend
```

The command failed while trying to create the worktree index lock:

```text
fatal: Unable to create '/Users/lewisliu/Dev/ACTIVE/bioinfoflow/.git/worktrees/bioinfoflow9/index.lock': Operation not permitted
```

The same blocker was observed again after the Phase 9 AgentCore action/artifact/memory UI milestone:

```bash
rtk git add -f docs/plans/2026-06-04-agent-core-rewrite.md frontend/hooks/use-agent-core.ts frontend/components/bioinfoflow/agent-core/agent-core-chat.tsx frontend/lib/agent-core/client.ts frontend/lib/runtime/demo-runtime.ts frontend/messages/en.json frontend/messages/zh-CN.json frontend/tests/unit/hooks/use-agent-core.test.tsx frontend/tests/unit/components/agent-core-chat.test.tsx frontend/tests/unit/lib/runtime/demo-runtime.test.ts
```

The command failed while trying to create the worktree index lock:

```text
fatal: Unable to create '/Users/lewisliu/Dev/ACTIVE/bioinfoflow/.git/worktrees/bioinfoflow9/index.lock': Operation not permitted
```

The same blocker was observed again after the Phase 9 AgentCore user-input clarification UI milestone:

```bash
rtk git add -f docs/plans/2026-06-04-agent-core-rewrite.md frontend/components/bioinfoflow/agent-core/agent-core-chat.tsx frontend/lib/runtime/demo-runtime.ts frontend/messages/en.json frontend/messages/zh-CN.json frontend/tests/unit/components/agent-core-chat.test.tsx frontend/tests/unit/lib/runtime/demo-runtime.test.ts
```

The command failed while trying to create the worktree index lock:

```text
fatal: Unable to create '/Users/lewisliu/Dev/ACTIVE/bioinfoflow/.git/worktrees/bioinfoflow9/index.lock': Operation not permitted
```

The same blocker was observed again after the Phase 9 platform LLM catalog settings UI milestone:

```bash
rtk git add -f docs/plans/2026-06-04-agent-core-rewrite.md frontend/lib/llm/types.ts frontend/lib/llm/client.ts frontend/lib/llm/index.ts frontend/hooks/use-llm-catalog.ts frontend/components/bioinfoflow/settings/llm-catalog-panel.tsx frontend/components/bioinfoflow/settings/settings-page-client.tsx frontend/lib/runtime/demo-runtime.ts frontend/messages/en.json frontend/messages/zh-CN.json frontend/tests/unit/components/settings-page.test.tsx frontend/tests/unit/lib/runtime/demo-runtime.test.ts
```

The command failed while trying to create the worktree index lock:

```text
fatal: Unable to create '/Users/lewisliu/Dev/ACTIVE/bioinfoflow/.git/worktrees/bioinfoflow9/index.lock': Operation not permitted
```

The same blocker was observed again after the Phase 10 CLI migration milestone:

```bash
rtk git add -f docs/plans/2026-06-04-agent-core-rewrite.md backend/app/cli/commands/agent.py backend/app/cli/commands/events.py backend/app/cli/main.py backend/app/cli/commands/agent_approvals.py backend/tests/test_cli/test_cli_agent.py backend/tests/test_cli/test_cli_events.py backend/tests/test_cli/test_cli_smoke.py
```

The command failed while trying to create the worktree index lock:

```text
fatal: Unable to create '/Users/lewisliu/Dev/ACTIVE/bioinfoflow/.git/worktrees/bioinfoflow9/index.lock': Operation not permitted
```

The same blocker was observed again after fresh final verification on 2026-06-04:

```bash
rtk git add -f docs/plans/2026-06-04-agent-core-rewrite.md backend frontend
```

The command failed while trying to create the worktree index lock:

```text
fatal: Unable to create '/Users/lewisliu/Dev/ACTIVE/bioinfoflow/.git/worktrees/bioinfoflow9/index.lock': Operation not permitted
```

Fresh verification immediately before this failed stage attempt:

- `cd backend && rtk env UV_CACHE_DIR=.uv-cache uv run pytest`: `951 passed, 1 skipped`
- `cd backend && rtk env UV_CACHE_DIR=.uv-cache uv run ruff check .`: passed
- `cd backend && rtk env UV_CACHE_DIR=.uv-cache uv run ruff format --check app/config.py app/startup_logging.py tests/test_auth/test_config_defaults.py tests/test_startup_logging.py tests/test_migrations/test_legacy_scheduler_bridge.py alembic/versions/0029_drop_legacy_agent_tables.py`: `6 files already formatted`
- `cd frontend && rtk env TMPDIR=/private/tmp bun run lint`: passed
- `cd frontend && rtk env TMPDIR=/private/tmp bun run lint:i18n`: passed
- `cd frontend && rtk env TMPDIR=/private/tmp bun run build`: passed
- `cd frontend && rtk env TMPDIR=/private/tmp bun run test`: passed with exit code 0; existing jsdom/React warning noise remains
- temporary SQLite `alembic upgrade head`: passed; table audit returned only `agent_events`, `agent_sessions`, `agent_turns`
- `rtk bash -lc 'git diff --check'`: passed
- final legacy-reference audit: no production matches for old `app.services.agent` or `app.services.hermes_service`; remaining matches are guard tests, config tombstone assertions, demo-runtime `404` tombstones, and negative tests proving old routes/CLI flags are not used

If commit remains blocked, continue implementation without destructive git operations. Do not request elevated permissions when approval policy is `never`.

Before resuming, run:

```bash
rtk git status --short
rtk git diff --cached --name-only
rtk git diff --name-only
```

Ensure no generated files such as `__pycache__` are staged.

### Next Resume Point

Continue from git commit handling or optional hardening, not from cleanup implementation and not from reconstructing this plan:

- Preserve the current branch/worktree:
  - branch: `codex/agent-core-rewrite`
  - worktree: `/Users/lewisliu/.codex/worktrees/987b/bioinfoflow`
- Treat these as already complete:
  - Phase 9 frontend replacement for the production `/agent` surface
  - Phase 10 `bif agent` migration to AgentCore APIs
  - Phase 11 backend production runtime cleanup for old `app.services.agent` and `app.services.hermes_service`
- Also treat these as already complete:
  - frontend legacy ChatMessage/SSE renderer cleanup
  - demo replay migration to AgentCore turns/events
  - backend legacy/Hermes config cleanup
  - `0029_drop_legacy_agent_tables` schema cleanup migration
- Treat final verification and final legacy-reference audit as already recorded in `Final Verification Snapshot`.
- If code changes again, rerun the verification relevant to the changed files before reporting completion.
- Next concrete task: attempt `git add` / `git commit` for the AgentCore replacement when the environment can write the worktree git index.
- Suggested commit message: `refactor: replace legacy agent with agent core`.
- If the sandbox still blocks `.git/worktrees/.../index.lock`, record the blocker in this plan and final response.

Optional Phase 7/8 hardening can continue in parallel only when needed by the visible product surface:

- richer file edit/code execution abstractions
- diff artifact registration for controlled file edits
- terminal/log retention policy if command output should also be written to disk rather than only ledger/artifact payload
- memory UI/CLI integration

Implementation and verification are complete for the destructive AgentCore replacement described by this plan. Integration remains blocked only if git staging/commit cannot acquire the worktree index lock under the current sandbox.
