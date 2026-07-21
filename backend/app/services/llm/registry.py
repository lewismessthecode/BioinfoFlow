from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import Literal

from app.models.llm import LlmWireProtocol


CatalogStrategy = Literal[
    "bundled",
    "openai_models",
    "anthropic_models",
    "openrouter_models",
    "gemini_models",
]


@dataclass(frozen=True)
class ApiKeyAuthSpec:
    env_vars: tuple[str, ...]
    header: str = "Authorization"
    scheme: str = "Bearer"


@dataclass(frozen=True)
class EndpointSpec:
    default_base_url: str
    base_url_supported: bool = False
    alternative_base_urls: tuple[str, ...] = ()
    env_vars: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeSpec:
    litellm_model_prefix: str
    supported_wire_protocols: tuple[str, ...] = (LlmWireProtocol.CHAT_COMPLETIONS,)
    default_wire_protocol: str = LlmWireProtocol.CHAT_COMPLETIONS
    responses_litellm_model_prefix: str | None = None


@dataclass(frozen=True)
class CatalogSpec:
    strategy: CatalogStrategy
    path: str | None = None
    public: bool = False


@dataclass(frozen=True)
class ModelSpec:
    id: str
    name: str
    context_length: int | None = None
    max_output_tokens: int | None = None
    supports_tools: bool = True
    supports_streaming: bool = True
    supports_vision: bool = False
    supports_json_schema: bool = True
    supports_reasoning: bool = False
    output_modalities: tuple[str, ...] = ("text",)


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    name: str
    kind: str
    docs_url: str
    auth: ApiKeyAuthSpec
    endpoint: EndpointSpec
    runtime: RuntimeSpec
    catalog: CatalogSpec
    bundled_models: tuple[ModelSpec, ...] = ()


_SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        id="openai",
        name="OpenAI",
        kind="openai",
        docs_url="https://platform.openai.com/api-keys",
        auth=ApiKeyAuthSpec(("OPENAI_API_KEY",)),
        endpoint=EndpointSpec(
            "https://api.openai.com/v1",
            env_vars=("OPENAI_BASE_URL",),
        ),
        runtime=RuntimeSpec(
            "",
            supported_wire_protocols=LlmWireProtocol.ALL,
            responses_litellm_model_prefix="openai/",
        ),
        catalog=CatalogSpec("openai_models", "/models"),
    ),
    ProviderSpec(
        id="anthropic",
        name="Anthropic",
        kind="anthropic",
        docs_url="https://console.anthropic.com/settings/keys",
        auth=ApiKeyAuthSpec(
            ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
            header="x-api-key",
            scheme="",
        ),
        endpoint=EndpointSpec(
            "https://api.anthropic.com",
            env_vars=("ANTHROPIC_BASE_URL", "ANTHROPIC_API_BASE"),
        ),
        runtime=RuntimeSpec("anthropic/"),
        catalog=CatalogSpec("anthropic_models", "/v1/models"),
    ),
    ProviderSpec(
        id="openrouter",
        name="OpenRouter",
        kind="openrouter",
        docs_url="https://openrouter.ai/settings/keys",
        auth=ApiKeyAuthSpec(("OPENROUTER_API_KEY",)),
        endpoint=EndpointSpec("https://openrouter.ai/api/v1"),
        runtime=RuntimeSpec("openrouter/"),
        catalog=CatalogSpec("openrouter_models", "/models", public=True),
    ),
    ProviderSpec(
        id="fireworks",
        name="Fireworks AI",
        kind="fireworks",
        docs_url="https://fireworks.ai/account/api-keys",
        auth=ApiKeyAuthSpec(("FIREWORKS_API_KEY", "FIREWORKSAI_API_KEY")),
        endpoint=EndpointSpec("https://api.fireworks.ai/inference/v1"),
        runtime=RuntimeSpec("fireworks_ai/"),
        catalog=CatalogSpec("openai_models", "/models"),
    ),
    ProviderSpec(
        id="qwen",
        name="Qwen",
        kind="qwen",
        docs_url="https://bailian.console.aliyun.com/",
        auth=ApiKeyAuthSpec(("DASHSCOPE_API_KEY", "QWEN_API_KEY")),
        endpoint=EndpointSpec(
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            base_url_supported=True,
            alternative_base_urls=(
                "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            ),
        ),
        runtime=RuntimeSpec("openai/"),
        catalog=CatalogSpec("openai_models", "/models"),
    ),
    ProviderSpec(
        id="deepseek",
        name="DeepSeek",
        kind="deepseek",
        docs_url="https://platform.deepseek.com/api_keys",
        auth=ApiKeyAuthSpec(("DEEPSEEK_API_KEY",)),
        endpoint=EndpointSpec("https://api.deepseek.com/v1"),
        runtime=RuntimeSpec("deepseek/"),
        catalog=CatalogSpec("openai_models", "/models"),
    ),
    ProviderSpec(
        id="xai",
        name="xAI",
        kind="xai",
        docs_url="https://console.x.ai/",
        auth=ApiKeyAuthSpec(("XAI_API_KEY", "GROK_API_KEY")),
        endpoint=EndpointSpec("https://api.x.ai/v1"),
        runtime=RuntimeSpec("xai/"),
        catalog=CatalogSpec("openai_models", "/models"),
    ),
    ProviderSpec(
        id="zai",
        name="Z.AI",
        kind="zai",
        docs_url="https://z.ai/manage-apikey/apikey-list",
        auth=ApiKeyAuthSpec(("ZAI_API_KEY", "ZHIPUAI_API_KEY")),
        endpoint=EndpointSpec("https://api.z.ai/api/paas/v4"),
        runtime=RuntimeSpec("zai/"),
        catalog=CatalogSpec("openai_models", "/models"),
    ),
    ProviderSpec(
        id="kimi-code",
        name="Kimi Code",
        kind="kimi_code",
        docs_url="https://www.kimi.com/code/console",
        auth=ApiKeyAuthSpec(("KIMI_API_KEY", "KIMI_CODE_API_KEY")),
        endpoint=EndpointSpec("https://api.kimi.com/coding/v1"),
        runtime=RuntimeSpec("openai/"),
        catalog=CatalogSpec("bundled"),
        bundled_models=(
            ModelSpec("k3", "Kimi K3", supports_reasoning=True),
            ModelSpec(
                "kimi-for-coding",
                "Kimi for Coding",
                supports_reasoning=True,
            ),
            ModelSpec(
                "kimi-for-coding-highspeed",
                "Kimi for Coding Highspeed",
                supports_reasoning=True,
            ),
        ),
    ),
    ProviderSpec(
        id="minimax",
        name="MiniMax",
        kind="minimax",
        docs_url="https://platform.minimax.io/user-center/basic-information/interface-key",
        auth=ApiKeyAuthSpec(("MINIMAX_API_KEY",)),
        endpoint=EndpointSpec("https://api.minimax.io/v1"),
        runtime=RuntimeSpec("minimax/"),
        catalog=CatalogSpec("bundled"),
    ),
    ProviderSpec(
        id="huggingface",
        name="Hugging Face",
        kind="huggingface",
        docs_url="https://huggingface.co/settings/tokens",
        auth=ApiKeyAuthSpec(("HUGGINGFACE_API_KEY", "HF_TOKEN")),
        endpoint=EndpointSpec("https://router.huggingface.co/v1"),
        runtime=RuntimeSpec("huggingface/"),
        catalog=CatalogSpec("bundled"),
    ),
    ProviderSpec(
        id="gemini",
        name="Gemini",
        kind="gemini",
        docs_url="https://aistudio.google.com/apikey",
        auth=ApiKeyAuthSpec(("GEMINI_API_KEY",), header="x-goog-api-key", scheme=""),
        endpoint=EndpointSpec("https://generativelanguage.googleapis.com"),
        runtime=RuntimeSpec("gemini/"),
        catalog=CatalogSpec("gemini_models", "/v1beta/models"),
    ),
)

