"""Tests for provider registry and configuration."""

from __future__ import annotations


from app.services.agent.runtime.providers import (
    PROVIDER_REGISTRY,
    infer_provider_from_model,
    litellm_model_name,
)


def test_registry_has_all_providers():
    assert set(PROVIDER_REGISTRY.keys()) == {
        "anthropic",
        "openai",
        "gemini",
        "deepseek",
        "qwen",
        "kimi",
        "minimax",
        "xai",
        "openrouter",
        "ollama",
    }


def test_each_provider_has_default_model():
    for name, config in PROVIDER_REGISTRY.items():
        assert config.default_model, f"{name} missing default_model"


def test_each_provider_has_label():
    for name, config in PROVIDER_REGISTRY.items():
        assert config.label, f"{name} missing label"


def test_each_provider_has_models_or_is_dynamic():
    """Providers should either have a model catalog or be dynamic (ollama/openrouter)."""
    for name, config in PROVIDER_REGISTRY.items():
        if name not in ("ollama", "openrouter"):
            assert config.models, f"{name} should have a model catalog"


def test_each_provider_has_credential_config():
    """Every provider must declare how its credentials work."""
    for name, config in PROVIDER_REGISTRY.items():
        assert config.credential_type in (
            "api_key",
            "api_key_and_base_url",
            "base_url_only",
        ), f"{name} has invalid credential_type: {config.credential_type}"
        if config.credential_type in ("api_key", "api_key_and_base_url"):
            assert config.env_key_var, (
                f"{name} needs env_key_var for credential_type={config.credential_type}"
            )


def test_anthropic_has_prefix():
    assert PROVIDER_REGISTRY["anthropic"].prefix == "anthropic/"


def test_openrouter_has_base_url():
    assert "openrouter.ai" in PROVIDER_REGISTRY["openrouter"].base_url


def test_ollama_has_base_url():
    assert "11434" in PROVIDER_REGISTRY["ollama"].base_url


def test_openai_catalog_tracks_current_gpt_5_family():
    model_ids = {model.id for model in PROVIDER_REGISTRY["openai"].models}
    assert {
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.4-nano",
        "gpt-5.2",
        "gpt-5.1",
        "gpt-5-mini",
        "gpt-5-chat-latest",
    }.issubset(model_ids)


def test_gemini_catalog_uses_current_official_models():
    model_ids = {model.id for model in PROVIDER_REGISTRY["gemini"].models}
    assert {
        "gemini-3.1-pro-preview",
        "gemini-3-flash-preview",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    }.issubset(model_ids)


def test_kimi_catalog_uses_k2_series_models():
    kimi = PROVIDER_REGISTRY["kimi"]
    model_ids = {model.id for model in kimi.models}
    assert kimi.base_url == "https://api.moonshot.ai/v1"
    assert {
        "kimi-k2.5",
        "kimi-k2-thinking",
        "kimi-k2-turbo-preview",
    }.issubset(model_ids)


def test_minimax_catalog_uses_current_m2_series_models():
    minimax = PROVIDER_REGISTRY["minimax"]
    model_ids = {model.id for model in minimax.models}
    assert minimax.base_url == "https://api.minimax.io/v1"
    assert {
        "MiniMax-M2.7",
        "MiniMax-M2.7-highspeed",
        "MiniMax-M2.5",
        "MiniMax-M2.5-highspeed",
    }.issubset(model_ids)


def test_xai_provider_exposes_current_grok_models():
    xai = PROVIDER_REGISTRY["xai"]
    model_ids = {model.id for model in xai.models}
    assert xai.base_url == "https://api.x.ai/v1"
    assert {
        "grok-4",
        "grok-4.20-beta-latest-non-reasoning",
    }.issubset(model_ids)


class TestLitellmModelName:
    def test_anthropic(self):
        assert (
            litellm_model_name("anthropic", "claude-sonnet-4-6")
            == "anthropic/claude-sonnet-4-6"
        )

    def test_openai_no_prefix(self):
        assert litellm_model_name("openai", "gpt-5.4") == "gpt-5.4"

    def test_gemini(self):
        assert (
            litellm_model_name("gemini", "gemini-2.5-flash")
            == "gemini/gemini-2.5-flash"
        )

    def test_openrouter(self):
        assert (
            litellm_model_name("openrouter", "anthropic/claude-sonnet-4-6")
            == "openrouter/anthropic/claude-sonnet-4-6"
        )

    def test_ollama(self):
        assert litellm_model_name("ollama", "llama3.3") == "ollama/llama3.3"

    def test_xai(self):
        assert litellm_model_name("xai", "grok-4") == "xai/grok-4"

    def test_no_double_prefix(self):
        assert (
            litellm_model_name("anthropic", "anthropic/claude-sonnet-4-6")
            == "anthropic/claude-sonnet-4-6"
        )


class TestInferProvider:
    def test_claude_model(self):
        assert infer_provider_from_model("claude-sonnet-4-6") == "anthropic"

    def test_gpt_model(self):
        assert infer_provider_from_model("gpt-5.4") == "openai"

    def test_gemini_model(self):
        assert infer_provider_from_model("gemini-2.5-flash") == "gemini"

    def test_openrouter_slash_format(self):
        assert infer_provider_from_model("anthropic/claude-sonnet-4-6") == "openrouter"
        assert infer_provider_from_model("openai/gpt-5.4") == "openrouter"
        assert infer_provider_from_model("google/gemini-2.5-pro") == "openrouter"

    def test_unknown_defaults_to_ollama(self):
        assert infer_provider_from_model("llama3.3") == "ollama"

    def test_deepseek_model(self):
        assert infer_provider_from_model("deepseek-chat") == "deepseek"
        assert infer_provider_from_model("deepseek-reasoner") == "deepseek"

    def test_qwen_model(self):
        assert infer_provider_from_model("qwen3-coder-plus") == "qwen"

    def test_kimi_model(self):
        assert infer_provider_from_model("kimi-k2.5") == "kimi"

    def test_minimax_model(self):
        assert infer_provider_from_model("MiniMax-M2.7") == "minimax"

    def test_xai_model(self):
        assert infer_provider_from_model("grok-4") == "xai"
