# Common LLM Provider Catalog Plan

## Goal

Remove the prior relay-specific direction and make Bioinfoflow's AI provider
setup generic: choose a common provider, paste an API key, save, and load the
provider's model list when the upstream API supports discovery.

## Requirements

- Delete relay-specific examples, model IDs, relay IPs, and UI copy.
- Keep the current settings UI shape; improve the setup path without a redesign.
- Prefer official provider defaults over user-entered model IDs.
- Keep endpoint override and manual model ID as advanced fallbacks for local
  gateways, self-hosted services, and providers whose model endpoint is blocked.
- Cover common providers: OpenAI, Anthropic, Gemini, DeepSeek, xAI/Grok, Groq,
  OpenRouter, Ollama, vLLM, Kimi/Moonshot global and China, Qwen/DashScope,
  Mistral, Cohere, Together AI, Fireworks AI, and Perplexity.

## Official API Basis

- OpenAI: `https://platform.openai.com/docs/api-reference/models/list`
- Anthropic: `https://docs.anthropic.com/en/api/models-list`
- Gemini: `https://ai.google.dev/api/models`
- DeepSeek: `https://api-docs.deepseek.com/`
- xAI: `https://docs.x.ai/docs/api-reference`
- Groq: `https://console.groq.com/docs/api-reference#models-list`
- OpenRouter: `https://openrouter.ai/docs/api-reference/list-available-models`
- Ollama: `https://docs.ollama.com/openai`
- vLLM: `https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html`
- Moonshot/Kimi global: `https://platform.kimi.ai/docs/api/chat`
- Moonshot/Kimi China: `https://platform.kimi.com/docs/api/chat`
- Qwen/DashScope: `https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope`
- Mistral: `https://docs.mistral.ai/api/`
- Cohere: `https://docs.cohere.com/docs/compatibility-api`
- Together AI: `https://docs.together.ai/reference/models-1`
- Fireworks AI: `https://docs.fireworks.ai/api-reference/list-models`
- Perplexity: `https://docs.perplexity.ai/api-reference/chat-completions`

## Design

Most hosted providers publish an OpenAI-compatible API. Bioinfoflow should model
them as first-class templates with official default `base_url`, API-key env vars,
and `openai_models` discovery. The runtime should route these through LiteLLM's
OpenAI-compatible adapter (`openai/` prefix plus provider `api_base`) rather than
adding bespoke per-provider code.

Provider-specific discovery remains small and explicit:

- Anthropic uses `GET /v1/models` with `x-api-key` and `anthropic-version`.
- Gemini uses `GET /v1beta/models` with `x-goog-api-key`.
- Ollama uses `GET /api/tags`.
- Cohere uses its documented list-models shape while invocation uses the
  compatibility API base URL.

The UI continues to render fields from provider templates. For most providers,
the only visible field is `API key`; providers that genuinely need more show
`Endpoint` and optional `Model ID`. Copy should stay generic: no relay brand, no
specific IP address, no provider-specific workaround text.

## Validation

- Backend tests:
  - provider templates include the common provider IDs and expose one-field key
    setup for hosted OpenAI-compatible providers;
  - relay-specific strings are absent from provider templates and docs examples;
  - OpenAI-compatible providers route through the generic `openai/` adapter;
  - Cohere model discovery parses the official list response shape;
  - public HTTP endpoint opt-in stays generic and does not mention one service.
- Frontend tests:
  - provider cards keep the simple key-first setup copy;
  - Anthropic no longer renders relay-specific endpoint label/help;
  - demo runtime provider templates match the backend catalog breadth.
- Docs checks:
  - `.env.example`, `RUNBOOK.md`, and `docs/getting-started/docker.md` describe
    generic provider setup and contain no relay-specific artifacts.
