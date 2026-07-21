# Provider Request Compilation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compile AgentCore's provider-neutral model invocation into a LiteLLM-compatible, provider-specific request for all twelve phase-one API-key providers, fixing Kimi Code and the equivalent local validation failures found for Z.AI, Qwen, and Hugging Face.

**Architecture:** The protocol codec continues to create a baseline request. `ProviderProfile.compile_request()` then returns a new request after applying model-, provider-, and wire-protocol-specific transformations. The gateway attaches endpoint credentials only after compilation, and LiteLLM remains the network transport and response normalizer.

**Tech Stack:** Python 3.13, FastAPI service modules, LiteLLM 1.83, pytest, Ruff.

---

## File map

- Modify `backend/app/services/llm/profiles/base.py`: define the pure request compiler contract and shared copy/merge helpers.
- Modify `backend/app/services/model_runtime/gateway.py`: replace flat option merging with complete request compilation.
- Modify `backend/app/services/llm/profiles/deepseek.py`: encode DeepSeek thinking without conflicting controls.
- Modify `backend/app/services/llm/profiles/kimi_code.py`: implement Kimi-specific token, reasoning, message, and tool transformations.
- Create `backend/app/services/llm/profiles/kimi_schema.py`: normalize Kimi tool JSON Schemas as a focused pure helper.
- Modify `backend/app/services/llm/profiles/minimax.py`: compile MiniMax reasoning fields through `extra_body`.
- Modify `backend/app/services/llm/profiles/zai.py`: stop inheriting DeepSeek and compile Z.AI fields explicitly.
- Create `backend/app/services/llm/profiles/qwen.py`: compile Qwen thinking toggles only for Qwen-family models.
- Create `backend/app/services/llm/profiles/huggingface.py`: avoid unverified universal effort controls for heterogeneous routed models.
- Modify `backend/app/services/llm/profiles/__init__.py`: register the new concrete profiles.
- Modify `backend/tests/test_services/test_llm_provider_profiles.py`: unit-test provider compilation and invariants.
- Modify `backend/tests/test_model_runtime/test_gateway_profiles.py`: prove compilation happens at the gateway boundary.
- Modify `backend/tests/test_model_runtime/test_litellm_backend.py`: verify compiled call shapes survive LiteLLM's local validation without external credentials.

### Task 1: Lock the failing behavior with request-compilation tests

**Files:**

- Modify: `backend/tests/test_services/test_llm_provider_profiles.py`
- Modify: `backend/tests/test_model_runtime/test_gateway_profiles.py`

- [ ] **Step 1: Replace flat-option expectations with complete-request expectations**

Add a baseline helper and table-driven assertions equivalent to:

```python
def compile_chat_request(provider_kind: str, model_name: str, *, enabled=True):
    return profile_for(provider_kind).compile_request(
        {
            "model": model_name,
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
            "max_tokens": 321,
        },
        model_name=model_name,
        wire_protocol="chat_completions",
        reasoning=ReasoningRequest(
            enabled=enabled,
            effort="medium" if enabled else None,
        ),
    )
```

Assert at minimum:

```python
kimi = compile_chat_request("kimi_code", "kimi-for-coding")
assert kimi["extra_body"]["thinking"] == {"type": "enabled"}
assert kimi["max_completion_tokens"] == 321
assert "thinking" not in kimi
assert "max_tokens" not in kimi

zai = compile_chat_request("zai", "glm-4.7")
assert zai["extra_body"]["thinking"] == {"type": "enabled"}
assert "thinking" not in zai

qwen = compile_chat_request("qwen", "qwen3-max")
assert qwen["extra_body"]["enable_thinking"] is True
assert "reasoning_effort" not in qwen

hf = compile_chat_request("huggingface", "Qwen/Qwen3-32B")
assert "reasoning_effort" not in hf
```

- [ ] **Step 2: Add gateway regression assertions**

Update the Kimi gateway test to assert the backend receives
`extra_body.thinking`, `max_completion_tokens`, and no top-level `thinking` or
`max_tokens`.

- [ ] **Step 3: Run the focused tests and verify they fail for the missing compiler**

Run:

```bash
rtk uv run pytest tests/test_services/test_llm_provider_profiles.py tests/test_model_runtime/test_gateway_profiles.py -q
```

Expected: failures because `compile_request` does not exist and the gateway
still merges `invocation_options()`.

### Task 2: Establish the profile compiler boundary

**Files:**

- Modify: `backend/app/services/llm/profiles/base.py`
- Modify: `backend/app/services/model_runtime/gateway.py`
- Test: `backend/tests/test_services/test_llm_provider_profiles.py`
- Test: `backend/tests/test_model_runtime/test_gateway_profiles.py`

