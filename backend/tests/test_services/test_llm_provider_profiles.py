import pytest

from app.services.llm.profiles import ProviderConnection, profile_for
from app.services.model_runtime.contracts import ReasoningRequest


def connection(
    provider_kind: str,
    *,
    api_key: str = "secret",
    base_url: str | None = None,
) -> ProviderConnection:
    profile = profile_for(provider_kind)
    return ProviderConnection(
        base_url=base_url or profile.spec.endpoint.default_base_url,
        api_key=api_key,
    )


def test_default_catalog_request_uses_bearer_models_endpoint() -> None:
    request = profile_for("openai").catalog_request(connection("openai"))

    assert request.url == "https://api.openai.com/v1/models"
    assert request.headers == {"Authorization": "Bearer secret"}


def test_anthropic_catalog_request_uses_native_headers() -> None:
    request = profile_for("anthropic").catalog_request(connection("anthropic"))

    assert request.url == "https://api.anthropic.com/v1/models"
    assert request.headers["x-api-key"] == "secret"
    assert request.headers["anthropic-version"] == "2023-06-01"
    assert "Authorization" not in request.headers


def test_openrouter_catalog_is_public_and_does_not_send_saved_key() -> None:
    request = profile_for("openrouter").catalog_request(connection("openrouter"))

    assert request.url == "https://openrouter.ai/api/v1/models"
    assert request.headers == {}


def test_gemini_catalog_request_uses_query_free_native_key_header() -> None:
    request = profile_for("gemini").catalog_request(connection("gemini"))

    assert request.url == "https://generativelanguage.googleapis.com/v1beta/models"
    assert request.headers == {"x-goog-api-key": "secret"}


@pytest.mark.parametrize("provider_kind", ["minimax", "kimi_code", "huggingface"])
def test_bundled_catalog_profiles_do_not_create_network_requests(
    provider_kind: str,
) -> None:
    assert profile_for(provider_kind).catalog_request(connection(provider_kind)) is None


def test_catalog_url_composition_does_not_duplicate_version_or_models() -> None:
    request = profile_for("openai").catalog_request(
        connection("openai", base_url="https://gateway.example/v1/models/")
    )

    assert request.url == "https://gateway.example/v1/models"


def test_openai_catalog_parser_rejects_malformed_items() -> None:
    models = profile_for("openai").parse_catalog(
        {"data": [{"id": "gpt-test"}, {}, {"id": 42}]}
    )

    assert [model.id for model in models] == ["gpt-test"]


def test_anthropic_and_gemini_parsers_normalize_model_ids() -> None:
    anthropic = profile_for("anthropic").parse_catalog(
        {"data": [{"id": "claude-test", "display_name": "Claude Test"}]}
    )
    gemini = profile_for("gemini").parse_catalog(
        {"models": [{"name": "models/gemini-test", "displayName": "Gemini Test"}]}
    )

    assert [(model.id, model.name) for model in anthropic] == [
        ("claude-test", "Claude Test")
    ]
    assert [(model.id, model.name) for model in gemini] == [
        ("gemini-test", "Gemini Test")
    ]


def test_kimi_profile_compiles_openai_transport_request() -> None:
    source = {
        "model": "openai/kimi-for-coding",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": True,
        "max_tokens": 321,
    }

    compiled = profile_for("kimi_code").compile_request(
        source,
        model_name="kimi-for-coding",
        wire_protocol="chat_completions",
        reasoning=ReasoningRequest(enabled=True, effort="high"),
    )

    assert compiled["extra_body"]["thinking"] == {"type": "enabled"}
    assert compiled["max_completion_tokens"] == 321
    assert "thinking" not in compiled
    assert "reasoning_effort" not in compiled
    assert "max_tokens" not in compiled
    assert source["max_tokens"] == 321


