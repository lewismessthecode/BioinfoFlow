# Agent-First Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a verified localhost one-line install that opens directly into an Agent-first demo, connects a model without leaving the composer, runs a pre-seeded biological workflow through the normal approval path, and is accurately described by bilingual READMEs.

**Architecture:** Reuse the existing provider catalog and Agent runtime, add one shared provider-connection operation, introduce a user-scoped idempotent demo bootstrap API, and distribute a localhost-only release bundle with pinned multi-architecture images. Keep team/public deployment and advanced provider configuration on their existing paths.

**Tech Stack:** FastAPI, SQLAlchemy async, WDL/MiniWDL, Next.js 16, React 19, next-intl, Vitest, Playwright, Docker Compose, POSIX shell, GitHub Actions.

---

## File Structure

### Provider and composer

- Create `frontend/hooks/use-provider-connection.ts`: one recoverable setup, discovery, selection, and probe operation shared by Agent and Settings.
- Create `frontend/components/bioinfoflow/agent-runtime/connect-model-dialog.tsx`: compact provider/key dialog.
- Create `frontend/hooks/use-animated-placeholder.ts`: isolated accessible type/delete state machine.
- Modify `frontend/components/bioinfoflow/agent-runtime/agent-composer.tsx`: accept stable accessible label plus animated visual placeholder.
- Modify `frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx`: show the compact connect action and short contextual starters.
- Modify `frontend/hooks/use-llm-settings.ts`: expose refresh and programmatic selection required after connection.
- Modify `frontend/components/bioinfoflow/settings/llm-catalog-panel.tsx`: use the same connection operation where the quick setup path overlaps.
- Modify `frontend/messages/en.json` and `frontend/messages/zh-CN.json`: paired copy.

### Installer and release

- Create `docker-compose.local.yml`: loopback-only, no-auth, explicit identity-mounted home, pinned app images.
- Create `scripts/install.sh`: versioned installer and lifecycle commands.
- Create `scripts/tests/install-test.sh`: fake-command shell harness.
- Modify `.github/workflows/container-release.yml`: amd64/arm64 builds and localhost frontend variant.
- Create or modify the release workflow to attach installer artifacts and checksums.

### Demo bootstrap

- Create `backend/app/demo_assets/quickstart/`: WDL, sample sheet, tiny FASTQ-like inputs.
- Create `backend/app/services/demo_bootstrap_service.py`: idempotent current-user bootstrap and repair boundary.
- Create `backend/app/api/v1/first_run.py`: current-workspace endpoint.
- Modify `backend/app/api/v1/router.py`: route registration.
- Create `frontend/lib/first-run.ts` and `frontend/hooks/use-first-run.ts`: bootstrap client/state.
- Modify `frontend/app/(app)/app-layout.tsx`: select a newly seeded demo once without overriding existing selections.
- Modify Agent workbench state to attach the seeded workflow and submit a starter turn.

### Documentation

- Create `.agents/product-marketing.md`: durable audience, problem, differentiation, objections, voice, and conversion context.
- Rewrite `README.md` and `README.zh-CN.md` with factual parity.
- Update `docs/getting-started/docker.md`, `RUNBOOK.md`, and `docs/security.md` for the localhost installer boundary.

## Task 1: Lock Provider Reliability and Kimi Behavior

**Files:**
- Modify: `backend/tests/test_api/test_llm_api.py`
- Modify: `backend/tests/test_services/test_llm_provider_platform.py`
- Modify: `backend/tests/test_services/test_llm_provider_routing.py`
- Modify if required by failing tests: `backend/app/services/llm/provider_templates.py`
- Modify if required by failing tests: `backend/app/services/llm/catalog.py`

- [ ] **Step 1: Add regression tests**

Cover the following exact invariants:

```python
assert templates["kimi"].default_base_url == "https://api.moonshot.ai/v1"
assert templates["kimi-cn"].default_base_url == "https://api.moonshot.cn/v1"
assert route_provider_model_name("kimi", "kimi-k2") == "openai/kimi-k2"
assert route_provider_model_name("kimi_cn", "kimi-k2") == "openai/kimi-k2"
```

