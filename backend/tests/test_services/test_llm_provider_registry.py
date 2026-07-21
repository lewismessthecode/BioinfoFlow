from app.services.llm.registry import get_provider_spec, list_provider_specs


EXPECTED_IDS = {
    "openai",
    "anthropic",
    "openrouter",
    "fireworks",
    "qwen",
    "deepseek",
    "xai",
    "zai",
    "kimi-code",
    "minimax",
    "huggingface",
    "gemini",
}


def test_primary_registry_contains_exact_phase_one_providers() -> None:
    specs = list_provider_specs()

    assert {spec.id for spec in specs} == EXPECTED_IDS
    assert len({spec.kind for spec in specs}) == len(specs)


def test_phase_one_provider_endpoints_match_official_api_roots() -> None:
    assert (
        get_provider_spec("openai").endpoint.default_base_url
        == "https://api.openai.com/v1"
    )
    assert (
        get_provider_spec("anthropic").endpoint.default_base_url
        == "https://api.anthropic.com"
    )
    assert (
        get_provider_spec("openrouter").endpoint.default_base_url
        == "https://openrouter.ai/api/v1"
    )
    assert (
        get_provider_spec("fireworks").endpoint.default_base_url
        == "https://api.fireworks.ai/inference/v1"
    )
    assert (
        get_provider_spec("qwen").endpoint.default_base_url
        == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    assert (
        get_provider_spec("deepseek").endpoint.default_base_url
        == "https://api.deepseek.com/v1"
    )
    assert get_provider_spec("xai").endpoint.default_base_url == "https://api.x.ai/v1"
    assert (
        get_provider_spec("zai").endpoint.default_base_url
        == "https://api.z.ai/api/paas/v4"
    )
    assert (
        get_provider_spec("kimi-code").endpoint.default_base_url
        == "https://api.kimi.com/coding/v1"
    )
    assert (
        get_provider_spec("minimax").endpoint.default_base_url
        == "https://api.minimax.io/v1"
    )
    assert (
        get_provider_spec("huggingface").endpoint.default_base_url
        == "https://router.huggingface.co/v1"
    )
    assert (
        get_provider_spec("gemini").endpoint.default_base_url
        == "https://generativelanguage.googleapis.com"
    )


def test_qwen_allows_international_endpoint_override() -> None:
    spec = get_provider_spec("qwen")

    assert spec.endpoint.base_url_supported is True
    assert (
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        in spec.endpoint.alternative_base_urls
    )


def test_kimi_code_has_only_official_coding_models() -> None:
    spec = get_provider_spec("kimi-code")

    assert [model.id for model in spec.bundled_models] == [
        "k3",
        "kimi-for-coding",
        "kimi-for-coding-highspeed",
    ]
    assert spec.endpoint.default_base_url == "https://api.kimi.com/coding/v1"


def test_removed_kimi_open_platform_templates_are_absent() -> None:
    ids = {spec.id for spec in list_provider_specs()}

    assert "kimi" not in ids
    assert "kimi-cn" not in ids
