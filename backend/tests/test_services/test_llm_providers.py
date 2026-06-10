from __future__ import annotations

from app.services.llm.provider_templates import litellm_model_name


def test_ollama_uses_native_litellm_chat_route():
    assert (
        litellm_model_name("ollama", "deepseek-r1:latest")
        == "ollama_chat/deepseek-r1:latest"
    )
