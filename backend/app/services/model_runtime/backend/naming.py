from __future__ import annotations


_LITELLM_PREFIX_BY_PROVIDER_KIND = {
    "anthropic": "anthropic/",
    "deepseek": "deepseek/",
    "gemini": "gemini/",
    "grok": "xai/",
    "groq": "groq/",
    "ollama": "ollama_chat/",
    "openai_compatible": "openai/",
    "openrouter": "openrouter/",
    "vllm": "openai/",
}


def litellm_model_name(provider_kind: str, model: str) -> str:
    """Translate a canonical provider/model pair into LiteLLM's model name."""

    prefix = _LITELLM_PREFIX_BY_PROVIDER_KIND.get(provider_kind, "")
    if prefix and model.startswith(prefix):
        return model
    return f"{prefix}{model}"