Add API/service cases proving a saved credential remains configured when model
discovery or the subsequent probe fails, and legacy `.cn` Kimi records resolve
to the China template.

- [ ] **Step 2: Run the focused tests and confirm the new assertions fail only where behavior is missing**

Run from `backend/`:

```bash
rtk uv run pytest tests/test_api/test_llm_api.py tests/test_services/test_llm_provider_platform.py tests/test_services/test_llm_provider_routing.py -q
```

- [ ] **Step 3: Implement the smallest backend correction exposed by the tests**

Do not create a second provider setup API. Preserve the current template split,
credential encryption, and existing provider IDs.

- [ ] **Step 4: Verify provider tests and lint**

```bash
rtk uv run pytest tests/test_api/test_llm_api.py tests/test_services/test_llm_provider_platform.py tests/test_services/test_llm_provider_routing.py -q
rtk uv run ruff check app/services/llm tests/test_api/test_llm_api.py tests/test_services/test_llm_provider_platform.py tests/test_services/test_llm_provider_routing.py
```

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/services/llm backend/tests/test_api/test_llm_api.py backend/tests/test_services/test_llm_provider_platform.py backend/tests/test_services/test_llm_provider_routing.py
rtk git commit -m "fix: make provider connection recoverable"
```

## Task 2: Add Shared Provider Connection and Minimal Composer UI

**Files:**
- Create: `frontend/hooks/use-provider-connection.ts`
- Create: `frontend/components/bioinfoflow/agent-runtime/connect-model-dialog.tsx`
- Modify: `frontend/hooks/use-llm-catalog.ts`
- Modify: `frontend/hooks/use-llm-settings.ts`
- Modify: `frontend/components/bioinfoflow/settings/llm-catalog-panel.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`
- Test: `frontend/tests/unit/hooks/use-llm-catalog.test.tsx`
- Test: `frontend/tests/unit/hooks/use-llm-settings.test.ts`
- Test: `frontend/tests/unit/components/llm-catalog-panel.test.tsx`
- Test: `frontend/tests/unit/components/agent-workbench.test.tsx`

- [ ] **Step 1: Write failing connection-state tests**

Define a typed outcome with these stages:

```ts
type ProviderConnectionFailureStage = "setup" | "discovery" | "model" | "probe"
type ProviderConnectionOutcome =
  | { ok: true; providerId: string; modelId: string; modelName: string }
  | { ok: false; stage: ProviderConnectionFailureStage; error: Error; providerId?: string }
```

Tests must prove successful connection, saved-provider discovery failure,
no-usable-model failure, probe failure, automatic model selection, and refresh.

- [ ] **Step 2: Implement `use-provider-connection.ts`**

Compose existing client operations; do not copy credential or provider-template
logic. Keep a saved provider ID in failure outcomes after setup succeeds.

- [ ] **Step 3: Add compact dialog tests before UI implementation**

Assert:

- no model shows `Connect a model` on the empty Agent surface;
- OpenAI, Anthropic, and DeepSeek are directly available;
- `More providers` navigates to the existing provider settings section;
- the dialog contains one key input and remains open on failure;
- messages distinguish setup, discovery, model, and probe failures;
- success closes the dialog and restores composer focus.

- [ ] **Step 4: Implement the dialog under minimalist UI constraints**

Reuse existing Dialog primitives, font, icon wrapper, neutral colors, and
composer spacing. Use no gradient, large card, heavy shadow, new icon library,
or onboarding copy block. Keep the container radius at or below 8 px.

- [ ] **Step 5: Make Settings use the shared operation where behavior overlaps**

Preserve the full advanced catalog while eliminating divergent quick-setup
request order.

- [ ] **Step 6: Add bilingual copy and verify**

```bash
rtk bun run test tests/unit/hooks/use-llm-catalog.test.tsx tests/unit/hooks/use-llm-settings.test.ts tests/unit/components/llm-catalog-panel.test.tsx tests/unit/components/agent-workbench.test.tsx
rtk bun run lint:i18n
rtk bun run lint
```

- [ ] **Step 7: Commit**

```bash
rtk git add frontend/hooks frontend/components/bioinfoflow/agent-runtime frontend/components/bioinfoflow/settings/llm-catalog-panel.tsx frontend/messages frontend/tests
rtk git commit -m "feat: connect models from the agent composer"
```

## Task 3: Add Accessible Dynamic Composer Placeholder

**Files:**
- Create: `frontend/hooks/use-animated-placeholder.ts`
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-composer.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`
- Test: `frontend/tests/unit/components/agent-composer.test.tsx`
- Test: `frontend/tests/unit/components/agent-workbench.test.tsx`

