# cch Anthropic Relay Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or execute each task with explicit red/green verification. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Bioinfoflow configure and use cch through its working Anthropic Messages route instead of the currently failing OpenAI-compatible GPT route.

**Architecture:** Keep provider runtime routing provider-agnostic and use the existing Anthropic LiteLLM adapter. Expose a first-class Anthropic-compatible endpoint field in the provider catalog so users can point the Anthropic template at a cch root URL such as `http://8.129.13.231:8079`; LiteLLM then calls `/v1/messages`. Preserve explicit insecure-HTTP opt-in for public HTTP relay endpoints.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic schemas, LiteLLM, Next.js, React, next-intl, Vitest, pytest.

---

## Background Evidence

- cch `GET /v1/models` succeeds with the user's key, so the key and host are reachable.
- cch `POST /v1/responses` with `gpt-5.4` times out after 90 seconds with zero bytes.
- cch `POST /v1/chat/completions` with `gpt-5.4` returns `503 no_available_providers` with `format_type_mismatch`.
- cch `POST /v1/messages` with `claude-sonnet-5` returns `OK`.
- Therefore Bioinfoflow should not patch OpenAI-compatible GPT routing for this relay; it should support Anthropic-compatible custom endpoints.

## Phase 0: Plan and Branch

**Files:**
- Create: `docs/plans/2026-07-15-cch-anthropic-relay.md`

- [ ] Write this plan in `docs/plans/`.
- [ ] Run `rtk git diff --check`.
- [ ] Commit with `docs: plan cch anthropic relay support`.

## Phase 1: Backend Provider Template and API Behavior

**Files:**
- Modify: `backend/app/services/llm/provider_templates.py`
- Modify: `backend/tests/test_services/test_llm_provider_platform.py`
- Modify: `backend/tests/test_api/test_llm_api.py`

- [ ] Add a failing backend template test asserting the Anthropic template exposes a non-required `base_url` field with default `https://api.anthropic.com`.
- [ ] Add a failing API setup test that posts `template_id: "anthropic"`, `base_url: "http://8.129.13.231:8079"`, `allow_insecure_http: true`, `api_key`, and `model_ids: ["claude-sonnet-5"]`; assert the stored provider keeps the root URL, kind `anthropic`, protocol `chat_completions`, and model ID.
- [ ] Run the narrow backend tests and confirm they fail for the expected missing endpoint field behavior.
- [ ] Change the Anthropic provider template to set `base_url_required=False` and expose its endpoint field.
- [ ] Run:

```bash
rtk uv run pytest tests/test_services/test_llm_provider_platform.py tests/test_api/test_llm_api.py -q
rtk uv run ruff check app/services/llm/provider_templates.py tests/test_services/test_llm_provider_platform.py tests/test_api/test_llm_api.py
```

- [ ] Commit with `feat: expose anthropic-compatible endpoints`.

## Phase 2: Frontend Configuration Flow

**Files:**
- Modify: `frontend/tests/unit/components/llm-catalog-panel.test.tsx`
- Modify: `frontend/tests/integration/pages/settings-page-flow.test.tsx` if existing expectations need template fixture updates
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`

- [ ] Add a failing unit test showing the Anthropic provider card renders an Endpoint input when the backend template includes `base_url`.
- [ ] Add a failing unit test showing a public HTTP Anthropic endpoint displays the insecure HTTP opt-in and sends `allowInsecureHttp: true` plus the root base URL to `setupProvider`.
- [ ] Update frontend fixtures for the Anthropic template to include `base_url`.
- [ ] Keep generic endpoint copy; no new user-facing strings are needed unless tests reveal ambiguous copy.
- [ ] Run:

```bash
rtk bun run test -- frontend/tests/unit/components/llm-catalog-panel.test.tsx
rtk bun run lint:i18n
```

- [ ] Commit with `feat: configure anthropic relay endpoints`.

## Phase 3: Documentation and Operator Guidance

**Files:**
- Modify: `.env.example`
- Modify: `RUNBOOK.md` or `docs/operations/runbook.md` if the existing provider section is the better home

- [ ] Add cch guidance explaining that OpenAI-compatible GPT routes may fail independently of Anthropic Messages routes.
- [ ] Document Anthropic-compatible cch setup: base URL is the relay root, for example `http://8.129.13.231:8079`; model is a Claude model from `/v1/models`, for example `claude-sonnet-5`; public HTTP requires explicit opt-in.
- [ ] Run:

```bash
rtk git diff --check
```

- [ ] Commit with `docs: document cch anthropic relay setup`.

## Phase 4: Integrated Validation

**Files:**
- No planned edits unless validation reveals a defect.

- [ ] Run backend focused checks:

```bash
rtk uv run pytest tests/test_services/test_llm_provider_platform.py tests/test_api/test_llm_api.py -q
rtk uv run ruff check .
```

- [ ] Run frontend focused checks:

```bash
rtk bun run test -- frontend/tests/unit/components/llm-catalog-panel.test.tsx
rtk bun run lint
rtk bun run lint:i18n
```

- [ ] If UI layout looks risky, set the worktree `.env` to `AUTH_MODE=dev`, start backend/frontend, and do a browser visual check of Settings -> AI Providers.
- [ ] Commit any validation fixes with `fix: harden cch anthropic relay setup`.

## Phase 5: Parallel Review and PR

- [ ] Spawn parallel review agents after implementation. Give one reviewer backend/API scope, one frontend/UI scope, and one docs/operations scope.
- [ ] Fix Critical and Important findings.
- [ ] Re-run the relevant checks after fixes.
- [ ] Sync with `origin/main` before PR:

```bash
rtk git fetch origin --prune
rtk git rebase origin/main
```

- [ ] Push the branch and open a draft PR with a Conventional Commit style title.

