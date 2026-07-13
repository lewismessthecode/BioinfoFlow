# Permission Policy Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make permission changes live and auditable during active turns, make approval batches durable and idempotent, evaluate local and SSH commands with target-aware risk, and provide clear transactional permission UI.

**Architecture:** Resolve one fresh versioned permission context before every tool authorization. Persist each assistant tool-call group as a database batch and continue the model only after every call has a terminal result. Use conditional database transitions for decisions and execution claims. Keep approval policy separate from the local or remote execution boundary.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, pytest, Next.js 16, React 19, next-intl, Vitest, Testing Library.

---

## Status

Tasks 1-5 are implemented and committed. Task 6 documentation, compatibility,
and generated-contract work is complete; full-suite verification remains the
next gate before parallel final review and publication.

## File Structure

- Create `backend/alembic/versions/0044_agent_permission_policy.py`: policy version and action audit schema.
- Create migrations `0045`-`0047`: durable tool-call batches, stable batch ordering, and turn-local batch sequencing.
- Modify `backend/app/models/agent_core.py`: batch model and authorization audit fields.
- Modify `backend/app/repositories/agent_core_repo.py`: fresh reads and conditional transitions.
- Create `backend/app/services/agent_core/permissions/context.py`: immutable fresh permission context resolver.
- Create `backend/app/services/agent_core/tools/batches.py`: batch creation, resolution, continuation, and recovery decisions.
- Create `backend/app/services/agent_core/permissions/command_risk.py`: shared target-aware command assessment.
- Modify `backend/app/services/agent_core/core/loop.py`: batch barrier and fresh authorization contexts.
- Modify `backend/app/services/agent_core/tools/executor.py`: fresh context, audit snapshot, and conditional action claim.
- Modify `backend/app/services/agent_core/actions.py`: persist batch and policy audit data.
- Modify `backend/app/services/agent_core/service.py`: idempotent decisions, pending strategies, batch-aware recovery.
- Modify `backend/app/services/agent_core/tools/execution/shell.py` and `tools/remote/resources.py`: shared command assessment.
- Modify `backend/app/schemas/agent_core.py`, `backend/app/api/v1/agent.py`, and OpenAPI contracts: expose policy version, pending strategy, target and batch audit.
- Modify `frontend/hooks/use-agent-runtime.ts` and `frontend/lib/agent-runtime/*`: transactional permission updates and pending strategy API.
- Modify `frontend/components/bioinfoflow/agent-runtime/agent-composer.tsx`, `agent-workbench.tsx`, and `inline-approval-card.tsx`: accessible selector, pending confirmation, target details, and per-card progress/error.
- Modify both locale files and focused backend/frontend tests.
- Modify `docs/architecture.md`, `docs/security.md`, and `docs/reference/architecture.md`: durable behavior and security boundary.

## Task 1: Fresh Versioned Permission Context

**Files:** migration, agent models/repositories, new permission context module, executor/action service, schema/API, backend permission and API tests.

- [x] Write failing migration/model tests proving existing sessions default to policy version 1 and actions expose evaluated version/snapshot.
- [x] Write a two-`AsyncSession` regression test: load guarded policy in the loop session, commit bypass in another session, and assert the next high-risk action is allowed.
- [x] Write the reverse bypass-to-guarded test and a coherent snapshot test that changes target/toolset/role together.
- [x] Run the focused tests and confirm failures are caused by missing versioned fresh resolution.
- [x] Add migration `0044`, model fields, forced-fresh repository query, and immutable `PermissionContextResolver`.
- [x] Increment `permission_policy_version` atomically whenever permission mode, automation mode, toolset, role, or execution target changes.
- [x] Resolve the context immediately before exposure/risk evaluation and persist its bounded snapshot on the action/events.
- [x] Run focused backend tests, migration tests, and Ruff; fix only Task 1 failures.
- [x] Commit `fix: apply permission updates to active turns`.

## Task 2: Durable Tool-call Batch Barrier

**Files:** batch model/repository/service, loop/transcript/context assembler, runner, focused loop/harness/runtime tests.

- [x] Write failing tests for a model response containing three approval-gated calls: deciding one must not call the model; resolving all must continue exactly once with one result per tool-call id.
- [x] Write failing mixed read/approval/read, approve/reject, interaction-exclusive, and restart-recovery tests.
- [x] Run tests and confirm the current single-action resume and unmatched-tool-call behavior fails them.
- [x] Persist a batch id, ordinal, batch status, and continuation claim; create all actions/results under the barrier.
- [x] Allow independent reads to execute concurrently while keeping the model blocked until every action is terminal.
- [x] Make interaction tools exclusive and produce explicit terminal results for deferred/cancelled sibling calls.
- [x] Replace direct model continuation from `resume_turn_from_action` with batch resolution plus one claimed continuation.
- [x] Make provider message assembly reject or repair unmatched tool-call ids through explicit terminal results.
- [x] Run focused tests, the AgentCore harness/runtime suites, and Ruff.
- [x] Commit `refactor: persist agent tool call barriers`.

## Task 3: Idempotent Decisions, Claims, and Pending Strategies

**Files:** repositories, service, executor, runner/recovery, schemas/API/client contracts, concurrency and API tests.