- [ ] **Step 1: Write fake-timer tests for the state machine**

Prove type, pause, fast delete, and next-string behavior. Prove animation stops
when focused, when value is non-empty, on reduced motion, and after unmount.

- [ ] **Step 2: Implement an isolated hook**

Use `setTimeout`, clean every timer, accept `enabled`, `focused`, `value`, and a
localized string list. Return a stable complete placeholder under reduced
motion. Do not mutate layout or expose intermediate strings as an ARIA label.

- [ ] **Step 3: Wire the visual placeholder without changing composer layout**

Keep `aria-label` stable and localized. The existing textarea remains the only
input element.

- [ ] **Step 4: Verify tests, i18n, and lint**

```bash
rtk bun run test tests/unit/components/agent-composer.test.tsx tests/unit/components/agent-workbench.test.tsx
rtk bun run lint:i18n
rtk bun run lint
```

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/hooks/use-animated-placeholder.ts frontend/components/bioinfoflow/agent-runtime frontend/messages frontend/tests/unit/components
rtk git commit -m "feat: animate agent composer prompts"
```

## Task 4: Build the Localhost Release Installer

**Files:**
- Create: `docker-compose.local.yml`
- Create: `scripts/install.sh`
- Create: `scripts/tests/install-test.sh`
- Modify: `.github/workflows/container-release.yml`
- Modify or create: `.github/workflows/release.yml`
- Modify if necessary: `frontend/Dockerfile`

- [ ] **Step 1: Write the shell harness first**

Use temporary `HOME` and fake `docker`, `curl`, checksum, and opener commands.
Cover missing Compose, daemon down, remote context, amd64/arm64 mapping,
unsupported architecture, occupied ports, interrupted download, checksum
failure, pull/up failure, health timeout diagnostics, idempotent rerun, update,
uninstall preservation, and explicit purge.

- [ ] **Step 2: Add the localhost Compose contract**

It must render with:

```yaml
ports:
  - "127.0.0.1:${FRONTEND_PORT:-3000}:3000"
  - "127.0.0.1:${BACKEND_PORT:-8000}:8000"
