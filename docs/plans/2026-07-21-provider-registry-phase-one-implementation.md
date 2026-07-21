# Provider Registry Phase One Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the generic provider-template setup path with a backend-owned registry and profile hooks for the twelve approved API-key providers while preserving the existing settings layout.

**Architecture:** A declarative `ProviderSpec` registry owns provider facts and a small profile layer owns catalog, invocation, and error differences. Setup is local and deterministic, discovery is optional and non-destructive, and runtime adaptation happens inside ModelGateway before LiteLLM.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Pydantic, LiteLLM, pytest, Next.js 16, React 19, TypeScript, Vitest.

---

### Task 1: Registry contracts and twelve-provider catalog

**Files:**
- Create: `backend/app/services/llm/registry.py`
- Create: `backend/app/services/llm/profiles/base.py`
- Create: `backend/app/services/llm/profiles/__init__.py`
- Modify: `backend/app/services/llm/provider_templates.py`
- Test: `backend/tests/test_services/test_llm_provider_registry.py`

- [ ] **Step 1: Write failing registry tests**

Define tests asserting exactly the twelve primary IDs, unique kinds, expected endpoints, Qwen override support, Kimi Code's exact three models, and absence of `kimi`/`kimi-cn` templates.

```python
EXPECTED_IDS = {
    "openai", "anthropic", "openrouter", "fireworks", "qwen",
    "deepseek", "xai", "zai", "kimi-code", "minimax",
    "huggingface", "gemini",
}

def test_primary_registry_contains_exact_phase_one_providers():
    assert {spec.id for spec in list_provider_specs()} == EXPECTED_IDS

def test_kimi_code_has_only_official_coding_models():
    spec = get_provider_spec("kimi-code")
    assert [model.id for model in spec.bundled_models] == [
        "k3", "kimi-for-coding", "kimi-for-coding-highspeed"
    ]
    assert spec.endpoint.default_base_url == "https://api.kimi.com/coding/v1"
```

- [ ] **Step 2: Run the tests and confirm RED**

Run from `backend/`:

```bash
rtk uv run pytest tests/test_services/test_llm_provider_registry.py -q
```

Expected: import failure because `app.services.llm.registry` does not exist.

- [ ] **Step 3: Implement immutable registry contracts**

Add `ApiKeyAuthSpec`, `EndpointSpec`, `RuntimeSpec`, `CatalogSpec`, `ModelSpec`, and `ProviderSpec`. Implement a registry with twelve specs and lookup/list functions. Keep `provider_templates.py` as a compatibility facade that converts specs into the existing `ProviderTemplate` shape.

```python
@dataclass(frozen=True)
class ProviderSpec:
    id: str
    name: str
    kind: str
    docs_url: str
    auth: ApiKeyAuthSpec
    endpoint: EndpointSpec
    runtime: RuntimeSpec
    catalog: CatalogSpec
    bundled_models: tuple[ModelSpec, ...] = ()
```

- [ ] **Step 4: Run registry and existing provider-template tests**

```bash
rtk uv run pytest tests/test_services/test_llm_provider_registry.py tests/test_services/test_llm_provider_platform.py -q
```

Expected: PASS after updating obsolete Kimi and exact-provider assertions.

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/services/llm/registry.py backend/app/services/llm/profiles backend/app/services/llm/provider_templates.py backend/tests/test_services/test_llm_provider_registry.py backend/tests/test_services/test_llm_provider_platform.py
rtk git commit -m "refactor: establish llm provider registry"
```

### Task 2: Reviewed bundled model snapshot

**Files:**
- Create: `backend/app/services/llm/catalog_snapshot.json`
- Create: `backend/scripts/update_llm_catalog.py`
- Modify: `backend/app/services/llm/registry.py`
- Test: `backend/tests/test_services/test_llm_catalog_snapshot.py`

- [ ] **Step 1: Write failing snapshot tests**

Test schema validation, approved provider IDs, agent-capable model filtering, stable sorting, and Kimi's pinned list.

```python
def test_snapshot_contains_only_agent_capable_models():
    snapshot = load_catalog_snapshot()
    for models in snapshot.values():
        assert all(model.supports_tools for model in models)
        assert all(model.output_modalities == ("text",) for model in models)