- [x] Write failing concurrent decision tests proving two approvals cannot enqueue twice.
- [x] Write failing action-claim tests proving two workers cannot execute the same side effect.
- [x] Write failing recovery tests for waiting+requested, running+waiting, and all-terminal batches.
- [x] Write failing API tests for default `future_only` and explicit `approve_pending_tools`, excluding user-input and plan interactions.
- [x] Run focused tests and verify expected race/semantic failures.
- [x] Implement conditional `UPDATE ... WHERE status = expected RETURNING` repository transitions for decisions, action claims, and batch continuation.
- [x] Make duplicate decisions idempotent or return a stable conflict without duplicate enqueue.
- [x] Implement batch-aware recovery and treat in-process queues as wake-up mechanisms only.
- [x] Add pending strategy response metadata: policy version and affected/excluded/already-resolved counts.
- [x] Recheck hard blocks/protected resources before a requested action becomes running.
- [x] Run focused concurrency/API/recovery tests, broader backend pytest, and Ruff.
- [x] Commit `fix: make agent approvals idempotent`.

## Task 4: Target-aware Local and Remote Command Risk

**Files:** new command assessor, shell risk module/tool integrations, remote tools, action audit, command-risk and remote-tool tests.

- [x] Write failing target-by-mode tests for sandboxed local, unsandboxed local, and remote SSH safe reads, writes, network, destructive, and protected operations.
- [x] Write failing hardline spelling tests for wrappers, command positions, quoted `/`, `//`, `/./`, `/../..`, shell wrappers, separators, and non-command data such as `echo reboot`.
- [x] Write failing remote tests showing root-relative reads can be low risk while unknown/outside/symlink-sensitive paths ask, and connection grants never cross connections.
- [x] Run focused tests and confirm static `remote.exec` and current classifier gaps fail.
- [x] Add the shared command assessor, `CommandTargetProfile`, structured assessment, effects, confidence, protected resources, and boundary reasons.
- [x] Reuse command semantics but adapt results for enforced sandbox, unconfined local execution, remote SSH identity, and container targets.
- [x] Integrate local bash and `remote.exec`; keep structured remote read/list tools preferred and audited.
- [x] Implement the narrow catastrophic floor and protected-resource force-ask behavior without treating heuristics as confinement.
- [x] Persist target/effect/reasons/version in action audit and events.
- [x] Run command-risk, remote-tool, executor, permission tests and Ruff.
- [x] Commit `refactor: unify command risk evaluation`.

## Task 5: Transactional Permission and Approval UI

**Files:** runtime types/client/hook, composer/workbench/approval card, locale files, unit/integration tests.

- [x] Write failing hook tests for success, failure rollback of draft/storage/session, duplicate changes, and stale responses after session switch.
- [x] Write failing component tests for radio selection, busy disabling, control-local retryable error, accessible status/alert, and target-aware copy.
- [x] Write failing workbench tests for zero-pending direct update and pending confirmation with future-only versus approve-pending counts/exclusions.
- [x] Write failing approval-card tests for per-card busy/error/retry and remote target badge.
- [x] Run focused Vitest files and confirm failures are caused by missing transactional UI.
- [x] Extend runtime API/types with pending strategy and reconciliation metadata.
- [x] Implement rollback-safe permission transaction state and stale-response guards in the hook.
- [x] Implement the pending-action confirmation, accessible radio menu, local/remote boundary description, live status, and retry path.
- [x] Add independent approval-card progress/error state and prevent duplicate decisions.
- [x] Add complete English and Simplified Chinese messages.
- [x] Run focused tests, frontend lint, i18n lint, and dead-code lint if exports change.
- [ ] With `AUTH_MODE=dev`, visually verify desktop and narrow layouts for local/remote targets, zero/one/multiple pending actions, busy, and error states.
- [x] Commit `feat: clarify agent permission controls`.

## Task 6: Documentation, Compatibility, and Final Verification

**Files:** architecture/security/reference docs, compatibility tests, generated contract if required.

- [x] Add compatibility tests for existing sessions/actions and clients omitting `pending_strategy`.
- [x] Document approval policy versus sandbox/SSH authority, policy versions, batch barriers, pending strategy, hard blocks, and recovery.
- [x] Regenerate or update OpenAPI contracts using the repository's established command and inspect the diff.
- [x] Run `rtk git diff --check`.
- [ ] From `backend/`, run `rtk uv run pytest` and `rtk uv run ruff check .`.
- [ ] From `frontend/`, run `rtk bun run lint`, `rtk bun run lint:i18n`, `rtk bun run lint:dead-code`, and `rtk bun run test`.
- [ ] Run the frontend production build if dependencies and environment permit.
- [x] Commit `docs: document agent permission boundaries`.

## Task 7: Parallel Final Review and Findings

- [ ] Dispatch independent reviewers for specification compliance, backend concurrency/correctness, security/remote boundary, and frontend UX/accessibility.
- [ ] Give every reviewer its own dedicated goal and the exact commit range.
- [ ] Classify every finding with evidence; reject invalid findings with technical reasoning.
- [ ] Fix all critical and important findings with failing tests first, rerun their focused and broad verification, and commit findings by concern.
- [ ] Re-dispatch reviewers over the repaired range and require all review gates to pass.

## Task 8: Rebase and Publish

- [ ] Fetch `origin --prune` and rebase onto `origin/main` as required by `AGENTS.md`.
- [ ] Rerun full backend/frontend verification after the rebase.
- [ ] Inspect final status, diff, migration chain, commits, and requirement checklist.
- [ ] Push `codex/permission-policy-refactor` with tracking.
- [ ] Open a ready-for-review PR with a Conventional Commit title and a body covering root cause, architecture, local/remote behavior, migrations, UI, tests, and visual verification.
