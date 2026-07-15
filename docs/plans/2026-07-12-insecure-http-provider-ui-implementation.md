# Insecure HTTP Provider Opt-in Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a provider-scoped insecure HTTP opt-in and redesign the AI provider settings panel into a compact, accessible, risk-aware configuration surface.

**Architecture:** Store `allow_insecure_http` as a first-class provider column and pass it through every provider API contract. Centralize transport validation in the LLM catalog service and reuse it during persistence, model discovery, and AgentCore runtime resolution. Keep the React panel client-side, but separate transport classification and row presentation into focused helpers/components so the long provider list renders predictably and errors stay scoped to the edited provider.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy async, Alembic, pytest, Next.js 16, React 19, TypeScript, Tailwind CSS, Radix Switch, next-intl, Vitest, Testing Library.

---

### Task 1: Persist the provider transport opt-in

**Files:**
- Create: `backend/alembic/versions/0043_llm_provider_insecure_http_opt_in.py`
- Modify: `backend/app/models/llm.py`
- Modify: `backend/app/schemas/llm.py`
- Test: `backend/tests/test_api/test_llm_api.py`

- [ ] **Step 1: Write failing API assertions**

Add a provider setup test that posts:

```python
{
    "template_id": "openai-compatible",
    "name": "Public HTTP Relay",
    "base_url": "http://public-relay.example:8079/v1",
    "api_key": "relay-key",
    "model_ids": ["gpt-5.6-sol"],
    "allow_insecure_http": True,
    "scope": "user",
}
```

Assert status 200 and `data.provider.allow_insecure_http is True`. Add a read assertion through `/llm/configuration`.

- [ ] **Step 2: Run the test and verify RED**

Run: `rtk uv run pytest tests/test_api/test_llm_api.py -k insecure_http -q`

Expected: FAIL because the request/response schemas do not expose the field and public HTTP remains rejected.

- [ ] **Step 3: Add the migration and typed fields**

Create revision `0043_llm_provider_insecure_http_opt_in` with down revision `0042_remote_connection_stored_credentials`:

```python
op.add_column(
    "llm_providers",
    sa.Column(
        "allow_insecure_http",
        sa.Boolean(),
        nullable=False,
        server_default=sa.false(),
    ),
)
```

Downgrade drops the column. Add `allow_insecure_http: Mapped[bool]` to `LlmProvider` and optional/defaulted booleans to create, update, read, and setup Pydantic schemas.

- [ ] **Step 4: Run migration and schema tests**

Run: `rtk uv run alembic upgrade head`

Run: `rtk uv run pytest tests/test_api/test_llm_api.py -k insecure_http -q`

Expected: the schema accepts the field; the behavior test may still fail at transport validation until Task 2.

### Task 2: Enforce explicit transport policy across catalog operations

**Files:**
- Modify: `backend/app/services/llm/catalog.py`
- Modify: `backend/app/services/llm/bootstrap.py`
- Test: `backend/tests/test_services/test_llm_provider_platform.py`
- Test: `backend/tests/test_api/test_llm_api.py`

- [ ] **Step 1: Write failing policy tests**

Extend URL validation tests with:

```python
_validate_provider_base_url(
    "http://public-relay.example:8079/v1",
    allow_insecure_http=True,
)
```

and assert the same URL raises when the flag is false. Add API coverage that model discovery refuses a persisted public HTTP provider whose flag is false.

- [ ] **Step 2: Run tests and verify RED**

Run: `rtk uv run pytest tests/test_services/test_llm_provider_platform.py tests/test_api/test_llm_api.py -k 'insecure_http or validate_provider_base_url' -q`

Expected: FAIL because validation has no opt-in parameter and persistence does not retain it.

- [ ] **Step 3: Implement minimal policy plumbing**

Change the validator signature to:

```python
def _validate_provider_base_url(
    base_url: str | None,
    *,
    allow_insecure_http: bool = False,
) -> None:
```

Keep malformed URL checks unchanged. Return for public HTTP only when `allow_insecure_http` is true. Add a provider helper:

```python
def validate_provider_transport(provider: LlmProvider) -> None:
    _validate_provider_base_url(
        provider.base_url,
        allow_insecure_http=bool(provider.allow_insecure_http),
    )
```

Pass the flag during create, setup, and update. For partial updates, validate the effective URL and effective flag together before persistence. Call `validate_provider_transport` before discovery sends a credential.

- [ ] **Step 4: Preserve bootstrap compatibility**

Environment-managed providers default to `allow_insecure_http=False`. Do not add a global bypass variable. Existing HTTPS and internal HTTP bootstrap tests must remain green.

- [ ] **Step 5: Run policy/API tests and verify GREEN**

Run: `rtk uv run pytest tests/test_services/test_llm_provider_platform.py tests/test_api/test_llm_api.py -q`

Expected: PASS.

### Task 3: Add AgentCore defense-in-depth

**Files:**
- Modify: `backend/app/services/agent_core/runtime.py`
- Test: `backend/tests/test_agent_core/test_runtime_reliability.py`

- [ ] **Step 1: Write a failing runtime test**

Create a provider fixture with a public HTTP base URL and
`allow_insecure_http=False`. Assert runtime model resolution rejects it before
returning request arguments. Add a paired assertion showing the same provider
resolves when the flag is true.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `rtk uv run pytest tests/test_agent_core/test_runtime_reliability.py -k insecure_http -q`

Expected: FAIL because runtime currently accepts any persisted provider URL.

- [ ] **Step 3: Reuse catalog transport validation**

Import `validate_provider_transport` into AgentCore runtime and call it after the
provider is loaded and before credentials or `api_base` are added to request
arguments. Treat a rejected provider as unavailable using the existing selection
fallback behavior; do not leak its credential.

- [ ] **Step 4: Run focused and AgentCore tests**

Run: `rtk uv run pytest tests/test_agent_core/test_runtime_reliability.py -q`

Expected: PASS.

### Task 4: Extend the frontend provider contract and error flow

**Files:**
- Modify: `frontend/lib/llm/types.ts`
- Modify: `frontend/lib/llm/client.ts`
- Modify: `frontend/hooks/use-llm-catalog.ts`
- Create: `frontend/tests/unit/hooks/use-llm-catalog.test.tsx`

- [ ] **Step 1: Write failing hook/client tests**

Assert setup serialization contains:

```typescript
allow_insecure_http: true
```

Assert `setupProvider` exposes the concrete API error to the caller instead of
only converting it to `null`.

- [ ] **Step 2: Run tests and verify RED**

Run: `rtk bun run test frontend/tests/unit/hooks/use-llm-catalog.test.tsx`

Expected: FAIL because types and payload omit the flag and setup errors are not scoped.

- [ ] **Step 3: Implement the contract**

Add `allow_insecure_http: boolean` to provider reads and
`allowInsecureHttp?: boolean` to writes. Serialize it in create, update, and setup
calls. Change the setup hook to return a discriminated result:

```typescript
type SetupProviderOutcome =
  | { ok: true; result: LlmProviderSetupResult }
  | { ok: false; error: Error }
```

Retain the hook-level error for global consumers while enabling row-scoped UI.

- [ ] **Step 4: Run focused frontend tests and verify GREEN**

Run: `rtk bun run test frontend/tests/unit/hooks/use-llm-catalog.test.tsx`

Expected: PASS.

### Task 5: Redesign the provider catalog panel

**Files:**
- Modify: `frontend/components/bioinfoflow/settings/llm-catalog-panel.tsx`
- Test: `frontend/tests/unit/components/llm-catalog-panel.test.tsx`

- [ ] **Step 1: Write failing component tests**

Cover these behaviors:

- a public HTTP endpoint reveals an unchecked “Allow insecure HTTP” switch;
- enabling the switch submits `allowInsecureHttp: true`;
- the target URL and `gpt-5.6-sol` stay in the submitted payload;
- a failed setup shows the API message inside only the edited provider card;
- catalog loading renders provider-shaped skeleton rows;
- catalog load failure renders a retry button;
- provider actions remain inside each provider group.

