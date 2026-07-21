# Provider Registry Phase One Design

## Status

Approved direction in conversation on 2026-07-21. This document is the written
design review gate before implementation planning.

## Objective

Replace Bioinfoflow's template-plus-generic-discovery provider setup with a
single backend-owned provider registry and a small set of provider profiles.
Phase one supports API-key configuration for:

- OpenAI
- Anthropic
- OpenRouter
- Fireworks AI
- Qwen
- DeepSeek
- xAI
- Z.AI
- Kimi Code
- MiniMax
- Hugging Face
- Gemini

The existing settings layout remains. Provider-specific behavior belongs in the
backend, not in frontend conditionals.

## Explicit Scope Decisions

- Kimi Open Platform Global and Kimi Open Platform China are removed from new
  setup. Only Kimi Code is supported.
- Kimi Code uses keys from `https://www.kimi.com/code/console` and the endpoint
  `https://api.kimi.com/coding/v1`.
- Qwen defaults to the China DashScope endpoint and permits an advanced base URL
  override for the international endpoint.
- MiniMax phase one supports the international API-key endpoint only. MiniMax
  China and MiniMax OAuth are out of scope.
- OAuth, subscription login, AWS Bedrock, Vertex ADC, Copilot ACP, and external
  process transports are out of scope.
- Saving provider configuration is deterministic and does not access the
  provider network.
- Online discovery is an optional catalog refresh. A failed refresh never
  invalidates a saved connection or removes bundled models.
- A successful provider test means a real minimal runtime request completed. A
  successful `/models` call alone is not readiness.

## Reference Implementations

The design ports behavior rather than importing another agent's runtime.

- Hermes Agent `2da64e78401fffa0bebee2bb498106bd41765f30`
  - `hermes_cli/providers.py`
  - `hermes_cli/provider_catalog.py`
  - `hermes_cli/auth.py`
  - `hermes_cli/models.py`
  - `plugins/model-providers/*/__init__.py`
- OpenCode `849c2598abc7d2b40261e74b5826bc74ffc78308`
  - models.dev-backed built-in catalog
  - authentication stored separately from provider configuration
  - custom providers require an explicit base URL and model list
- JCode `ccf6153ebc32c07b42a37a8c2ccc8a5b310b45d9`
  - configuration, catalog, and runtime validation checkpoints

Official Kimi references:

- `https://www.kimi.com/code/docs/kimi-code/models.html`
- `https://www.kimi.com/code/docs/third-party-tools/opencode.html`
- `https://platform.kimi.com/docs/api/list-models`

## First Principles

1. A credential authenticates an account; it does not define a model catalog.
2. Model listing and model invocation are different capabilities.
3. Configuration must be deterministic and transaction-safe.
4. Provider differences should be explicit data or narrow hooks, not scattered
   endpoint checks.
5. AgentCore must remain provider-neutral.
6. The smallest stable abstraction is a registry of facts plus profiles for
   genuine behavioral differences.

## Rejected Designs

### Copy one Hermes class per provider

This would maximize short-term visual similarity while copying assumptions from
Hermes' transport stack into Bioinfoflow's LiteLLM-backed model runtime. It also
duplicates mostly declarative data across twelve classes.

### Depend on Hermes or models.dev at runtime

This makes provider setup depend on third-party availability and unreviewed
catalog changes. Bioinfoflow instead uses a reviewed build-time snapshot.

### Delegate provider setup to LiteLLM

LiteLLM remains the invocation backend. It is not the product catalog, setup
contract, migration policy, or user-facing error taxonomy.

## Architecture

```text
ProviderRegistry
  |- ProviderSpec (facts)
  |- Bundled model snapshot
  `- ProviderProfile (behavioral hooks)
          |
          +-> LlmCatalogService
          |     |- deterministic setup
          |     |- optional catalog refresh
          |     `- structured provider test
          |
          `-> ModelGateway
                `- invocation adaptation before LiteLLMBackend
```

### ProviderSpec

`ProviderSpec` is immutable registry data:

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
    bundled_models: tuple[ModelSpec, ...]
```

It declares:

- API-key environment aliases
- default and overridable base URLs
- LiteLLM routing prefix
- Bioinfoflow runtime operation: Chat or Responses
- upstream API family: OpenAI-compatible, Anthropic Messages, or Gemini
- bundled models and capabilities
- live catalog strategy

`runtime_operation` and `upstream_api_family` are separate. Anthropic and
Gemini can use Bioinfoflow's Chat codec while LiteLLM translates to their native
upstream protocols.

### ProviderProfile

The default profile handles Bearer-authenticated OpenAI-compatible endpoints.
Special profiles override only required behavior:

```python
class ProviderProfile(Protocol):
    spec: ProviderSpec

    def normalize_connection(self, candidate): ...
    async def fetch_models(self, connection): ...
    def prepare_invocation(self, invocation): ...
    def classify_error(self, error): ...
