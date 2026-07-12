# Explicit insecure HTTP providers and provider settings redesign

## Goal

Allow an administrator or user to explicitly configure a public plain-HTTP LLM
provider, including `http://8.129.13.231:8079/v1`, without weakening the default
transport policy for existing providers. Redesign the AI provider settings panel
so configuration is compact, aligned, readable, and explicit about transport
risk.

## Scope

- Add a provider-level `allow_insecure_http` boolean with a default of `false`.
- Preserve current behavior for HTTPS, loopback, private-network, and internal
  HTTP endpoints.
- Require an explicit opt-in before accepting a public HTTP endpoint.
- Enforce the policy while saving, discovering models, and starting agent model
  requests.
- Return and display specific provider errors instead of a generic save failure.
- Redesign the provider catalog panel without changing the surrounding settings
  shell or provider catalog concepts.
- Update English and Simplified Chinese copy.

Codex Responses API support remains a later harness project. This change creates
the provider transport contract it can reuse but does not add that adapter.

## Chosen approach

Use a first-class database column instead of provider metadata or a global
environment escape hatch.

`allow_insecure_http` is security-sensitive, must be visible in API contracts,
and must have a reliable default. A typed column makes the setting reviewable,
queryable, migration-safe, and difficult to bypass accidentally. A global flag
would weaken every provider; opaque metadata would make enforcement and audits
less dependable.

## Data model and API

Add `allow_insecure_http BOOLEAN NOT NULL DEFAULT FALSE` to `llm_providers` with
an Alembic migration.

Expose the field through:

- provider create, update, read, and configured-provider responses;
- provider setup requests and results;
- frontend provider and setup types;
- frontend setup request serialization.

Existing rows migrate to `false`. Existing callers that omit the field retain
the secure default.

## Transport policy

Refactor provider URL validation to accept an explicit policy value:

```text
HTTPS                              allowed
HTTP loopback/private/internal     allowed
HTTP public + opt-in false         rejected
HTTP public + opt-in true          allowed
Malformed/non-HTTP(S) URL          rejected
```

The opt-in applies only to the HTTP transport rule. It does not bypass malformed
URL checks, tenant authorization, credential protection, or tool permissions.

Enforce the invariant at three boundaries:

1. Provider create/update/setup before persistence.
2. Model discovery before sending credentials to the endpoint.
3. Agent runtime provider resolution before constructing a model request.

This defense in depth prevents a manually altered or legacy database row from
silently bypassing the runtime policy.

## Provider settings UI

### Visual direction

Use the existing Tailwind and component system with a warm, monochrome,
editorial treatment:

- white and warm-neutral surfaces;
- one-pixel low-contrast borders;
- crisp 8-10px radii;
- no gradients or heavy shadows;
- charcoal primary text and quiet secondary text;
- pale green for ready state and pale yellow for transport risk;
- restrained transitions and pressed feedback.

### Layout

Replace the tall, loosely aligned provider rows with compact provider cards.

On desktop, each card uses three aligned zones:

1. Provider identity: name, status, and credential source.
2. Configuration: labelled inputs in a responsive grid.
3. Actions: documentation link and a consistently aligned save button.

Common hosted providers remain compact because they expose only the API key.
Endpoint-based providers expand only for the fields and warning they need. On
narrow screens the same zones stack in reading order without clipped labels or
orphaned buttons.

The catalog header contains the configured count and model refresh action in one
compact band. Loading uses provider-shaped skeleton rows rather than a spinner
over an empty container.

### Insecure transport interaction

When an endpoint is public plain HTTP, show a pale-yellow inline safety panel
inside that provider card. The panel contains:

- the label “Allow insecure HTTP”;
- concise copy explaining that the API key and prompts are sent without TLS;
- a switch aligned to the right;
- a persistent risk indicator after saving.

The switch is off by default. Saving a public HTTP endpoint while it is off
keeps the backend authoritative and displays the returned validation error
inline. Enabling it sends `allow_insecure_http: true` with the provider setup.

The UI may classify obvious URL forms to reveal the control early, but client
logic is advisory only; backend validation remains the security boundary.

### Error handling

Track setup errors per provider card. Display the backend message below the
relevant form, keep the entered values intact, and retain a concise error toast
for global feedback. Clear the row error when the user edits or retries that
provider.

Catalog-load failure replaces the empty panel with an inline error state and a
retry action.

## Compatibility

- Existing providers and API clients continue to work because the new field is
  optional on writes and defaults to `false`.
- HTTPS behavior is unchanged.
- Current local, Docker, Kubernetes, and private-network HTTP providers remain
  allowed without enabling the switch.
- Credential storage and masking are unchanged.
- Provider kinds remain generic; no CCH-specific provider or URL is hardcoded.
- `http://8.129.13.231:8079/v1` works only when its provider explicitly stores
  `allow_insecure_http = true`.

## Verification

### Backend

- Migration upgrades and downgrades cleanly.
- URL validation covers HTTPS, internal HTTP, rejected public HTTP, and opted-in
  public HTTP.
- Provider setup persists and returns the flag.
- Update paths cannot change to public HTTP unless opted in.
- Model discovery refuses a public HTTP provider when the flag is false.
- Agent runtime refuses the same invalid state before sending credentials.
- Existing LLM API and agent tests remain green.

### Frontend

- Provider setup serializes the flag.
- Public HTTP reveals the warning and switch.
- The target CCH URL can be saved when the switch is enabled.
- Backend errors render in the correct provider card.
- Existing stored credentials remain write-only.
- Desktop and narrow layouts keep labels, inputs, status, and actions aligned.
- English and Chinese locale keys stay synchronized.

### Commands

Run backend tests and Ruff for backend changes. Run frontend lint, i18n lint,
tests, and dead-code checks for the UI refactor. Perform browser verification at
desktop and narrow viewport widths with the current worktree's backend and
frontend services.

## Delivery

Rebase the implementation branch onto the latest `origin/main`, resolve any
conflicts without discarding unrelated work, commit with a Conventional Commit,
push the branch, and open a PR with a Conventional Commit title.
