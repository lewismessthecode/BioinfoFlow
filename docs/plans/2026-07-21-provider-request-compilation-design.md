# Provider Request Compilation Design

## Status

Approved on 2026-07-21 as the follow-up to the phase-one provider registry.
This design changes backend request compilation only. The existing settings UI
and the separation between saving credentials, discovering models, and running
a real model request remain unchanged.

## Problem

AgentCore expresses one provider-neutral intent:

- use this model;
- allow reasoning at an optional effort level;
- expose these tools;
- limit the output to this many tokens.

Those concepts do not have one universal wire representation. Depending on the
provider, model family, and transport, reasoning may be represented by
`reasoning_effort`, `reasoning`, `thinking`, `extra_body.thinking`,
`thinkingConfig`, `chat_template_kwargs.enable_thinking`, or no request field at
all. Token-limit and tool-schema rules also differ.

The current gateway encodes a nominal OpenAI-compatible request and then merges
a flat dictionary returned by `ProviderProfile.invocation_options()`. That is
too weak: it cannot rename or remove codec fields, normalize messages or tools,
or distinguish a LiteLLM option from a provider request-body field.

The concrete Kimi failure demonstrates the boundary defect. The request used
the correct key, endpoint, and model, but the Kimi profile inherited a top-level
`thinking` option from DeepSeek. LiteLLM 1.83 rejects that option locally for an
`openai/` model with `UnsupportedParamsError(status=400)` before any HTTP
request reaches Kimi. The same local compatibility check exposes equivalent
failures for the current Z.AI, Qwen, and Hugging Face reasoning options.

## First-principles model

There are four distinct layers:

1. **Product intent**: AgentCore requests reasoning, an effort preference,
   tools, and an output limit.
2. **Model capability**: the selected model may support fixed reasoning,
   optional reasoning, effort tiers, or no reasoning control.
3. **Provider protocol**: the provider defines the actual request fields and
   continuation requirements.
4. **Transport library**: LiteLLM accepts a particular Python call shape and
   may map it again before sending HTTP.

Collapsing these layers into a flat dictionary makes correctness accidental.
The platform must preserve the first layer and compile it through the other
three.

## Reference implementations

The design was checked against these source snapshots:

- Hermes Agent, commit `f4df260f26c93f15694698869f3ea8e965eea301`.
  `providers/base.py` keeps catalog health separate from provider configuration
  and gives profiles request-level hooks. Provider plugins such as Kimi,
  DeepSeek, OpenRouter, and MiniMax split extra-body fields from top-level SDK
  options and apply model-specific behavior.
- OpenCode, commit `849c2598abc7d2b40261e74b5826bc74ffc78308`.
  `packages/opencode/src/provider/transform.ts` treats reasoning as
  model-and-transport-specific variants. It normalizes messages and tools before
  dispatch instead of assuming every OpenAI-compatible endpoint has identical
  semantics.
- JCode, commit `b81ac37d48be6fba2d2a59520249d5d50db376c8`.
  Its registry represents reasoning capability separately from provider
  credentials and supports effort, toggle, and token-budget metadata. Its
  runtime has one mapping boundary from provider configuration to model request.
- Kimi Code, commit `e45832398d0d9cad98dbad1cbf1e5b103a20aace`.
  `kimi.contrib.ts` defines Kimi as a vendor trait over an OpenAI transport. It
  converts `max_tokens` to `max_completion_tokens`, places thinking under
  `extra_body` for the SDK and expands it into the outgoing body, normalizes
  tool schemas, removes empty assistant content beside tool calls, and decodes
  `reasoning_content`.

We borrow their boundaries, not their entire abstraction systems. BioinfoFlow
has twelve first-party API-key providers, so a compact profile compiler is
enough; a generic provider DSL would add more concepts than the current scope
needs.

## Official protocol evidence

The compiler behavior is based on provider documentation, with LiteLLM mapping
tests used to verify the Python call shape actually accepted by version 1.83:

- OpenAI reasoning guide: <https://developers.openai.com/api/docs/guides/reasoning>
- Anthropic extended thinking: <https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking>
- OpenRouter reasoning tokens: <https://openrouter.ai/docs/guides/best-practices/reasoning-tokens>
- Fireworks text generation: <https://docs.fireworks.ai/guides/querying-text-models>
- Qwen API and thinking controls: <https://www.alibabacloud.com/help/en/model-studio/use-qwen-by-calling-api>
- DeepSeek thinking mode: <https://api-docs.deepseek.com/guides/thinking_mode>
- xAI reasoning: <https://docs.x.ai/docs/guides/reasoning>
- Z.AI API documentation: <https://docs.z.ai/>
- Kimi Code models: <https://www.kimi.com/code/docs/en/kimi-code/models.html>
- MiniMax API documentation: <https://platform.minimax.io/docs/api-reference>
- Hugging Face Inference Providers chat completion:
  <https://huggingface.co/docs/inference-providers/tasks/chat-completion>
- Gemini thinking: <https://ai.google.dev/gemini-api/docs/thinking>

Important conclusions:

- DeepSeek documents `thinking` as an OpenAI `extra_body` field and
  `reasoning_effort` as a separate effort control.
- Kimi Code's `kimi-for-coding` models are thinking-on models; K3 exposes
  effort control. Disabling reasoning is not a safe generic fallback.
- xAI reasoning models may not allow reasoning to be disabled.
- Gemini generations use model-specific thinking levels or budgets; LiteLLM
  already maps its normalized reasoning effort into `thinkingConfig`.
