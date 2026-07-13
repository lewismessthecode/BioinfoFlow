# LiteLLM Model Runtime Design

## Status

Approved direction for implementation on 2026-07-13.

## Problem

Bioinfoflow has a durable AgentCore loop, scoped model catalog, tool executor,
approvals, retries, fallbacks, event ledger, and transcript store. The model I/O
seam is still coupled to LiteLLM Chat Completions: `AgentLoopController` builds
`messages`, calls `acompletion()`, and parses `choices[].message` and Chat stream
deltas itself.

That coupling caused a real failure with the configured CCH relay. The same
credential and `gpt-5.4-mini` model return `503 no_available_providers` through
`/chat/completions`, while LiteLLM `aresponses()` against `/responses` completes
successfully. The relay documentation explicitly requires the Responses wire
API for Codex.

## Decision

Retain LiteLLM as the multi-provider execution backend. Introduce a
protocol-neutral Bioinfoflow model runtime between AgentCore and LiteLLM.

```text
AgentLoop
  -> ModelGateway
       -> LiteLLMBackend
            -> ChatCompletionsCodec -> litellm.acompletion
            -> ResponsesCodec       -> litellm.aresponses
```

AgentCore owns durable orchestration and semantic model fallback. LiteLLM owns
provider translation and low-level model invocation. Codecs own wire-format
encoding and decoding.

## Invariants

- `agent_core/core/loop.py` must not import LiteLLM or parse provider response
  shapes.
- The durable transcript is canonical Bioinfoflow state, not an OpenAI or
  LiteLLM request payload.
- Provider records are configured endpoint connections. `kind` selects the
  LiteLLM provider family; `wire_protocol` selects the invocation API.
- Wire protocol is explicit persisted configuration. It is never inferred from
  a domain, IP address, or model name.
- Existing provider rows default to `chat_completions`; upgrades do not change
  working request semantics.
- Credentials never appear in model events, transcript items, test status,
  logs, exception messages returned to users, or dataclass representations.
- LiteLLM retries are disabled for direct gateway calls. Bioinfoflow owns the
  current retry budget and semantic fallback until a later deployment-router
  phase explicitly assigns same-model deployment routing to LiteLLM Router.
- Commentary is user-visible progress, not hidden reasoning and not a final
  answer. Only `final_answer` text can complete a Responses turn.
- Tool call IDs survive persistence, approval pauses, process restart, and
  resume.

## Domain Model

### Configured endpoint

The existing `LlmProvider` public name, database table, and API paths remain for
compatibility. Its semantic meaning is documented as a configured endpoint:

```text
endpoint = provider family + base URL + credential + wire protocol + scope
```

Add a first-class field:

```python
class LlmWireProtocol:
    CHAT_COMPLETIONS = "chat_completions"
    RESPONSES = "responses"
```

`OpenAI` and `OpenAI Compatible` templates support both protocols and retain
Chat as their compatibility default. Other initial templates expose Chat only.
Environment-managed endpoints may set `OPENAI_WIRE_PROTOCOL` or
`OPENAI_COMPATIBLE_WIRE_PROTOCOL`; missing values default to Chat and invalid
values fail validation without guessing.

This campaign preserves the existing one-configured-connection-per-template
and scope behavior. A user may switch that connection between Chat and
Responses, but multiple simultaneous connections for one template/scope remain
a follow-up catalog feature.

### Effective capabilities

Capabilities are resolved from the protocol, stored model metadata, and runtime
policy:

```text
effective = protocol capabilities ∩ model capabilities ∩ run policy
```

The connectivity probe is not capability certification. Untested providers
remain usable when configuration and credentials are available. The first
implementation keeps the existing capability booleans but moves protocol
validation into the model runtime. Rich capability-specific probes can be added
later without changing the gateway contract.

## Runtime Contracts

The initial concrete contracts are:

