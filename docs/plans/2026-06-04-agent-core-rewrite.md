# BioInfoFlow AgentCore Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the legacy BioInfoFlow agent with a new AgentCore runtime that keeps Codex/Claude Code style harness capabilities while exposing BioInfoFlow projects, data, workflows, images, runs, logs, results, permissions, memory, skills, plugins, and LLM providers as typed, auditable platform capabilities.

**Architecture:** This is a destructive replacement, not a compatibility refactor. The new source of truth is `AgentSession`, `AgentTurn`, `AgentEvent`, `AgentAction`, `AgentArtifact`, and `AgentMemory`; all observable output is event-ledger-first, and all side effects are action-ledger-first. Provider/model catalog belongs to a platform-level `llm` module; bioinformatics intelligence belongs to deterministic domain services that AgentCore calls through typed tools.

**Tech Stack:** FastAPI, async SQLAlchemy, Alembic, Typer CLI, SSE, SQLite, Next.js App Router, React, Tailwind, Vitest, Playwright, pytest, ruff.

---

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

- [ ] Migrate `bif agent` to new AgentCore APIs.
- [ ] Add `session`, `send`, `stream`, `action`, `artifacts`, and `events` commands.
- [ ] Use NDJSON for streaming.
- [ ] Preserve JSON envelope, exit codes, and config/env precedence.
- [ ] Commit Phase 10 with `feat: migrate bif agent to agent core`.

Gate: CLI and frontend share APIs; old `/agent/message` is unused.

Verification:

```bash
cd backend && uv run pytest tests/test_cli/test_agent.py -v
cd backend && uv run bif --help
cd backend && uv run bif agent --help
cd backend && uv run ruff check .
```

### Phase 11: Final Delegacy

- [ ] Remove old `backend/app/services/agent/` production dependency.
- [ ] Remove Hermes production bridge.
- [ ] Delete old agent schemas/models/repos/tests or convert to deletion verification tests.
- [ ] Delete old frontend types/render path.
- [ ] Delete old config keys.
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