```

- [ ] **Step 2: Verify RED**

```bash
rtk uv run pytest tests/test_services/test_llm_catalog_snapshot.py -q
```

Expected: snapshot loader or file missing.

- [ ] **Step 3: Implement generator and committed snapshot**

The script accepts an input path or downloads models.dev only when run manually. It selects the mapped provider IDs, filters non-agent models, applies provider overrides, and writes deterministic JSON. Runtime loads only the committed file through `importlib.resources`/`Path`.

```python
APPROVED_SOURCE_IDS = {
    "openai": "openai",
    "anthropic": "anthropic",
    "openrouter": "openrouter",
    "fireworks": "fireworks-ai",
    "qwen": "alibaba-cn",
    "deepseek": "deepseek",
    "xai": "xai",
    "zai": "zai",
    "kimi-code": "kimi-for-coding",
    "minimax": "minimax",
    "huggingface": "huggingface",
    "gemini": "google",
}
```

- [ ] **Step 4: Generate twice and prove determinism**

```bash
rtk uv run python scripts/update_llm_catalog.py --input /tmp/models-dev-api.json
rtk shasum app/services/llm/catalog_snapshot.json
rtk uv run python scripts/update_llm_catalog.py --input /tmp/models-dev-api.json
rtk shasum app/services/llm/catalog_snapshot.json
```

Expected: identical hashes.

- [ ] **Step 5: Run tests and commit**

```bash
rtk uv run pytest tests/test_services/test_llm_catalog_snapshot.py tests/test_services/test_llm_provider_registry.py -q
rtk git add backend/app/services/llm/catalog_snapshot.json backend/app/services/llm/registry.py backend/scripts/update_llm_catalog.py backend/tests/test_services/test_llm_catalog_snapshot.py
rtk git commit -m "feat: bundle reviewed llm model catalog"
```

### Task 3: Provider profile catalog strategies

**Files:**
- Create: `backend/app/services/llm/profiles/anthropic.py`
- Create: `backend/app/services/llm/profiles/openrouter.py`
- Create: `backend/app/services/llm/profiles/gemini.py`
- Create: `backend/app/services/llm/profiles/minimax.py`
- Modify: `backend/app/services/llm/profiles/base.py`
- Modify: `backend/app/services/llm/profiles/__init__.py`
- Test: `backend/tests/test_services/test_llm_provider_profiles.py`

- [ ] **Step 1: Write failing request-plan tests**

Assert default Bearer `/models`, Anthropic headers, OpenRouter public catalog, Gemini `x-goog-api-key`, MiniMax bundled-only behavior, and safe base URL composition.

```python
def test_anthropic_catalog_request_uses_native_headers():
    request = profile_for("anthropic").catalog_request(connection("secret"))
    assert request.url == "https://api.anthropic.com/v1/models"
    assert request.headers["x-api-key"] == "secret"
    assert request.headers["anthropic-version"] == "2023-06-01"