- [ ] **Step 2: Run the component test and verify RED**

Run: `rtk bun run test frontend/tests/unit/components/llm-catalog-panel.test.tsx`

Expected: FAIL because the switch, scoped errors, skeletons, and retry state do not exist.

- [ ] **Step 3: Implement focused UI helpers**

Keep URL classification outside the render body:

```typescript
function isPublicPlainHttpEndpoint(value: string) {
  // Advisory UI classification only; backend remains authoritative.
}
```

Use module-level helper components for provider status, labelled fields, warning
panel, row error, and loading skeleton. Avoid defining components inside
`LlmCatalogPanel`. Use a Map for provider lookup and stable primitive effect
dependencies where possible.

- [ ] **Step 4: Apply the approved visual layout**

Use compact cards with:

```text
desktop:  identity | responsive field grid | actions
mobile:   identity -> fields -> warning/error -> actions
```

Use warm neutral surfaces, one-pixel borders, 8-10px radii, pale green/yellow
semantic states, no gradients, and no heavy shadows. Add visible labels above
inputs, prevent action wrapping on wide screens, and let endpoint cards expand
only when warnings/errors are present.

- [ ] **Step 5: Run component tests and verify GREEN**

Run: `rtk bun run test frontend/tests/unit/components/llm-catalog-panel.test.tsx`

Expected: PASS.

### Task 6: Add bilingual copy and integration coverage

**Files:**
- Modify: `frontend/messages/en.json`
- Modify: `frontend/messages/zh-CN.json`
- Modify: `frontend/tests/integration/pages/settings-page-flow.test.tsx`
- Modify: `frontend/tests/unit/components/settings-page.test.tsx`

- [ ] **Step 1: Add failing integration assertions**

Assert settings integration exposes the new switch, safety copy, inline error,
retry copy, and saved insecure status using realistic provider data.

- [ ] **Step 2: Run integration tests and verify RED**

Run: `rtk bun run test frontend/tests/integration/pages/settings-page-flow.test.tsx frontend/tests/unit/components/settings-page.test.tsx`

Expected: FAIL for missing translation keys and UI states.

- [ ] **Step 3: Add English and Chinese messages**

Add synchronized keys for field labels, insecure transport title/description,
enabled risk status, load failure, retry, and concrete save error fallback.

- [ ] **Step 4: Run i18n and integration checks**

Run: `rtk bun run lint:i18n`

Run: `rtk bun run test frontend/tests/integration/pages/settings-page-flow.test.tsx frontend/tests/unit/components/settings-page.test.tsx`

Expected: PASS.

### Task 7: Full verification, visual QA, and delivery

**Files:**
- Modify only files required by failures discovered during verification.

- [ ] **Step 1: Run backend verification**

From `backend/`:

```bash
rtk uv run pytest
rtk uv run ruff check .
rtk uv run alembic upgrade head
```

- [ ] **Step 2: Run frontend verification**

From `frontend/`:

```bash
rtk bun run lint
rtk bun run lint:i18n
rtk bun run lint:dead-code
rtk bun run test
```

- [ ] **Step 3: Perform browser verification**

Start the current worktree backend/frontend with `AUTH_MODE=dev`. Verify desktop
and narrow viewport layouts, inline safety warning, switch interaction, target
URL persistence, loading skeleton, error state, and no unwanted wrapping or
excess vertical gaps. Save screenshots as temporary verification artifacts, not
tracked product assets.

- [ ] **Step 4: Review the complete diff**

Run:

```bash
rtk git diff --check
rtk git status --short
rtk git diff --stat origin/main...HEAD
```

Confirm every design requirement has direct code/test/visual evidence.

- [ ] **Step 5: Sync and publish**

```bash
rtk git fetch origin --prune
rtk git rebase origin/main
rtk git push -u origin codex/allow-insecure-http-provider-ui
```

Open a PR titled `feat: allow explicit insecure HTTP providers` and include the
transport policy, UI redesign, migration, and verification results.
