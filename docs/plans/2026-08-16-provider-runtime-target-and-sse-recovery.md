# Provider Runtime Target and Agent SSE Recovery Plan

## Status

Approved for implementation on 2026-08-16.

## Goal

Fix two failures at their ownership boundaries instead of adding provider- or
error-specific patches:

1. Provider setup, testing, discovery, and Agent Runtime must resolve the same
   exact endpoint and upstream API contract for every provider.
2. The agent session hook must stop polling a session that is known not to
   exist while remaining able to recover from transient snapshot failures.

The implementation must preserve the existing working Kimi path, correct the
DeepSeek endpoint drift, and avoid changing exact endpoints such as Z.AI's
non-`/v1` URL.

## Evidence and Root Causes

### Provider drift

The provider registry already owns reviewed exact endpoints, including:

- DeepSeek: `https://api.deepseek.com/v1`
- Z.AI: `https://api.z.ai/api/paas/v4`
- Kimi Code: `https://api.kimi.com/coding/v1`

Legacy persisted rows may have a null `base_url`. Runtime resolution previously
treated null as permission to omit `api_base`, so LiteLLM supplied its own
provider default. For DeepSeek that selects `https://api.deepseek.com/beta`,
which is not the endpoint BioinfoFlow configured. The same endpoint decision is
currently repeated across catalog, provider test, and agent runtime code.

The violated invariant is: a configured provider has one product-owned exact
runtime endpoint. LiteLLM is an execution adapter and must not silently replace
that endpoint.

### Stale session polling

The frontend can retain a previously selected session ID after the backend no
longer contains that session. The hook repeatedly requests the events endpoint,
receives 404, reconnects, and repeats. A partial fix that waits for the initial
snapshot prevents the loop, but also prevents live recovery after a transient
non-404 snapshot failure and leaves the UI stuck in `connecting`.

The violated invariant is: only a confirmed missing session is terminal for
that session ID. Transport failures are recoverable and must not be represented
as permanent absence.

## Reference Model

The implementation follows the provider ownership pattern used by pi-ai at
commit `086c32e74530564922d011ade23ff582c9d63116`:

- provider identity and API family are separate dimensions;
- model targets carry an explicit exact base URL;
- branded providers own their endpoint facts;
- execution dispatches from the declared API family instead of model-name or
  URL inference;
- special providers compose a common transport rather than duplicating the
  whole runtime.

BioinfoFlow keeps LiteLLM for transport translation, but provider registry data
remains authoritative for product configuration.

## Design

### One resolved executable target

Introduce one immutable value produced from persisted provider/model state and
the provider registry/profile:

```text
ResolvedModelTarget
|- provider_id
|- provider_kind
|- upstream_api_family
|- exact_base_url
|- credential
|- upstream_model_id
|- wire_protocol
|- compatibility
`- capabilities
```

The concrete type may reuse or narrow the existing `ModelTarget` contract. It
must have one production resolver and be consumed by both:

- provider connectivity/runtime tests;
- Agent Runtime model invocation.

Rules:

1. A persisted explicit base URL wins.
2. Otherwise, a known branded provider uses its registry endpoint exactly.
3. A custom provider must provide an explicit endpoint; no suffix is guessed.
4. No generic code appends `/v1` or selects a beta endpoint.
5. Credential values remain secret and excluded from representations/logs.
6. The compatibility `provider_templates.py` facade exposes registry data but
   does not own runtime endpoint policy.

### Agent session lifecycle

Model session loading as explicit states:

```text
loading -> present -> streaming/reconnecting
        -> missing -> stopped
        -> transient_error -> recoverable/disconnected -> retry
```

Rules:

1. Initial snapshot 404 marks the requested session missing and does not open
   SSE.
2. A session that disappears after loading closes SSE and stops reconnecting.
3. A transient snapshot failure must leave the hook recoverable and may start
   or retry live recovery.
4. Switching session IDs tears down the prior lifecycle.
5. Snapshot request coalescing remains intact.
6. Dead speculative controls such as `skipIfHydrated` are removed.

## TDD Seams and Regression Cases

### Backend seam

Resolve one persisted provider/model into one immutable executable target.

Write failing tests before implementation for:

- legacy DeepSeek with null `base_url` resolves to the exact registry `/v1`;
- Z.AI remains byte-for-byte `https://api.z.ai/api/paas/v4`;
- all primary branded provider defaults remain byte-for-byte exact;
- explicit custom/provider overrides remain unchanged;
- provider test and Agent Runtime receive equivalent targets;
- the LiteLLM invocation receives explicit `api_base` for DeepSeek;
- Kimi Code retains its endpoint and API-family behavior.

### Frontend seam

Exercise `useAgentSession` as a lifecycle boundary.

Write failing tests before implementation for:

- initial 404 never opens SSE;
- loaded session disappearing closes SSE and does not reconnect;
- transient initial snapshot failure enters a recoverable state and restores
  live updates without manual intervention;
- switching sessions tears down the stale stream;
- concurrent snapshot requests remain coalesced.

## Implementation Phases and Commits

1. `docs: plan provider runtime target consolidation`
   - commit this plan and the pi-ai comparison note if tracked.
2. `refactor: centralize provider runtime target resolution`
   - add red tests;
   - move endpoint/runtime ownership into the registry/profile boundary;
   - route provider test and Agent Runtime through the same resolver;
   - remove compatibility-facade policy and duplicated helpers.
3. `fix: make agent session streaming recover safely`
   - add lifecycle regression tests;
   - implement missing-versus-transient behavior;
   - remove dead hydration controls.
4. Optional review-fix commit when parallel review finds material issues.

Each code commit must leave its focused tests green.

## Verification

Backend, from `backend/`:

```bash
rtk uv run pytest tests/test_agent_harness/test_model_runtime_resolution.py \
  tests/test_services/test_llm_provider_platform.py
rtk uv run pytest
rtk uv run ruff check .
```

Frontend, from `frontend/`:

```bash
rtk bun run test tests/unit/hooks/use-agent-session.test.tsx
rtk bun run test
rtk bun run lint
rtk bun run lint:i18n
rtk bun run lint:dead-code
```

Repository:

```bash
rtk git diff --check
```

Before PR, run parallel Standards and Spec reviews against the fixed point and
this plan, fix all validated findings, re-run verification, fetch `origin`, and
rebase onto `origin/main`.

## Completion Criteria

- DeepSeek never falls through to LiteLLM's beta default.
- Z.AI and every other branded provider retain their exact registry endpoint.
- Provider Test and Agent Runtime use the same resolved target path.
- Custom endpoints are explicit and never mutated by generic suffix logic.
- A stale session produces at most the confirming 404 flow and no reconnect
  storm.
- A transient snapshot failure recovers without a manual retry.
- Focused and broad test/lint suites pass.
- Review has no remaining validated findings.
- The branch is rebased, the PR checks pass, and the PR is rebase-merged.