def test_kimi_profile_normalizes_tool_schemas_without_mutating_source() -> None:
    source = {
        "model": "openai/kimi-for-coding",
        "messages": [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "inspect", "arguments": "{}"},
                    }
                ],
            }
        ],
        "stream": True,
        "max_tokens": 321,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "inspect",
                    "description": "Inspect a resource.",
                    "parameters": {
                        "type": "object",
                        "$defs": {
                            "mode": {"enum": ["fast", "thorough"]},
                        },
                        "properties": {
                            "mode": {"$ref": "#/$defs/mode"},
                        },
                    },
                },
            }
        ],
    }

    compiled = profile_for("kimi_code").compile_request(
        source,
        model_name="kimi-for-coding",
        wire_protocol="chat_completions",
        reasoning=ReasoningRequest(enabled=True, effort="high"),
    )

    parameters = compiled["tools"][0]["function"]["parameters"]
    assert parameters == {
        "type": "object",
        "properties": {
            "mode": {"enum": ["fast", "thorough"], "type": "string"},
        },
    }
    assert "content" not in compiled["messages"][0]
    assert "$defs" in source["tools"][0]["function"]["parameters"]


def test_kimi_k3_maps_medium_effort_to_supported_high_tier() -> None:
    compiled = profile_for("kimi_code").compile_request(
        {"model": "openai/k3", "messages": [], "max_tokens": 100},
        model_name="k3",
        wire_protocol="chat_completions",
        reasoning=ReasoningRequest(enabled=True, effort="medium"),
    )

    assert compiled["extra_body"]["thinking"] == {
        "type": "enabled",
        "effort": "high",
    }


@pytest.mark.parametrize(
    ("provider_kind", "model_name", "expected_path", "expected_value"),
    [
        ("openai", "gpt-5", ("reasoning_effort",), "high"),
        ("anthropic", "claude-sonnet-4-6", ("reasoning_effort",), "high"),
        (
            "openrouter",
            "anthropic/claude-sonnet-4-6",
            ("reasoning", "effort"),
            "high",
        ),
        ("fireworks", "accounts/fireworks/models/gpt-oss-120b", ("reasoning_effort",), "high"),
        ("qwen", "qwen3-max", ("extra_body", "enable_thinking"), True),
        ("deepseek", "deepseek-reasoner", ("thinking", "type"), "enabled"),
        ("xai", "grok-4.5", ("reasoning_effort",), "high"),
        ("zai", "glm-4.7", ("extra_body", "thinking", "type"), "enabled"),
        ("kimi_code", "kimi-for-coding", ("extra_body", "thinking", "type"), "enabled"),
        ("minimax", "MiniMax-M3", ("extra_body", "reasoning_split"), True),
        ("gemini", "gemini-3-pro-preview", ("reasoning_effort",), "high"),
    ],
)
def test_phase_one_profiles_compile_reasoning_controls(
    provider_kind: str,
    model_name: str,
    expected_path: tuple[str, ...],
    expected_value: object,
) -> None:
    compiled = profile_for(provider_kind).compile_request(
        {"model": model_name, "messages": [], "max_tokens": 100},
        model_name=model_name,
        wire_protocol="chat_completions",
        reasoning=ReasoningRequest(enabled=True, effort="high"),
    )

    value: object = compiled
    for part in expected_path:
        assert isinstance(value, dict)
        value = value[part]
    assert value == expected_value


def test_huggingface_profile_omits_unverified_universal_reasoning_control() -> None:
    compiled = profile_for("huggingface").compile_request(
        {"model": "MiniMaxAI/MiniMax-M3", "messages": [], "max_tokens": 100},
        model_name="MiniMaxAI/MiniMax-M3",
        wire_protocol="chat_completions",
        reasoning=ReasoningRequest(enabled=True, effort="high"),
    )

    assert "reasoning_effort" not in compiled
    assert "thinking" not in compiled


def test_qwen_profile_omits_qwen_controls_for_heterogeneous_dashscope_model() -> None:
    compiled = profile_for("qwen").compile_request(
        {"model": "deepseek-v4-pro", "messages": [], "max_tokens": 100},
        model_name="deepseek-v4-pro",
        wire_protocol="chat_completions",
        reasoning=ReasoningRequest(enabled=True, effort="high"),
    )

    assert "reasoning_effort" not in compiled
    assert "extra_body" not in compiled