```

- [ ] **Step 2: Verify RED**

```bash
rtk uv run pytest tests/test_services/test_llm_provider_profiles.py -q
```

- [ ] **Step 3: Implement catalog request plans and parsers**

Profiles return typed `CatalogRequest` objects and parse provider payloads. They do not create unrestricted HTTP clients; `LlmCatalogService` executes requests through the existing network-policy client.

- [ ] **Step 4: Run tests and commit**

```bash
rtk uv run pytest tests/test_services/test_llm_provider_profiles.py -q
rtk git add backend/app/services/llm/profiles backend/tests/test_services/test_llm_provider_profiles.py
rtk git commit -m "feat: add provider catalog profiles"
```

### Task 4: Deterministic setup and non-destructive discovery

**Files:**
- Modify: `backend/app/services/llm/catalog.py`
- Modify: `backend/app/schemas/llm.py`
- Modify: `backend/tests/test_api/test_llm_api.py`
- Modify: `backend/tests/test_services/test_llm_provider_platform.py`

- [ ] **Step 1: Write failing deterministic-setup tests**

Tests must fail if setup opens an HTTP client, must assert bundled models are returned, and must assert `discover=true` remains local.

```python
async def test_setup_provider_never_accesses_network(monkeypatch, async_client):
    monkeypatch.setattr(
        "app.services.llm.catalog.network_policy_http_client",
        lambda **_: (_ for _ in ()).throw(AssertionError("network accessed")),
    )
    response = await async_client.post(
        "/api/v1/llm/provider-setups",
        json={"template_id": "kimi-code", "api_key": "sk-kimi-test", "discover": True},
    )
    assert response.status_code == 200
    assert {m["model_id"] for m in response.json()["data"]["models"]} == {
        "k3", "kimi-for-coding", "kimi-for-coding-highspeed"
    }
```

- [ ] **Step 2: Write failing non-destructive discovery tests**

Seed bundled/manual/live models, make discovery fail, and assert no model metadata changes. Then return a successful catalog and assert live metadata merges while bundled/manual models remain active.

- [ ] **Step 3: Verify RED**

```bash
rtk uv run pytest tests/test_api/test_llm_api.py -k "setup_provider or discover_models" -q
```

- [ ] **Step 4: Implement registry-driven setup and discovery**

Remove network discovery from `setup_provider`. Upsert bundled models with catalog provenance. Replace the discovery `if` chain with profile resolution, typed request execution, parse/filter, then merge on success.

- [ ] **Step 5: Run focused tests and commit**

```bash
rtk uv run pytest tests/test_api/test_llm_api.py tests/test_services/test_llm_provider_platform.py -q
rtk git add backend/app/services/llm/catalog.py backend/app/schemas/llm.py backend/tests/test_api/test_llm_api.py backend/tests/test_services/test_llm_provider_platform.py
rtk git commit -m "refactor: separate provider setup from discovery"
```

### Task 5: Legacy provider reconciliation

**Files:**
- Modify: `backend/app/services/llm/catalog.py`
- Modify: `backend/app/services/llm/provider_templates.py`
- Test: `backend/tests/test_services/test_llm_provider_platform.py`
- Test: `backend/tests/test_api/test_llm_api.py`

- [ ] **Step 1: Write failing migration tests**

Cover `grok -> xai`, canonical Kimi Code endpoint migration, disabling Moonshot global/China rows without deleting credentials, and legacy out-of-scope provider readability.

- [ ] **Step 2: Verify RED**

```bash
rtk uv run pytest tests/test_services/test_llm_provider_platform.py -k "legacy or reconcile or kimi or grok" -q
```

- [ ] **Step 3: Implement idempotent reconciliation**

Reconciliation runs while building configuration and updates only recognized legacy records. Unsupported Moonshot records get metadata:

```python
{
    "providerTemplate": "legacy-kimi-platform",
    "unsupported_reason": "kimi_open_platform_removed",
}
```

They are disabled; credential rows are preserved.

- [ ] **Step 4: Run tests and commit**

```bash
rtk uv run pytest tests/test_services/test_llm_provider_platform.py tests/test_api/test_llm_api.py -q
rtk git add backend/app/services/llm/catalog.py backend/app/services/llm/provider_templates.py backend/tests/test_services/test_llm_provider_platform.py backend/tests/test_api/test_llm_api.py
rtk git commit -m "fix: reconcile legacy llm providers"
```

### Task 6: Runtime reasoning contract and invocation profiles

**Files:**
- Modify: `backend/app/services/model_runtime/contracts.py`
- Modify: `backend/app/services/model_runtime/gateway.py`
- Modify: `backend/app/services/model_runtime/backend/litellm.py`
- Create: `backend/app/services/llm/profiles/deepseek.py`
- Create: `backend/app/services/llm/profiles/zai.py`
- Create: `backend/app/services/llm/profiles/kimi_code.py`
- Modify: `backend/app/services/llm/profiles/openrouter.py`
- Modify: `backend/app/services/llm/profiles/minimax.py`
- Modify: `backend/app/services/llm/profiles/gemini.py`
- Modify: `backend/app/services/agent_core/runtime.py`
- Test: `backend/tests/test_services/test_model_runtime.py`
- Test: `backend/tests/test_services/test_llm_provider_profiles.py`

- [ ] **Step 1: Write failing normalized reasoning tests**

Add `ReasoningRequest(enabled, effort)` and table tests for DeepSeek, Z.AI, Kimi Code, MiniMax M3, Gemini, and OpenRouter. Assert Kimi never sends both `thinking` and `reasoning_effort`.

- [ ] **Step 2: Verify RED**

```bash
rtk uv run pytest tests/test_services/test_llm_provider_profiles.py tests/test_services/test_model_runtime.py -q
```

- [ ] **Step 3: Implement provider-neutral reasoning contract**

`ModelInvocation` receives `ReasoningRequest`; AgentCore supplies normalized intent. `ModelGateway` obtains invocation options from `profile_for(target.provider_kind)` and merges them into the private LiteLLM request. No provider branch is added to AgentCore.

- [ ] **Step 4: Verify profiles and existing codec tests**

```bash
rtk uv run pytest tests/test_services/test_llm_provider_profiles.py tests/test_services/test_model_runtime.py tests/test_services/test_model_runtime_codecs.py -q
```

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/services/model_runtime backend/app/services/agent_core/runtime.py backend/app/services/llm/profiles backend/tests/test_services/test_llm_provider_profiles.py backend/tests/test_services/test_model_runtime.py
rtk git commit -m "feat: adapt model invocation by provider profile"
```

