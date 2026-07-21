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


@pytest.mark.parametrize(
    ("provider_kind", "model_name", "expected"),
    [
        ("openai", "gpt-5", {"reasoning_effort": "high"}),
        ("deepseek", "deepseek-chat", {"thinking": {"type": "enabled"}}),
        ("zai", "glm-4.7", {"thinking": {"type": "enabled"}}),
        ("kimi_code", "kimi-for-coding", {"thinking": {"type": "enabled"}}),
        ("minimax", "MiniMax-M3", {"reasoning_split": True}),
        ("gemini", "gemini-3-pro", {"reasoning_effort": "high"}),
        ("openrouter", "anthropic/claude-sonnet-5", {"reasoning": {"effort": "high"}}),
    ],
)
def test_provider_profiles_translate_normalized_reasoning(
    provider_kind: str,
    model_name: str,
    expected: dict,
) -> None:
    options = profile_for(provider_kind).invocation_options(
        model_name,
        ReasoningRequest(enabled=True, effort="high"),
    )

    assert options == expected


def test_disabled_reasoning_produces_no_provider_options() -> None:
    assert profile_for("kimi_code").invocation_options(
        "kimi-for-coding",
        ReasoningRequest(enabled=False),
    ) == {}


def test_kimi_reasoning_never_sends_conflicting_controls() -> None:
    options = profile_for("kimi_code").invocation_options(
        "kimi-for-coding",
        ReasoningRequest(enabled=True, effort="high"),
    )

    assert "thinking" in options
    assert "reasoning_effort" not in options