_BY_ID = {spec.id: spec for spec in _SPECS}
_BY_KIND = {spec.kind: spec for spec in _SPECS}

if len(_BY_ID) != len(_SPECS) or len(_BY_KIND) != len(_SPECS):
    raise RuntimeError("Duplicate provider id or kind in LLM provider registry")


def list_provider_specs() -> list[ProviderSpec]:
    snapshot = load_catalog_snapshot()
    return [
        replace(spec, bundled_models=snapshot.get(spec.id, spec.bundled_models))
        for spec in _SPECS
    ]


def get_provider_spec(provider_id: str) -> ProviderSpec:
    try:
        spec = _BY_ID[provider_id]
    except KeyError as exc:
        raise ValueError(f"Unknown LLM provider spec: {provider_id}") from exc
    return replace(
        spec,
        bundled_models=load_catalog_snapshot().get(provider_id, spec.bundled_models),
    )


def provider_spec_for_kind(kind: str) -> ProviderSpec | None:
    spec = _BY_KIND.get(kind)
    return get_provider_spec(spec.id) if spec is not None else None


def load_catalog_snapshot() -> dict[str, tuple[ModelSpec, ...]]:
    path = Path(__file__).with_name("catalog_snapshot.json")
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        provider_id: tuple(
            ModelSpec(
                id=model["id"],
                name=model["name"],
                context_length=model.get("context_length"),
                max_output_tokens=model.get("max_output_tokens"),
                supports_tools=model["supports_tools"],
                supports_streaming=model.get("supports_streaming", True),
                supports_vision=model.get("supports_vision", False),
                supports_json_schema=model.get("supports_json_schema", False),
                supports_reasoning=model.get("supports_reasoning", False),
                output_modalities=tuple(model["output_modalities"]),
            )
            for model in models
        )
        for provider_id, models in payload["providers"].items()
    }