- OpenRouter has a stable aggregator-level `reasoning` object and performs the
  downstream provider translation.
- Anthropic thinking affects output-token budgeting and continuation history;
  LiteLLM maps normalized effort for the native Anthropic transport.
- Qwen-compatible endpoints commonly use `enable_thinking` and optional
  thinking budgets rather than OpenAI's native model-family validation.

## Selected architecture

### Canonical input remains provider-neutral

`ModelInvocation` and `ReasoningRequest` remain the only product-facing input:

```python
ReasoningRequest(enabled=True, effort="medium")
```

AgentCore must never emit `thinking`, `reasoning_effort`, `extra_body`, or other
provider fields.

### Codec creates the protocol baseline

The chat-completions codec continues to translate canonical conversation and
tool objects into the ordinary OpenAI chat-completions shape. It does not know
which vendor will receive the request.

### Profile compiles the complete request

Replace the flat option merge with a request compiler hook:

```python
def compile_request(
    self,
    request: dict[str, Any],
    *,
    model_name: str,
    wire_protocol: WireProtocol,
    reasoning: ReasoningRequest,
) -> dict[str, Any]:
    ...
```

The gateway calls the hook after codec encoding and before credentials and
network policy are attached. The profile receives and returns an owned request
dictionary, so it may add, replace, or remove provider-facing fields without
mutating the canonical invocation.

The default implementation adds `reasoning_effort` only when reasoning is
enabled. Specialized profiles override only the transformations they need.

### Profile behavior is model-aware

The normalized effort is a preference, not a promise that every model accepts
that literal value. A profile may:

- pass a supported effort through;
- map it to the nearest supported tier;
- omit effort while leaving mandatory/fixed reasoning enabled;
- encode an explicit enable/disable toggle when the provider supports one.

It must not claim that mandatory reasoning was disabled when the provider does
not support disabling it.

### LiteLLM remains the transport

Profiles compile the Python call shape accepted by the pinned LiteLLM version;
LiteLLM remains responsible for clients, streaming, provider response parsing,
and normalized transport errors. Provider profiles must not perform network
requests or instantiate SDK clients.

## Phase-one provider matrix

| Provider | Compiler behavior |
| --- | --- |
| OpenAI | Use LiteLLM's supported `reasoning_effort` mapping for reasoning-capable models. |
| Anthropic | Keep normalized effort; LiteLLM maps it to native thinking and adjusts token budgeting. |
| OpenRouter | Send the aggregator-level `reasoning: {effort: ...}` object. |
| Fireworks | Use its LiteLLM-supported `reasoning_effort` path. |
| Qwen | Put compatible thinking controls in `extra_body`; never pass an OpenAI model-family validation field directly to LiteLLM. |
| DeepSeek | Put `thinking` in `extra_body`; send supported effort separately when applicable. |
| xAI | Use `reasoning_effort`; omit false disable controls for mandatory-reasoning models. |
| Z.AI | Compile model-aware effort/toggle controls through fields LiteLLM accepts; do not inherit DeepSeek blindly. |
| Kimi Code | Put thinking in `extra_body`, rename `max_tokens`, normalize tool schemas, and remove empty assistant content beside tool calls. |
| MiniMax | Put `reasoning_split` and model-appropriate thinking controls in `extra_body`. |
| Hugging Face | Use `extra_body` for pass-through reasoning controls only when the selected model exposes them; otherwise rely on model defaults. |
| Gemini | Keep normalized effort and let LiteLLM map it to native `thinkingConfig`. |

## Invariants

1. AgentCore contains no provider request fields.
2. A compiled request contains at most one enable/disable representation and
   one effort representation accepted by that transport.
3. Provider profiles do not change credential persistence, catalog discovery,
   or runtime verification state.
4. Compilation is pure and deterministic: no network I/O and no mutation of the
   caller's request.
5. Unknown models prefer omission and provider defaults over sending an
   unverified control that can make an otherwise valid request fail.
6. Token-limit conversion preserves the canonical output limit exactly unless
   an official provider limit requires clamping.
7. Tool normalization preserves names, descriptions, required fields, and
   semantic constraints.

## Error handling

Local LiteLLM compatibility failures and remote provider validation failures
continue to become normalized `ModelError` values. The compiler prevents known
invalid combinations before dispatch. It does not hide provider errors or
retry non-retryable 400 responses.

Provider error details that are safe identifiers remain available through the
existing normalized metadata. Secret-bearing request bodies and API keys are
never logged.

## Verification

Tests must cover three boundaries:

1. profile unit tests for provider/model-specific compilation;
2. gateway tests proving codec output is transformed before backend dispatch;
3. LiteLLM mapping tests proving each generated call shape is accepted by the
   pinned LiteLLM version without network access.

Kimi receives additional regression coverage for:

- no top-level `thinking`;
- `extra_body.thinking` present;
- `max_completion_tokens` replaces `max_tokens`;
- no conflicting reasoning controls;
- Kimi-compatible tool schemas;
- assistant tool-call messages omit empty `content`.

The full backend suite and Ruff checks remain the release gate. A final manual
Kimi request through AgentCore is desirable when a credential is available,
but automated request-compilation tests must not depend on external secrets.

## Non-goals

- redesigning the frontend provider cards;
- making model discovery a save-time requirement;
- introducing a universal declarative provider DSL;
- exposing new reasoning controls in the UI;
- storing provider-specific request fields in AgentCore sessions;
- guaranteeing every arbitrary Hugging Face model supports the same reasoning
  controls.