```

Special profiles exist for:

- Anthropic
- OpenRouter
- DeepSeek
- Z.AI
- Kimi Code
- MiniMax
- Gemini

OpenAI, Fireworks, Qwen, xAI, and Hugging Face use the default profile plus
declarative registry data. xAI declares Responses as its preferred operation
while retaining Chat compatibility.

### Compatibility Facade

`provider_templates.py` stops being the source of truth but remains as a facade
during migration. Existing imports and `GET /provider-templates` derive their
responses from `ProviderRegistry`, keeping frontend API compatibility.

## Provider Matrix

| Provider | Default endpoint | Runtime operation | Catalog | Special behavior |
| --- | --- | --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | Chat and Responses | bundled + `/models` | agent-model filtering |
| Anthropic | `https://api.anthropic.com` | Chat | bundled + native `/v1/models` | `x-api-key`, `anthropic-version` |
| OpenRouter | `https://openrouter.ai/api/v1` | Chat | public live catalog + fallback | aggregator IDs and reasoning translation |
| Fireworks | `https://api.fireworks.ai/inference/v1` | Chat | bundled + `/models` | preserve full `accounts/...` IDs |
| Qwen | `https://dashscope.aliyuncs.com/compatible-mode/v1` | Chat | China snapshot + `/models` | international endpoint override |
| DeepSeek | `https://api.deepseek.com/v1` | Chat | bundled + `/models` | thinking and effort translation |
| xAI | `https://api.x.ai/v1` | Responses preferred, Chat allowed | bundled + `/models` | protocol preference |
| Z.AI | `https://api.z.ai/api/paas/v4` | Chat | bundled + `/models` | GLM thinking and effort translation |
| Kimi Code | `https://api.kimi.com/coding/v1` | Chat | three bundled models + optional `/models` | omit temperature; mutually exclusive thinking/effort |
| MiniMax | `https://api.minimax.io/anthropic` | Chat via LiteLLM | bundled primary | Anthropic route and M3 reasoning behavior |
| Hugging Face | `https://router.huggingface.co/v1` | Chat | bundled + `/models` | organization/model IDs |
| Gemini | `https://generativelanguage.googleapis.com` | Chat via LiteLLM | bundled + native `v1beta/models` | `x-goog-api-key`, thinking config |

## Bundled Model Catalog

### Source

A repository script downloads `https://models.dev/api.json`, selects the twelve
approved provider IDs, applies Bioinfoflow filters and Hermes-derived overlays,
then writes a reviewed JSON snapshot committed to the repository.

Runtime code never downloads models.dev.

### Filters

Bundled models must:

- produce text
- support tool calls
- not be embedding-only
- not be image/video-generation-only
- not be realtime-only

Kimi Code is explicitly pinned to:

- `k3`
- `kimi-for-coding`
- `kimi-for-coding-highspeed`

### Precedence

```text
manual override > successful live observation > bundled snapshot > profile fallback
```

Model metadata records source, source version, and observation time in the
existing `model_metadata` JSON field. No new catalog table is introduced.

## Setup Flow

`POST /provider-setups` becomes a deterministic transaction:

1. Resolve `ProviderSpec`.
2. Validate and normalize local input.
3. Create or update the provider connection.
4. Encrypt and store the credential.
5. Upsert bundled models.
6. Disable bundled models removed by the new reviewed snapshot.
7. Commit and return provider plus models.

It does not perform discovery or a runtime probe. The legacy `discover` field is
accepted but ignored and documented as deprecated.

## Catalog Refresh Flow

`POST /providers/{id}/discover-models`:

1. Resolves the provider profile.
2. Builds the provider-specific catalog request.
3. Uses the stored credential when required.
4. Filters results to agent-capable models.
5. Merges only after a complete successful response.

Failure leaves all persisted models unchanged. Only a successful authoritative
refresh may mark previously live-observed models stale. Bundled and manual
models are never marked stale merely because live discovery omitted them.

## Provider Test Flow

`POST /providers/{id}/test` retains current top-level response fields and adds:

```json
{
  "failed_at": "configuration | catalog | runtime | null",
  "checks": [
    {"name": "configuration", "status": "passed"},
    {"name": "catalog", "status": "passed | failed | skipped"},
    {"name": "runtime", "status": "passed | failed | not_run"}
  ]
}
```

Catalog validation is skipped when the provider does not expose an appropriate
low-cost catalog endpoint. Overall `success` is true only after the real minimal
runtime probe succeeds.

## Runtime Adaptation

AgentCore remains provider-neutral. The model runtime contract replaces the
boolean reasoning flag with normalized semantics:

```python
@dataclass(frozen=True)
class ReasoningRequest:
    enabled: bool
    effort: Literal["low", "medium", "high", "max"] | None
```

`ModelGateway` asks the profile to produce provider invocation options before
calling `LiteLLMBackend`.

Provider-specific dictionaries do not enter AgentCore transcripts or public
events.

Hermes-derived behavior to port:

- OpenRouter reasoning and modern Anthropic-model handling
- DeepSeek V4/R1 thinking controls
- Z.AI GLM 4.5+ thinking and GLM 5.2 effort mapping
- Kimi Code temperature omission and thinking/effort exclusivity
- MiniMax M3 reasoning split behavior where applicable
- Gemini thinking-config translation

## Error Taxonomy

Provider errors normalize to:

- `CREDENTIAL_REJECTED`
- `CREDENTIAL_ENDPOINT_MISMATCH`
- `ENDPOINT_UNREACHABLE`
- `CATALOG_UNAVAILABLE`
- `MODEL_NOT_FOUND`
- `MODEL_ACCESS_DENIED`
- `PROTOCOL_UNSUPPORTED`
- `RATE_LIMITED`
- `QUOTA_EXHAUSTED`
- `PROVIDER_UNAVAILABLE`

Safe public details may include HTTP status, provider code, retryability,
request ID, and a provider-specific remediation hint. They never include API
keys, authorization headers, raw request bodies, or opaque provider payloads.

## Frontend Compatibility

The settings layout and provider cards remain.

Required behavior changes are deliberately small:

- remove the save-then-discover orchestration
- use models returned by deterministic setup
- display backend error text instead of replacing it with a generic discovery
  failure message
- preserve the existing explicit Test control

Frontend code does not contain provider endpoint or protocol branches.

## Migration

### Provider IDs

Canonical phase-one kinds are:

```text
openai, anthropic, openrouter, fireworks, qwen, deepseek,
xai, zai, kimi_code, minimax, huggingface, gemini
```

Existing `grok` rows migrate to `xai`.

Existing Kimi rows:

- canonical Kimi Code endpoints migrate to `kimi_code`
- `api.moonshot.cn` and `api.moonshot.ai` rows are disabled
- their credentials are preserved but never reused for Kimi Code
- configuration responses identify them as unsupported legacy connections so
  users can remove them explicitly

### Out-of-scope existing providers

Existing configured providers outside the twelve-provider phase-one registry
remain readable and runnable through a legacy compatibility adapter, avoiding a
destructive upgrade. They are not offered for new setup from the primary
registry. A later cleanup can remove the compatibility path after a deprecation
period.

`openai-compatible`, Ollama, and vLLM remain available through this legacy path
because they are extension mechanisms rather than branded phase-one providers.

## Security And Network Policy

- Existing credential encryption remains authoritative.
- Provider base URLs continue through the current SSRF/network policy.
- Provider profiles cannot bypass public-only restrictions.
- HTTP endpoints still require explicit insecure transport opt-in.
- Catalog and runtime error logging redacts credential-bearing headers.
- Snapshot generation is a developer command and never runs in production.

## Verification Strategy

### Registry and catalog

- exactly twelve primary provider specs
- unique IDs and kinds
- valid HTTPS defaults
- expected environment aliases
- snapshot schema validation
- only agent-capable models included
- Kimi Code contains exactly the three approved models

### Setup

- setup succeeds without network access
- setup writes bundled models
- invalid local configuration rolls back
- replacement preserves the old connection when the transaction fails
- deprecated `discover=true` does not cause network access

### Discovery

- provider-specific auth headers and paths
- failed discovery leaves the database unchanged
- successful discovery merges live metadata
- bundled/manual models survive live omission
- credential and provider errors are safely classified

### Runtime profiles

- table-driven routing tests for all twelve providers
- focused tests for OpenRouter, DeepSeek, Z.AI, Kimi Code, MiniMax, and Gemini
- no provider-specific imports in AgentCore
- no credential data in representations, events, or errors

### Frontend

- saving a provider does not call `discover-models`
- setup-returned models populate the test selector
- exact backend errors remain visible
- existing provider-card layout and accessibility tests remain valid

### Broad verification

- backend: `uv run pytest` and `uv run ruff check .`
- frontend: `bun run lint`, `bun run lint:i18n`, `bun run lint:dead-code`, and
  `bun run test`

Live provider credentials are not available in CI. Provider wire behavior is
verified with recorded contract fixtures and mock HTTP servers. Optional manual
smoke commands are documented for maintainers with real keys.

## Console Findings From The Original Report

- Vercel Analytics is currently rendered unconditionally in self-hosted builds,
  producing `/_vercel/insights/script.js` 404. The implementation will gate it
  behind an explicit deployment setting or Vercel environment detection.
- The React hydration error appeared alongside extension-owned
  `contentScript.js`, `ObjectMultiplex`, and EventEmitter warnings. Browser
  verification will compare a clean profile/extensions-disabled run before any
  application hydration change is made.
- Extension-owned warnings are not suppressed by Bioinfoflow code.

## Delivery

Implementation will use test-first changes and may be split into coherent
commits within one feature branch. Before opening the PR, the branch will be
rebased onto the latest `origin/main`, the full relevant verification matrix
will run, and the PR title will use Conventional Commits.