### Task 7: Structured provider verification and error taxonomy

**Files:**
- Create: `backend/app/services/llm/errors.py`
- Modify: `backend/app/services/llm/probe.py`
- Modify: `backend/app/services/llm/catalog.py`
- Modify: `backend/app/schemas/llm.py`
- Modify: `backend/app/api/v1/llm.py`
- Test: `backend/tests/test_api/test_llm_api.py`
- Test: `backend/tests/test_services/test_llm_provider_profiles.py`

- [ ] **Step 1: Write failing error-classification tests**

Cover 401, 403/model denial, 404/model missing, 429/rate limit, quota errors, network errors, and Kimi endpoint mismatch. Assert secrets and Authorization values never appear.

- [ ] **Step 2: Write failing structured-test response tests**

Assert backward-compatible top-level fields plus `failed_at` and ordered checks for configuration, catalog, and runtime.

- [ ] **Step 3: Verify RED**

```bash
rtk uv run pytest tests/test_api/test_llm_api.py -k "test_provider or provider_auth or discovery" -q
```

- [ ] **Step 4: Implement normalized errors and checkpoints**

Use a finite code enum and safe public details. Catalog is `skipped` where unsupported; overall success requires the runtime probe.

- [ ] **Step 5: Run tests and commit**

```bash
rtk uv run pytest tests/test_api/test_llm_api.py tests/test_services/test_llm_provider_profiles.py -q
rtk git add backend/app/services/llm/errors.py backend/app/services/llm/probe.py backend/app/services/llm/catalog.py backend/app/schemas/llm.py backend/app/api/v1/llm.py backend/tests/test_api/test_llm_api.py backend/tests/test_services/test_llm_provider_profiles.py
rtk git commit -m "feat: report provider verification checkpoints"
```

### Task 8: Preserve the existing frontend layout with backend-owned behavior

