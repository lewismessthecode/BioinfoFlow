# Relay Runtime, Model Discovery, and Selector Design

Date: 2026-07-14

## Goal

Keep LiteLLM as Bioinfoflow's provider-neutral network execution layer while
making OpenAI-compatible Responses endpoints, including Codex-oriented models,
reliable and diagnosable. Fix the provider setup and selector regressions
without adding relay-specific hostnames, model names, or protocol guesses.

## Root Causes

1. Provider save currently sends `discover: false` even when Model ID is blank.
   The provider is saved with no models, so it cannot appear in the selector.
2. The selector groups and persists providers by `provider.kind`. Two endpoints
   of the same kind collide, and a stale vLLM model can remain selected even
   after a new OpenAI-compatible endpoint is configured.
3. The `public_only` LiteLLM transport is injected through `client=` for every
   protocol. LiteLLM Chat Completions interprets that argument as an
   `openai.AsyncOpenAI` client and accesses `.api_key`; Bioinfoflow supplies an
   HTTP handler instead, causing an internal error before the request is sent.
   Responses accepts the HTTP handler through `client=`, so transport injection
   must be protocol-specific.
4. Discovered model metadata currently assumes streaming and tool support.
   `/models` proves only that a model ID exists, not that a relay supports a
   particular protocol or streaming behavior.
5. Agent requests have no explicit turn-level model deadline. The restricted
   LiteLLM HTTP transport may wait up to 600 seconds, while the provider probe is
   bounded to 15 seconds and uses a non-streaming request.
6. `ModelError` already carries safe structured metadata, but the turn result
   collapses it to `model_request_failed` plus a generic string. This makes the
   UI and logs unable to distinguish authentication, timeout, unavailable, or
   invalid-request failures.

## Runtime Modes

The canonical AgentCore loop remains provider-neutral. A model target selects a
wire protocol (`chat_completions` or `responses`) and a provider adapter derives
the LiteLLM routed model name. LiteLLM performs one network attempt; Bioinfoflow
owns retry, semantic fallback, deadlines, events, and durable state.

Responses remains the Codex-oriented adapter path. It uses typed Responses SSE
events and preserves commentary/final-answer phases. It must not silently route
to Chat Completions because that changes protocol semantics and may target an
unsupported relay endpoint.

## Turn Loop

- Inject the restricted transport according to LiteLLM's protocol contract:
  Chat Completions receives the policy session through `shared_session=`, while
  Responses receives the policy HTTP handler through `client=`.
- Add a configurable model-attempt timeout around the complete gateway
  consumption, covering connection, first event, and stream completion.
- Timeout produces a structured, replay-safe `ModelError(category="timeout")`
  before semantic output. Existing retry policy may retry it.
- A failure after semantic output remains non-replay-safe.
- Retry events expose safe category/status metadata, never raw provider bodies
  or credentials.
- Terminal turn events preserve the existing stable `model_request_failed`
  error code for API compatibility while adding safe diagnostic metadata and a
  category-specific public message.
- Streaming-to-non-streaming fallback is not automatic in this change. It can
  hide protocol defects and duplicate expensive requests. A provider/model may
  explicitly disable streaming through stored capability configuration or a
  successful capability probe in a later enhancement.

## Tool Model

No tool registry or tool-call contract changes are required. Chat and Responses
codecs continue deriving provider-specific request copies from the same
canonical transcript and tool definitions.

## Context and Memory Model

No transcript migration is required. Provider identity changes affect only UI
selection and request metadata. Responses continuation remains bound to the
endpoint UUID, provider kind, model name, protocol, base URL, and target
revision.

## Provider Configuration and Discovery

Saving and discovery are separate operations:

1. Save provider, credential, protocol, endpoint, and any explicit Model IDs
   with `discover: false`.
2. If the Model ID field is blank and the template discovery mode is not
   `static`, call the existing discovery endpoint after save succeeds.
3. Discovery success refreshes the catalog and reports the model count.
4. Discovery returning no models reports a non-fatal warning.
5. Discovery failure reports "saved, discovery failed", keeps the provider and
   any existing models, and offers the existing refresh action.

An explicit Model ID is authoritative and skips automatic discovery. This keeps
manual setup usable for relays that do not expose `/models`.

## Provider Identity and Selector

- `provider_id` is the stable group, selection, React key, and local-storage
  identity.
- `provider_kind` remains separate and is used only for routing semantics,
  icons, and capability policy.
- Provider display name is always the group heading.
- Legacy local-storage selections keyed by kind are migrated only when they
  match exactly one configured provider and model. Ambiguous selections fall
  back to the first valid catalog model.
- The model UUID remains the authoritative backend selection, preventing two
  providers exposing the same model slug from colliding.
- Composer chips use a readable line height and sufficient minimum height so
  descenders are not clipped.

## Extension Model

Provider adapters continue owning:

- supported wire protocols;
- default protocol;
- LiteLLM model routing prefix;
- endpoint normalization;
- discovery strategy;
- protocol-specific transport injection requirements.

No relay address or GPT model slug is hardcoded. Future equivalent-deployment
load balancing may use LiteLLM Router behind the same backend boundary, while
cross-model fallback remains AgentCore-owned.

## Safety and Observability

- Preserve credential and provider-body redaction.
- Propagate only safe error category, HTTP status, provider code, request ID,
  retryability, and retry delay.
- Log the endpoint UUID, provider kind, protocol, model slug, attempt number,
  elapsed time, and safe error metadata.
- The UI renders retry progress and the terminal category-specific public error
  instead of remaining indefinitely at "processing".

## Compatibility

- Existing setup clients may continue sending `discover` explicitly.
- Existing turn APIs retain `model_request_failed` as the stable terminal code.
- Existing model UUID selections continue to resolve without migration.
- Legacy kind-based local storage is read and migrated best-effort.
- Chat Completions providers and manually configured models retain their
  current behavior.

## Verification

### Provider setup

- Blank Model ID on a discoverable template saves first, then discovers.
- Explicit Model ID does not discover.
- Static templates do not discover.
- Discovery failure leaves the saved provider and existing models intact.
- Base URLs with and without `/v1` both request exactly `/v1/models`.

### Runtime

- A `public_only` Chat request uses `shared_session`, reaches the HTTP endpoint,
  and never treats the HTTP handler as an OpenAI SDK client.
- A `public_only` Responses request retains its supported `client=` transport.
- Responses uses `/v1/responses`; Chat uses `/v1/chat/completions`.
- Model attempt timeout is bounded and retryable before semantic output.
- Timeout/failure after semantic output is not replay-safe.
- Safe error metadata reaches retry and terminal events without leaking secrets.
- Existing Chat and Responses codec, retry, fallback, continuation, and live
  relay tests remain green.

### Frontend

- Two providers of the same kind render as distinct groups with their names.
- Selecting identical model slugs from different providers persists the correct
  model UUID and endpoint UUID.
- Legacy selection migration is deterministic.
- Composer model chip text is not vertically clipped.
- Empty-model save shows discovery success, empty-result warning, or non-fatal
  failure state as appropriate.