```

Require an absolute `BIOINFOFLOW_HOME`, mount it at the identical container
path, use a local Unix Docker socket, set dev auth for backend and localhost
frontend variant, and reference versioned images.

- [ ] **Step 3: Implement POSIX installer lifecycle**

Support default install/repair, `--dry-run`, `--version`, `--update`,
`--uninstall`, `--purge`, and `--no-open`. Use modes 700/600, atomic downloads,
same-release checksums, bounded health polling, and bounded failure logs. Never
prompt for or store an API key.

- [ ] **Step 4: Publish multi-architecture application images**

Set `platforms: linux/amd64,linux/arm64` for backend and frontend builds. Publish
an explicit localhost frontend variant with dev auth compiled in. Preserve the
authenticated personal/team image path.

- [ ] **Step 5: Attach version-matched installer artifacts**

Release assets include `install.sh`, `docker-compose.local.yml`, and SHA-256
checksums. Image references match the selected release tag.

- [ ] **Step 6: Verify shell and Compose behavior**

```bash
rtk sh -n scripts/install.sh scripts/tests/install-test.sh
rtk shellcheck scripts/install.sh scripts/tests/install-test.sh
rtk sh scripts/tests/install-test.sh
rtk docker compose --env-file scripts/tests/fixtures/local.env -f docker-compose.local.yml config
```

If ShellCheck is unavailable, install it or record that external prerequisite
before proceeding; do not claim the phase fully verified without it.

- [ ] **Step 7: Commit**

```bash
rtk git add docker-compose.local.yml scripts .github/workflows frontend/Dockerfile
rtk git commit -m "feat: add localhost installer"
```

## Task 5: Seed a Real Demo Project, Workflow, and Data

**Files:**
- Create: `backend/app/demo_assets/quickstart/workflow.wdl`
- Create: `backend/app/demo_assets/quickstart/samples.tsv`
- Create: `backend/app/demo_assets/quickstart/sample-a.fastq`
- Create: `backend/app/demo_assets/quickstart/sample-b.fastq`
- Create: `backend/app/services/demo_bootstrap_service.py`
- Create: `backend/app/api/v1/first_run.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/test_api/test_first_run.py`
- Test or extend: `backend/tests/test_services/test_run_compiler.py`

- [ ] **Step 1: Write bootstrap API tests**

Cover fresh creation, exact project/workflow/binding/pin/data state, repeated
calls, missing-file repair, missing-binding repair, concurrent calls, workspace
isolation, and no automatic creation for a non-fresh workspace.

- [ ] **Step 2: Add deterministic demo assets**

Use a two- or three-stage WDL with one small pinned multi-architecture image.
Inputs are local bundled files; outputs include a TSV summary and readable
report with deterministic assertions.

- [ ] **Step 3: Implement user-scoped idempotent bootstrap**

Create a normal managed user project rather than a system or undeletable
default project. Use stable marker metadata, repository/service boundaries, and
transaction-safe duplicate handling. Repair canonical assets without
overwriting unrelated user content.

- [ ] **Step 4: Register the endpoint and verify compilation**

The response includes `ready`, `created`, `demo_project_id`, `workflow_id`, and
the canonical starter context required by the frontend.

- [ ] **Step 5: Run backend checks**

```bash
rtk uv run pytest tests/test_api/test_first_run.py tests/test_services/test_run_compiler.py -q
rtk uv run ruff check app/api/v1/first_run.py app/services/demo_bootstrap_service.py tests/test_api/test_first_run.py
```

- [ ] **Step 6: Commit**

```bash
rtk git add backend/app/demo_assets backend/app/services/demo_bootstrap_service.py backend/app/api/v1 backend/tests
rtk git commit -m "feat: seed the bioinfoflow demo"
```

## Task 6: Activate the Demo in Agent and Keep Starters Short

**Files:**
- Create: `frontend/lib/first-run.ts`
- Create: `frontend/hooks/use-first-run.ts`
- Modify: `frontend/app/(app)/app-layout.tsx`
- Modify: `frontend/components/bioinfoflow/agent-runtime/agent-workbench.tsx`
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`
- Test: `frontend/tests/integration/components/app-layout-coordination.test.tsx`
- Test: `frontend/tests/unit/components/agent-workbench.test.tsx`
- Test: `frontend/tests/integration/pages/agent-page.test.tsx`
- Test: `frontend/tests/e2e/agent-first-analysis.spec.ts`

- [ ] **Step 1: Add failing first-run coordination tests**

Prove the freshly created demo becomes active exactly once and remembered or
existing project choices are not replaced.

- [ ] **Step 2: Add short contextual starter tests**

English and Chinese starters remain comparable to the current screenshot, for
example:

```text
Check and run the demo workflow
Explain the demo inputs
Review the latest demo run
```

The primary click attaches the seeded workflow and submits the Agent turn. It
must not call the run API directly or bypass approval.

- [ ] **Step 3: Implement bootstrap coordination and contextual starters**

Keep the current line list, icons, spacing, hover behavior, and maximum visible
count. Generic projects retain generic starters.

- [ ] **Step 4: Verify frontend and E2E behavior**