**Files:**
- Modify: `frontend/hooks/use-llm-catalog.ts`
- Modify: `frontend/hooks/use-provider-connection.ts`
- Modify: `frontend/components/bioinfoflow/settings/llm-catalog-panel.tsx`
- Modify: `frontend/lib/llm/types.ts`
- Modify: `frontend/tests/unit/hooks/use-llm-catalog.test.tsx`
- Modify: `frontend/tests/unit/pages/settings-page-flow.test.tsx`
- Modify: `frontend/tests/unit/components/llm-catalog-panel.test.tsx`

- [ ] **Step 1: Write failing frontend behavior tests**

Assert Save calls only `/provider-setups`, setup-returned models populate the selector, and backend error messages are not replaced by generic discovery text. Keep layout snapshots/role assertions unchanged.

- [ ] **Step 2: Verify RED**

```bash
rtk bun run test -- tests/unit/hooks/use-llm-catalog.test.tsx tests/unit/pages/settings-page-flow.test.tsx tests/unit/components/llm-catalog-panel.test.tsx
```

- [ ] **Step 3: Remove save-time discovery orchestration**

Merge `result.models` into catalog state after setup. Retain explicit Refresh Models and Test actions. Remove Kimi endpoint matching from the component; matching is based only on backend `providerTemplate` metadata/kind.

- [ ] **Step 4: Run focused frontend tests and commit**

```bash
rtk bun run test -- tests/unit/hooks/use-llm-catalog.test.tsx tests/unit/pages/settings-page-flow.test.tsx tests/unit/components/llm-catalog-panel.test.tsx
rtk git add frontend/hooks/use-llm-catalog.ts frontend/hooks/use-provider-connection.ts frontend/components/bioinfoflow/settings/llm-catalog-panel.tsx frontend/lib/llm/types.ts frontend/tests/unit
rtk git commit -m "fix: keep provider setup backend driven"
```

### Task 9: Documentation and maintainability checks

**Files:**
- Create: `docs/development/llm-providers.md`
- Modify: `RUNBOOK.md`
- Modify: `docs/plans/2026-07-21-provider-registry-phase-one-design.md`

- [ ] **Step 1: Document registry ownership and snapshot refresh**

Include the twelve provider matrix, manual snapshot update command, review checklist, live smoke commands, and the rule that normal setup never accesses provider networks.

- [ ] **Step 2: Run documentation checks**

```bash
rtk git diff --check
```

- [ ] **Step 3: Commit**

```bash
rtk git add docs/development/llm-providers.md RUNBOOK.md docs/plans/2026-07-21-provider-registry-phase-one-design.md
rtk git commit -m "docs: document llm provider registry"
```

### Task 10: Full verification and PR preparation

**Files:**
- Modify only files required by verification failures caused by this campaign.

- [ ] **Step 1: Run backend verification**

From `backend/`:

```bash
rtk uv run pytest
rtk uv run ruff check .
rtk uv run ruff format --check .
```

Expected: all pass.

- [ ] **Step 2: Run frontend verification**

From `frontend/`:

```bash
rtk bun run lint
rtk bun run lint:i18n
rtk bun run lint:dead-code
rtk bun run test
```

Expected: all pass.

- [ ] **Step 3: Inspect final diff and secrets**

```bash
rtk git diff origin/main...HEAD --check
rtk git status --short
rtk rg -n "sk-kimi-|sk-ant-|Bearer [A-Za-z0-9]" backend frontend docs
```

Expected: no real credential material and only intentional documentation/test placeholders.

- [ ] **Step 4: Rebase onto current main and re-run affected tests**

```bash
rtk git fetch origin --prune
rtk git rebase origin/main
```

Re-run backend and frontend verification after conflict resolution or any changed upstream provider files.

- [ ] **Step 5: Push and open PR**

```bash
rtk git push -u origin codex/provider-registry-phase-one
rtk gh pr create --base main --title "refactor: establish llm provider registry" --body-file /tmp/provider-registry-pr.md
```

The PR body must summarize architecture, the twelve providers, migrations,
verification commands/results, and note that real-key smoke tests remain an
optional maintainer action.
