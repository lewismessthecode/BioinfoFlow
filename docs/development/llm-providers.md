# LLM Provider Registry

Bioinfoflow owns provider setup through an immutable backend registry. The
frontend renders that registry and must not infer provider behavior from URLs,
key prefixes, or model names.

## Phase-One Providers

| Provider | Registry ID | Default endpoint | Catalog strategy |
| --- | --- | --- | --- |
| OpenAI | `openai` | `https://api.openai.com/v1` | snapshot plus `/models` |
| Anthropic | `anthropic` | `https://api.anthropic.com` | snapshot plus native `/v1/models` |
| OpenRouter | `openrouter` | `https://openrouter.ai/api/v1` | snapshot plus public `/models` |
| Fireworks AI | `fireworks` | `https://api.fireworks.ai/inference/v1` | snapshot plus `/models` |
| Qwen | `qwen` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | snapshot plus `/models` |
| DeepSeek | `deepseek` | `https://api.deepseek.com/v1` | snapshot plus `/models` |
| xAI | `xai` | `https://api.x.ai/v1` | snapshot plus `/models` |
| Z.AI | `zai` | `https://api.z.ai/api/paas/v4` | snapshot plus `/models` |
| Kimi Code | `kimi-code` | `https://api.kimi.com/coding/v1` | three pinned coding models |
| MiniMax | `minimax` | `https://api.minimax.io/v1` | reviewed snapshot |
| Hugging Face | `huggingface` | `https://router.huggingface.co/v1` | reviewed snapshot |
| Gemini | `gemini` | `https://generativelanguage.googleapis.com` | snapshot plus native `v1beta/models` |

Qwen may override its endpoint with
`https://dashscope-intl.aliyuncs.com/compatible-mode/v1`. Kimi Open Platform
Global and China are not Kimi Code: their keys and endpoints are not
interchangeable.

## Operation Boundaries

- `POST /provider-setups` validates and stores configuration locally. It never
  contacts a provider, even if an older client sends `discover=true`.
- `POST /providers/{id}/discover-models` is an explicit, optional catalog
  refresh. A failure does not mutate existing model records.
- `POST /providers/{id}/test` makes a minimal real model request. It reports
  configuration, catalog, and runtime checkpoints; only runtime success makes
  the overall result successful.

The checked-in snapshot supplies initial model choices without making save
depend on `/models`. Manual and snapshot models are not removed merely because
a live catalog omits them.

## Refreshing The Snapshot

From `backend/`:

```bash
rtk curl -fsSL https://models.dev/api.json -o /tmp/models-dev-api.json
rtk uv run python scripts/update_llm_catalog.py --input /tmp/models-dev-api.json
rtk uv run pytest tests/test_services/test_llm_catalog_snapshot.py -q
```

Generate twice and compare `rtk shasum app/services/llm/catalog_snapshot.json`
to confirm deterministic output.

Review before committing:

- only the twelve mapped source providers changed
- every included model supports tools and text output
- embedding, image-generation, video, and realtime-only models are absent
- Kimi Code remains exactly `k3`, `kimi-for-coding`, and
  `kimi-for-coding-highspeed`
- endpoints, model IDs, and capability changes agree with official provider
  documentation

## Live Smoke Tests

Real keys are intentionally not required by CI. In a development deployment:

1. Paste one provider key and save. Confirm the provider and snapshot models
   appear without a provider-network request.
2. Use **Refresh models** and inspect the provider-specific error if it fails.
3. Select a model and use **Test**. Confirm the runtime checkpoint passes.
4. Repeat with Kimi Code and verify the stored endpoint is
   `https://api.kimi.com/coding/v1`.

Never place real keys in tests, documentation, shell history, or PR output.

## Legacy Reconciliation

- `grok` becomes `xai`.
- A Kimi row already using `api.kimi.com/coding/v1` becomes `kimi-code`.
- Moonshot `.ai` and `.cn` rows are disabled and marked
  `kimi_open_platform_removed`; encrypted credentials remain stored until the
  user removes the connection.
- Other previously configured providers remain readable through the legacy
  adapter, but are not returned by the primary provider-template endpoint.