- [ ] **Step 1: Implement the pure default compiler**

Add a method with this contract:

```python
def compile_request(
    self,
    request: dict[str, Any],
    *,
    model_name: str,
    wire_protocol: WireProtocol,
    reasoning: ReasoningRequest,
) -> dict[str, Any]:
    del model_name, wire_protocol
    compiled = copy.deepcopy(request)
    if reasoning.enabled:
        compiled["reasoning_effort"] = reasoning.effort or "medium"
    return compiled
```

Keep compilation pure by deep-copying nested messages, tools, and `extra_body`.
Remove `invocation_options()` after all subclasses and tests migrate.

- [ ] **Step 2: Make the gateway delegate complete compilation**

Replace `request.update(profile.invocation_options(...))` with:

```python
request = profile.compile_request(
    request,
    model_name=invocation.target.model_name,
    wire_protocol=wire_protocol,
    reasoning=invocation.reasoning,
)
```

Leave API base, API key, network policy, backend dispatch, response decoding,
and error normalization unchanged.

- [ ] **Step 3: Run the focused tests**

Run the Task 1 command. Expected: default-profile tests pass; specialized
provider expectations still fail.

- [ ] **Step 4: Commit the compiler boundary**

```bash
rtk git add backend/app/services/llm/profiles/base.py backend/app/services/model_runtime/gateway.py backend/tests/test_services/test_llm_provider_profiles.py backend/tests/test_model_runtime/test_gateway_profiles.py
rtk git commit -m "refactor: compile provider model requests"
```

### Task 3: Implement Kimi Code's official request dialect

**Files:**

- Modify: `backend/app/services/llm/profiles/kimi_code.py`
- Create: `backend/app/services/llm/profiles/kimi_schema.py`
- Test: `backend/tests/test_services/test_llm_provider_profiles.py`
- Test: `backend/tests/test_model_runtime/test_gateway_profiles.py`

- [ ] **Step 1: Add failing Kimi tool and message tests**

Cover a schema containing local `$defs`/`$ref` and an enum property without a
`type`. Assert the compiled schema dereferences the local definition, infers the
enum's type, and does not mutate the source schema. Add an assistant tool-call
message with `content=None` and assert `content` is omitted.

- [ ] **Step 2: Port the focused schema normalizer**

Implement pure helpers that:

- resolve local JSON Pointer `$ref` values while preserving circular refs;
- remove unused `$defs` and `definitions` buckets;
- infer missing property types from `enum`, `const`, `properties`, `items`, or
  primitive validation keywords;
- recurse through standard JSON Schema child-schema positions;
- return a deep copy.

This is a Python adaptation of Kimi Code's `kimi-schema.ts`, restricted to the
JSON Schema behavior required by AgentCore tools.

- [ ] **Step 3: Implement `KimiCodeProfile.compile_request()`**

Starting from a deep copy of the baseline request:

```python
compiled["max_completion_tokens"] = compiled.pop("max_tokens")
compiled["extra_body"] = {
    **compiled.get("extra_body", {}),
    "thinking": {"type": "enabled"},
}
```

For disabled reasoning, use `{"type": "disabled"}` only for a model whose
official contract allows the toggle; otherwise omit the disable field and keep
the mandatory model default. Do not send an effort for `kimi-for-coding` or its
high-speed variant. For `k3`, pass only an officially supported normalized
effort.

Normalize every function tool's `parameters`. For assistant messages carrying
`tool_calls`, delete `content` when it is `None` or an empty string.

- [ ] **Step 4: Run Kimi-focused tests**

```bash
rtk uv run pytest tests/test_services/test_llm_provider_profiles.py -k kimi -q
rtk uv run pytest tests/test_model_runtime/test_gateway_profiles.py -q
```

Expected: all Kimi compilation tests pass.

- [ ] **Step 5: Commit the Kimi dialect**

```bash
rtk git add backend/app/services/llm/profiles/kimi_code.py backend/app/services/llm/profiles/kimi_schema.py backend/tests/test_services/test_llm_provider_profiles.py backend/tests/test_model_runtime/test_gateway_profiles.py
rtk git commit -m "fix: compile Kimi Code requests"
```

### Task 4: Compile the remaining phase-one provider controls

**Files:**

- Modify: `backend/app/services/llm/profiles/deepseek.py`
- Modify: `backend/app/services/llm/profiles/minimax.py`
- Modify: `backend/app/services/llm/profiles/zai.py`
- Create: `backend/app/services/llm/profiles/qwen.py`
- Create: `backend/app/services/llm/profiles/huggingface.py`
- Modify: `backend/app/services/llm/profiles/__init__.py`
- Test: `backend/tests/test_services/test_llm_provider_profiles.py`