```python
Phase = Literal["commentary", "final_answer"]
WireProtocol = Literal["chat_completions", "responses"]

@dataclass(frozen=True)
class TextPart:
    text: str
    phase: Phase | None = None

@dataclass(frozen=True)
class ToolCallPart:
    call_id: str
    name: str
    arguments: dict[str, Any]

@dataclass(frozen=True)
class ToolResultPart:
    call_id: str
    output: str
    is_error: bool = False

@dataclass(frozen=True)
class ModelTarget:
    endpoint_id: str
    provider_kind: str
    model_name: str
    wire_protocol: WireProtocol
    base_url: str | None
    api_key: str | None = field(default=None, repr=False)

@dataclass(frozen=True)
class ModelInvocation:
    target: ModelTarget
    instructions: str
    input_items: tuple[TextPart | ToolCallPart | ToolResultPart, ...]
    tools: tuple[ToolDefinition, ...]
    stream: bool
    max_output_tokens: int
    allow_reasoning: bool = False
    continuation: ResponsesContinuation | None = None

@dataclass(frozen=True)
class ResponsesContinuation:
    response_id: str | None
    output_items: tuple[dict[str, Any], ...]

@dataclass(frozen=True)
class TextDelta:
    text: str
    phase: Phase = "final_answer"

@dataclass(frozen=True)
class ToolCallDelta:
    index: int
    call_id: str | None
    name: str | None
    arguments_delta: str
```

`ModelInvocation` contains only typed model semantics:

- endpoint target and model name
- stable instructions
- canonical input items
- canonical tool definitions
- generation settings
- optional continuation state
- tracing metadata

Canonical input parts initially cover:

- text with optional `commentary` or `final_answer` phase
- tool call with canonical arguments
- tool result with call ID and error flag

`ModelEvent` is a tagged union consumed by AgentCore:

- text delta with phase
- reasoning delta
- tool call delta
- usage report
- warning
- completion metadata including response ID

An absent Chat phase deterministically maps to `final_answer`. Responses phase
is preserved. A turn completes only when final-answer text exists and no tool
calls are pending.

`ModelError` normalizes LiteLLM failures into category, HTTP status, provider
code, retryability, replay safety, retry-after, request ID, and a safe public
message. Raw exceptions remain internal causes only.

## Backend And Codecs

### LiteLLMBackend

The backend dispatches a typed operation to `acompletion()` or `aresponses()`,
passes endpoint transport settings, disables hidden retries, and normalizes
exceptions. It does not build messages, parse output, write ledger events, or
select fallback models.

### ChatCompletionsCodec

The Chat codec preserves current behavior:

- system/user/assistant/tool message order
- LiteLLM provider-prefixed model names
- Chat function tool schema
- text, reasoning, tool arguments, usage, streaming, and non-streaming decoding

It provides the behavior-preserving seam used to migrate AgentCore away from
direct `acompletion()` calls.

### ResponsesCodec

The Responses codec maps canonical input to Responses items and handles:

- instructions and input items
- function tools, calls, and `function_call_output`
- streaming text and function argument deltas
- `commentary` and `final_answer` phases
- usage and response IDs
- unknown/refusal items as explicit warnings instead of silent loss

Responses continuation state is provider-derived state, not canonical
transcript identity. This campaign uses `store=false` and requests
`include=["reasoning.encrypted_content"]`. The Responses codec assembles the
complete provider output items required for continuation—including encrypted
reasoning, message, and function-call items—and binds them to the exact endpoint,
provider kind, model, protocol, and base URL that produced them. The next request
replays those items plus the matching `function_call_output` only when that target
identity still matches. This state survives approval pauses and process restart
without exposing raw reasoning or depending on provider-side storage.

Continuation metadata is stored as one replaceable, turn-scoped anchor in the
durable transcript metadata used by AgentCore resume. Tool-result messages do not
copy it, a target change discards it, and a final answer clears it. It is treated
as opaque provider state: public transcript/API serializers omit it, logs and
ledger events may report only its presence and item count, and compaction must
preserve the latest live continuation chain until the turn finishes. It follows
the session/transcript retention and deletion lifecycle; completing, deleting,
or expiring the owning session removes the need to replay it. The encrypted
reasoning payload is never decrypted or rendered by Bioinfoflow.

## AgentCore Integration

`AgentCoreRuntime` continues resolving scoped provider/model/profile records and
semantic fallback candidates. It converts database records into a typed model
target rather than a dictionary containing arbitrary request kwargs.

`AgentLoopController` continues owning:

- iteration budget and lease renewal
- interrupt/cancel handling
- event ledger
- tool exposure and execution
- approval pause/resume
- no-progress detection
- final turn status

It calls one `ModelGateway` interface and aggregates canonical events. It does
not know which LiteLLM API or provider response shape produced them.

