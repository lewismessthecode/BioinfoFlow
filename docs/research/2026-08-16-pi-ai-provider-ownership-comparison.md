# pi-ai Provider Ownership Compared With BioinfoFlow

## Scope

This note compares BioinfoFlow's current multi-provider boundary with the
`@earendil-works/pi-ai` implementation at commit
[`086c32e74530564922d011ade23ff582c9d63116`](https://github.com/earendil-works/pi/tree/086c32e74530564922d011ade23ff582c9d63116/packages/ai).
It is an architectural comparison, not a proposal to import the TypeScript
package into the Python backend.

## pi-ai's ownership model

pi-ai treats a provider as the concrete runtime unit. The provider owns its
identity, authentication, model list, optional refresh behavior, and streaming
entrypoints. The top-level `Models` collection resolves auth and delegates to
the provider that owns the selected model; it does not reconstruct provider
behavior itself. See [`Provider` and `Models`](https://github.com/earendil-works/pi/blob/086c32e74530564922d011ade23ff582c9d63116/packages/ai/src/models.ts#L88-L155).

Provider and API are separate dimensions. Every model explicitly carries its
provider, API implementation, exact base URL, capabilities, and compatibility
metadata. See [`Model`](https://github.com/earendil-works/pi/blob/086c32e74530564922d011ade23ff582c9d63116/packages/ai/src/types.ts#L793-L823).
`createProvider()` accepts one API implementation or a map keyed by
`model.api`, then dispatches without inferring the API from a model-name prefix.
See [`createProvider()`](https://github.com/earendil-works/pi/blob/086c32e74530564922d011ade23ff582c9d63116/packages/ai/src/models.ts#L739-L832).

Built-in providers therefore declare exact composition locally:

- DeepSeek owns its endpoint, env-key aliases, catalog, and
  `openai-completions` adapter in
  [`deepseek.ts`](https://github.com/earendil-works/pi/blob/086c32e74530564922d011ade23ff582c9d63116/packages/ai/src/providers/deepseek.ts#L1-L15).
- Z.AI declares its non-`/v1` coding endpoint in
  [`zai.ts`](https://github.com/earendil-works/pi/blob/086c32e74530564922d011ade23ff582c9d63116/packages/ai/src/providers/zai.ts#L1-L15).
- Kimi For Coding deliberately uses the Anthropic Messages implementation and
  owns both API-key and OAuth auth in
  [`kimi-coding.ts`](https://github.com/earendil-works/pi/blob/086c32e74530564922d011ade23ff582c9d63116/packages/ai/src/providers/kimi-coding.ts#L1-L24).

The README states the same public contract: providers own authentication,
provider factories import their own catalog and API wrapper, model refresh is
an explicit operation, and provider-wide endpoint transformations belong in
the provider's API implementation. See
[`Providers and Models`](https://github.com/earendil-works/pi/blob/086c32e74530564922d011ade23ff582c9d63116/packages/ai/README.md#L236-L326)
and
[`Custom Providers`](https://github.com/earendil-works/pi/blob/086c32e74530564922d011ade23ff582c9d63116/packages/ai/README.md#L996-L1080).

## Why BioinfoFlow drifts

BioinfoFlow currently has overlapping representations of the same provider:

1. persisted `LlmProvider.kind`, `base_url`, `wire_protocol`, and JSON metadata;
2. immutable `ProviderSpec` registry facts;
3. generated and legacy `ProviderTemplate` compatibility objects;
4. `ProviderProfile` request/catalog hooks;
5. model-name prefixes and defaults inside LiteLLM.

The intended registry exists, but setup still resolves through
`ProviderTemplate`, profiles do not own complete connection normalization, and
runtime still supplies a LiteLLM-routed model name plus an optional base URL.
Consequently setup, discovery, test, and agent invocation can derive different
effective targets for the same database row.

The reported DeepSeek row demonstrates the failure. Migration `0031` seeded
provider `10000000-0000-4000-8000-000000000005` with `base_url=None`, while the
new registry declares `https://api.deepseek.com/v1`. Before the reviewed change,
that registry endpoint never reached runtime, so LiteLLM selected its own
DeepSeek default. This is a migration and ownership gap, not a DeepSeek-only
HTTP quirk.

The reviewed global normalization then demonstrates the opposite failure:
assuming that every OpenAI-compatible endpoint must end in `/v1` changes Z.AI's
exact `/api/paas/v4` endpoint. OpenAI compatibility describes a request/response
dialect; it does not standardize provider URL paths, auth products, model IDs,
or reasoning controls.

## Plain-language conclusion

The implementation is difficult because one provider participates in several
independent flows: save configuration, resolve credentials, list models, test a
model, run an agent request, resume a request, and classify errors. If each flow
rebuilds the target from partly different facts, adding providers creates a
provider-by-flow matrix of failure modes.

pi-ai reduces that matrix by resolving one owned runtime object first. The
equivalent BioinfoFlow invariant should be:

> Before any provider I/O, resolve exactly one immutable target containing the
> provider, upstream API implementation, exact endpoint, credential, upstream
> model ID, and compatibility options. Setup, discovery, test, and runtime must
> consume that same ownership model and must not ask LiteLLM to fill missing
> product facts.

BioinfoFlow has extra difficulty that pi-ai does not solve for it: persistent
multi-tenant connections, encrypted credentials, SSRF policy, legacy database
migrations, and server-side catalog state. Those concerns justify a database
and service layer, but they do not justify multiple competing provider truths.