```bash
rtk bun run test tests/integration/components/app-layout-coordination.test.tsx tests/unit/components/agent-workbench.test.tsx tests/integration/pages/agent-page.test.tsx
rtk bunx playwright test tests/e2e/agent-first-analysis.spec.ts
rtk bun run lint:i18n
rtk bun run lint
```

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/app frontend/components/bioinfoflow/agent-runtime frontend/hooks/use-first-run.ts frontend/lib/first-run.ts frontend/messages frontend/tests
rtk git commit -m "feat: start new users in an agent demo"
```

## Task 7: Rewrite Product Context and Bilingual READMEs

**Files:**
- Create: `.agents/product-marketing.md`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `docs/getting-started/docker.md`
- Modify: `RUNBOOK.md`
- Modify: `docs/security.md`

- [ ] **Step 1: Write the product-marketing context**

Capture the primary audience, operational pains, Agent differentiation,
switching anxiety, anti-personas, exact trust boundaries, restrained technical
voice, and the conversion action `install -> connect -> run demo`.

- [ ] **Step 2: Rewrite both READMEs from the verified product state**

Use this order:

1. One-sentence category and outcome.
2. Product demo.
3. Fast fit/non-fit decision.
4. Verified one-line install.
5. First successful demo.
6. Agent inspect-plan-act-approve-observe loop.
7. Data, model, Docker socket, and deployment boundaries.
8. Source build, authenticated deployment, development, docs, license.

Keep English and Chinese factually equivalent and naturally written. Avoid AI
cliches, unsupported metrics, fake proof, and promises broader than localhost.

- [ ] **Step 3: Update operational docs**

Document the local installer, update/uninstall/purge behavior, authenticated
deployment alternative, data path, loopback binding, and Docker-socket trust
boundary.

- [ ] **Step 4: Run copy editing and documentation checks**

Perform clarity, voice, so-what, proof, specificity, emotion, and zero-risk
sweeps. Then run:

```bash
rtk git diff --check
rtk rg -n "curl -fsSL|~/.bioinfoflow/data|127.0.0.1|Connect a model|连接模型" README.md README.zh-CN.md docs/getting-started/docker.md RUNBOOK.md docs/security.md
```

- [ ] **Step 5: Commit**

```bash
rtk git add -f .agents/product-marketing.md README.md README.zh-CN.md docs/getting-started/docker.md RUNBOOK.md docs/security.md
rtk git commit -m "docs: rewrite bilingual project readmes"
```

## Task 8: Full Verification, Visual Review, and Independent Review

**Files:** All files changed by Tasks 1-7.

- [ ] **Step 1: Run full backend verification**

```bash
rtk uv run pytest
rtk uv run ruff check .
```

- [ ] **Step 2: Run full frontend verification**

```bash
rtk bun run lint
rtk bun run lint:i18n
rtk bun run lint:dead-code
rtk bun run test
rtk bun run build
```

- [ ] **Step 3: Run installer and Compose verification**

```bash
rtk sh -n scripts/install.sh scripts/tests/install-test.sh
rtk shellcheck scripts/install.sh scripts/tests/install-test.sh
rtk sh scripts/tests/install-test.sh
rtk docker compose -f docker-compose.local.yml config
```

- [ ] **Step 4: Perform local visual and behavior review**

Use `AUTH_MODE=dev`, restart the backend/frontend, open `/agent`, and verify:

- no login;
- unchanged starter-list layout and short copy;
- placeholder motion stops on focus/input/reduced motion;
- compact provider dialog matches the existing composer;
- successful provider connection returns focus;
- demo project/workflow/data exist;
- primary starter creates an Agent turn and pauses at normal run approval;
- mobile and desktop layouts remain usable.

- [ ] **Step 5: Dispatch independent parallel reviews**

Request separate reviews for backend/data integrity, frontend UX/accessibility,
installer/security/release, and README accuracy. Fix every critical and
important finding, rerun affected checks, and ask reviewers to confirm fixes.

- [ ] **Step 6: Sync, final audit, and publish**

```bash
rtk git fetch origin --prune
rtk git rebase origin/main
```

Repeat affected verification after rebase. Confirm the branch contains only the
intended scope, push it, and create a ready PR with a Conventional Commit title
and a body listing behavior, boundaries, and exact validation evidence.