## Transcript Compatibility

New transcript writes use canonical tool call objects. Readers accept both the
legacy Chat-shaped `{function: {name, arguments}}` representation and the new
canonical shape, so existing databases do not require destructive message
rewrites.

Assistant text metadata preserves phase. Commentary may be persisted and
rendered as progress, but `turn.final_text` is derived only from final-answer
content.

Existing character-count compaction remains compatible during this campaign.
Native Responses compaction is a follow-up capability. Encrypted reasoning
replay is part of this campaign because stateless Responses continuation must
survive approval pauses and process restart.

## Provider Probe

Replace `contract_only` provider tests with a real probe that reuses the
production gateway:

```text
provider + selected model + credential
  -> configured wire protocol
  -> minimal non-sensitive invocation
  -> structured test status
```

`POST /providers/{provider_id}/test` accepts an optional
`LlmProviderTestRequest(model_id: UUID | None)`. The ID is a Bioinfoflow model
record and must belong to the provider. Existing clients may omit the body; the
service then selects the first provider model deterministically. A provider
without models returns a safe failed result instructing the user to add or
discover a model.

Test status includes protocol, model, latency, success, and a safe structured
error. It excludes the key, prompt, full request, raw provider response, and
credential fingerprint. Internally, the service stores a keyed HMAC
fingerprint derived from provider kind, normalized base URL, protocol,
credential source/name, resolved credential, provider template metadata, and
tested model identity. The HMAC key comes from server-side secret material and
the fingerprint is never logged or returned. Public provider reads,
configuration responses, probe responses, logs, and serialized errors are
constructed from a sanitized public status that cannot contain the internal
fingerprint. A result is displayed only while the internal fingerprint matches
current configuration.

## Frontend

Only templates supporting multiple protocols display a selector. OpenAI and
OpenAI Compatible expose Chat Completions and Responses. Saved providers
restore the persisted selection. Saving configuration, discovering models, and
testing connectivity are separate actions and states. Save succeeds with a
manually supplied model even if `/models` is unavailable; discovery is explicit
or best-effort after persistence.

The UI explains that protocol choice follows endpoint documentation and is not
inferred from the model name. Both locales and accessibility labels are
required.

## Reliability Ownership

For this campaign:

- LiteLLM backend performs one invocation attempt per Bioinfoflow retry.
- Bioinfoflow structured retry policy handles replay-safe transient failures.
- Bioinfoflow profile fallback handles different semantic models.

A later LiteLLM Router enhancement may own load balancing and cooldown among
equivalent deployments of one logical model. It must not also own cross-model
fallback.

## Security

- Credential-bearing fields use `repr=False`.
- Model events and ledger payloads contain endpoint IDs, not credentials.
- Public errors are normalized and redacted.
- Provider probe status is safe to persist and return through the API.
- Live relay tests read secrets from environment or the existing encrypted
  local credential and never print them.
- In team mode, server environment credentials and non-public provider
  destinations are deployment-owned resources available only to owner/admin
  roles. Personal and development modes retain localhost and internal-relay
  support.
- Public provider hostnames can be saved without DNS access, while test and
  discovery operations re-resolve the hostname immediately before network I/O
  and reject private, loopback, link-local, reserved, internal, or unresolvable
  targets for ordinary team members.

## Acceptance Criteria

- Existing Chat providers remain behavior-compatible.
- AgentCore loop and runtime no longer import or monkeypatch LiteLLM calls.
- Importing the model runtime is deterministic and does not depend on the LLM
  catalog package being imported first.
- Explicit persisted protocol selects `acompletion()` or `aresponses()`.
- The configured relay completes `gpt-5.4-mini` through Responses.
- Responses text, tools, usage, and phase are normalized into AgentCore events.
- Responses continuation is codec-owned, target-bound, and persisted at most
  once per active turn.
- Tool approvals pause and resume with stable call IDs for both protocols.
- Provider test executes the same gateway path used by AgentCore.
- Ordinary team members cannot use provider configuration to read arbitrary
  server environment variables or target non-public backend network addresses.
- No protocol inference or relay-specific hardcoding exists.
- Migration upgrade/downgrade, backend tests/Ruff, frontend tests/lints/build,
  live smoke, and independent reviews pass before the PR is opened.