- [ ] **Step 1: Add a twelve-provider compilation matrix**

For every phase-one provider, assert an enabled reasoning request compiles to a
shape appropriate for its LiteLLM transport and never produces known conflicting
controls. Include disabled reasoning cases for optional-thinking profiles and
mandatory-reasoning cases where disabling must be omitted.

- [ ] **Step 2: Implement provider-specific compilers**

- DeepSeek: keep one accepted thinking representation; do not send both a
  top-level `thinking` and `extra_body.thinking`.
- MiniMax: place `reasoning_split` and model-supported thinking controls in
  `extra_body`.
- Z.AI: become a direct `ProviderProfile` subclass and put its documented
  thinking toggle under `extra_body` instead of inheriting DeepSeek.
- Qwen: for Qwen-family model IDs put `enable_thinking` in `extra_body`; for
  heterogeneous non-Qwen DashScope models omit unverified controls.
- Hugging Face: omit a universal effort field for heterogeneous routed models;
  preserve the selected model's default reasoning mode.
- OpenAI, Anthropic, OpenRouter, Fireworks, xAI, and Gemini: retain their current
  LiteLLM-supported normalized paths through the new compiler contract.

- [ ] **Step 3: Run all profile and gateway tests**

```bash
rtk uv run pytest tests/test_services/test_llm_provider_profiles.py tests/test_model_runtime/test_gateway_profiles.py -q
```

Expected: pass.

- [ ] **Step 4: Commit the provider matrix**

```bash
rtk git add backend/app/services/llm/profiles backend/tests/test_services/test_llm_provider_profiles.py
rtk git commit -m "fix: normalize provider reasoning controls"
```

### Task 5: Verify the generated call shapes against LiteLLM 1.83

**Files:**

- Modify: `backend/tests/test_model_runtime/test_litellm_backend.py`

- [ ] **Step 1: Add a no-network LiteLLM compatibility test**

Use LiteLLM's parameter-mapping function for each compiled request after
resolving the routed model prefix. The test must fail if LiteLLM raises
`UnsupportedParamsError` before network dispatch. Cover at least Kimi, Z.AI,
Qwen, Hugging Face, DeepSeek, MiniMax, Anthropic, OpenRouter, xAI, Fireworks,
Gemini, and OpenAI.

- [ ] **Step 2: Prove the old Kimi shape is rejected**

Keep a narrow regression assertion showing that LiteLLM 1.83 rejects
top-level `thinking` for `openai/kimi-for-coding`, while the profile's compiled
`extra_body.thinking` shape maps successfully. This documents the exact root
cause without external credentials.

- [ ] **Step 3: Run the LiteLLM backend tests**

```bash
rtk uv run pytest tests/test_model_runtime/test_litellm_backend.py -q
```

Expected: pass without network access.

- [ ] **Step 4: Commit compatibility coverage**

```bash
rtk git add backend/tests/test_model_runtime/test_litellm_backend.py
rtk git commit -m "test: verify provider request compatibility"
```

### Task 6: Complete backend verification and publish the fix PR

**Files:**

- Modify only files required by failures found during verification.

- [ ] **Step 1: Format and lint changed Python files**

```bash
rtk uv run ruff format app/services/llm/profiles app/services/model_runtime/gateway.py tests/test_services/test_llm_provider_profiles.py tests/test_model_runtime/test_gateway_profiles.py tests/test_model_runtime/test_litellm_backend.py
rtk uv run ruff check .
```

Expected: clean.

- [ ] **Step 2: Run focused runtime and provider tests**

```bash
rtk uv run pytest tests/test_services/test_llm_provider_profiles.py tests/test_model_runtime/test_gateway_profiles.py tests/test_model_runtime/test_chat_completions_codec.py tests/test_model_runtime/test_litellm_backend.py -q
```

Expected: pass.

- [ ] **Step 3: Run the full backend suite**

```bash
rtk uv run pytest
```

Expected: all tests pass with only the repository's documented skips.

- [ ] **Step 4: Inspect the final diff and repository state**

```bash
rtk git diff origin/main...HEAD --check
rtk git status --short
rtk git log --oneline origin/main..HEAD
```

Expected: no whitespace errors and no unrelated changes.

- [ ] **Step 5: Rebase once more, push, and create the PR**

```bash
rtk git fetch origin --prune
rtk git rebase origin/main
rtk git push -u origin codex/fix-provider-request-compilation
rtk gh pr create --base main --head codex/fix-provider-request-compilation --title "fix: compile provider model requests" --body-file /tmp/provider-request-compilation-pr.md
```

The PR body must summarize the root cause, the request compiler boundary,
provider coverage, official/reference sources, and exact verification results.
