from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Literal

from app.models.llm import LlmWireProtocol


ProviderDiscovery = Literal[
    "static",
    "openai_models",
    "ollama_tags",
    "anthropic_models",
    "gemini_models",
    "cohere_models",
]

_PROVIDER_KIND_PATTERN = re.compile(
    r"^[a-z][a-z0-9]*(?:[_-][a-z0-9]+)*$"
)


def validate_provider_kind(kind: str) -> str:
    if (
        not isinstance(kind, str)
        or kind != kind.strip()
        or len(kind) > 40
        or _PROVIDER_KIND_PATTERN.fullmatch(kind) is None
    ):
        raise ValueError(
            "Invalid LLM provider kind; use 1-40 lowercase letters, numbers, "
            "underscores, or hyphens, starting with a letter."
        )
    return kind


@dataclass(frozen=True, kw_only=True)
class ProviderAdapter:
    kind: str
    supported_wire_protocols: tuple[str, ...] = (
        LlmWireProtocol.CHAT_COMPLETIONS,
    )
    default_wire_protocol: str = LlmWireProtocol.CHAT_COMPLETIONS
    litellm_model_prefix: str = ""
    responses_litellm_model_prefix: str | None = None

    def __post_init__(self) -> None:
        validate_provider_kind(self.kind)
        if not self.supported_wire_protocols:
            raise ValueError(
                f"Provider kind {self.kind!r} must support at least one wire protocol."
            )
        for wire_protocol in self.supported_wire_protocols:
            LlmWireProtocol.validate(wire_protocol)
        if self.default_wire_protocol not in self.supported_wire_protocols:
            raise ValueError(
                f"Default wire protocol {self.default_wire_protocol!r} is not supported "
                f"by provider kind {self.kind!r}."
            )

    def validate_wire_protocol(self, wire_protocol: str) -> str:
        LlmWireProtocol.validate(wire_protocol)
        if wire_protocol not in self.supported_wire_protocols:
            raise ValueError(
                f"Provider kind {self.kind!r} does not support wire protocol "
                f"{wire_protocol!r}."
            )
        return wire_protocol

    def route_model_name(self, model_name: str, wire_protocol: str) -> str:
        self.validate_wire_protocol(wire_protocol)
        prefix = self.litellm_model_prefix
        if (
            wire_protocol == LlmWireProtocol.RESPONSES
            and self.responses_litellm_model_prefix is not None
        ):
            prefix = self.responses_litellm_model_prefix
        if prefix and model_name.startswith(prefix):
            return model_name
        return f"{prefix}{model_name}"


@dataclass(frozen=True)
class ProviderFieldTemplate:
    name: str
    label: str
    secret: bool = False
    required: bool = False
    placeholder: str = ""
    default: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "label": self.label,
            "secret": self.secret,
            "required": self.required,
            "placeholder": self.placeholder,
        }
        if self.default is not None:
            payload["default"] = self.default
        return payload


@dataclass(frozen=True)
class ModelTemplate:
    id: str
    name: str
    context_length: int | None = None
    max_output_tokens: int | None = None
    supports_tools: bool = True
    supports_streaming: bool = True
    supports_vision: bool = False
    supports_json_schema: bool = True
    supports_reasoning: bool = False


@dataclass(frozen=True, kw_only=True)
class ProviderTemplate(ProviderAdapter):
    id: str
    name: str
    docs_url: str
    discovery: ProviderDiscovery
    default_base_url: str | None = None
    env_api_key_vars: tuple[str, ...] = ()
    env_base_url_vars: tuple[str, ...] = ()
    env_allow_insecure_http_vars: tuple[str, ...] = ()
    env_model_vars: tuple[str, ...] = ()
    env_wire_protocol_vars: tuple[str, ...] = ()
    api_key_required: bool = True
    base_url_supported: bool = False
    base_url_required: bool = False
    model_id_supported: bool = False
    models: tuple[ModelTemplate, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.id.strip():
            raise ValueError("Provider template id cannot be empty.")

    def validate_wire_protocol(self, wire_protocol: str) -> str:
        return super().validate_wire_protocol(wire_protocol)

    def fields(self) -> list[ProviderFieldTemplate]:
        fields: list[ProviderFieldTemplate] = []
        if self.base_url_supported or self.base_url_required:
            fields.append(
                ProviderFieldTemplate(
                    name="base_url",
                    label="Endpoint",
                    required=self.base_url_required,
                    placeholder="Provider endpoint",
                    default=self.default_base_url,
                )
            )
        if self.api_key_required or self.env_api_key_vars:
            fields.append(
                ProviderFieldTemplate(
                    name="api_key",
                    label="API key",
                    secret=True,
                    required=self.api_key_required,
                    placeholder="Paste API key",
                )
            )
        if self.model_id_supported:
            fields.append(
                ProviderFieldTemplate(
                    name="model_id",
                    label="Model ID",
                    required=False,
                    placeholder="Model ID",
                )
            )
        return fields

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "docs_url": self.docs_url,
            "discovery": self.discovery,
            "default_base_url": self.default_base_url,
            "supported_wire_protocols": list(self.supported_wire_protocols),
            "default_wire_protocol": self.default_wire_protocol,
            "fields": [field.as_dict() for field in self.fields()],
            "models": [
                {
                    "id": model.id,
                    "name": model.name,
                    "context_length": model.context_length,
                    "max_output_tokens": model.max_output_tokens,
                    "supports_tools": model.supports_tools,
                    "supports_streaming": model.supports_streaming,
                    "supports_vision": model.supports_vision,
                    "supports_json_schema": model.supports_json_schema,
                    "supports_reasoning": model.supports_reasoning,
                }
                for model in self.models
            ],
        }


PROVIDER_TEMPLATES: tuple[ProviderTemplate, ...] = (
    ProviderTemplate(
        id="openai",
        name="OpenAI",
        kind="openai",
        docs_url="https://platform.openai.com/api-keys",
        discovery="openai_models",
        default_base_url="https://api.openai.com/v1",
        env_api_key_vars=("OPENAI_API_KEY",),
        env_base_url_vars=("OPENAI_BASE_URL",),
        env_wire_protocol_vars=("OPENAI_WIRE_PROTOCOL",),
        supported_wire_protocols=LlmWireProtocol.ALL,
        responses_litellm_model_prefix="openai/",
    ),
    ProviderTemplate(
        id="anthropic",
        name="Anthropic",
        kind="anthropic",
        docs_url="https://console.anthropic.com/settings/keys",
        discovery="anthropic_models",
        default_base_url="https://api.anthropic.com",
        env_api_key_vars=("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
        env_base_url_vars=("ANTHROPIC_BASE_URL", "ANTHROPIC_API_BASE"),
        env_model_vars=("ANTHROPIC_MODEL",),
        litellm_model_prefix="anthropic/",
    ),
    ProviderTemplate(
        id="gemini",
        name="Gemini",
        kind="gemini",
        docs_url="https://aistudio.google.com/apikey",
        discovery="gemini_models",
        default_base_url="https://generativelanguage.googleapis.com",
        env_api_key_vars=("GEMINI_API_KEY",),
        litellm_model_prefix="gemini/",
    ),
    ProviderTemplate(
        id="grok",
        name="Grok",
        kind="grok",
        docs_url="https://console.x.ai/",
        discovery="openai_models",
        default_base_url="https://api.x.ai/v1",
        env_api_key_vars=("XAI_API_KEY", "GROK_API_KEY"),
        litellm_model_prefix="xai/",
    ),
    ProviderTemplate(
        id="groq",
        name="Groq",
        kind="groq",
        docs_url="https://console.groq.com/keys",
        discovery="openai_models",
        default_base_url="https://api.groq.com/openai/v1",
        env_api_key_vars=("GROQ_API_KEY",),
        litellm_model_prefix="groq/",
    ),
    ProviderTemplate(
        id="deepseek",
        name="DeepSeek",
        kind="deepseek",
        docs_url="https://platform.deepseek.com/api_keys",
        discovery="openai_models",
        default_base_url="https://api.deepseek.com/v1",
        env_api_key_vars=("DEEPSEEK_API_KEY",),
        litellm_model_prefix="deepseek/",
    ),
    ProviderTemplate(
        id="openrouter",
        name="OpenRouter",
        kind="openrouter",
        docs_url="https://openrouter.ai/settings/keys",
        discovery="openai_models",
        default_base_url="https://openrouter.ai/api/v1",
        env_api_key_vars=("OPENROUTER_API_KEY",),
        litellm_model_prefix="openrouter/",
    ),
    ProviderTemplate(
        id="kimi",
        name="Kimi",
        kind="kimi",
        docs_url="https://platform.moonshot.cn/console/api-keys",
        discovery="openai_models",
        default_base_url="https://api.moonshot.cn/v1",
        env_api_key_vars=("KIMI_API_KEY", "MOONSHOT_API_KEY"),
        litellm_model_prefix="openai/",
    ),
    ProviderTemplate(
        id="qwen",
        name="Qwen",
        kind="qwen",
        docs_url="https://bailian.console.aliyun.com/",
        discovery="openai_models",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        env_api_key_vars=("DASHSCOPE_API_KEY", "QWEN_API_KEY"),
        litellm_model_prefix="openai/",
    ),
    ProviderTemplate(
        id="mistral",
        name="Mistral",
        kind="mistral",
        docs_url="https://console.mistral.ai/api-keys/",
        discovery="openai_models",
        default_base_url="https://api.mistral.ai/v1",
        env_api_key_vars=("MISTRAL_API_KEY",),
        litellm_model_prefix="openai/",
    ),
    ProviderTemplate(
        id="cohere",
        name="Cohere",
        kind="cohere",
        docs_url="https://dashboard.cohere.com/api-keys",
        discovery="cohere_models",
        default_base_url="https://api.cohere.ai/compatibility/v1",
        env_api_key_vars=("COHERE_API_KEY",),
        litellm_model_prefix="openai/",
        metadata={"modelDiscoveryBaseUrl": "https://api.cohere.ai/v2"},
    ),
    ProviderTemplate(
        id="together",
        name="Together AI",
        kind="together",
        docs_url="https://api.together.ai/settings/api-keys",
        discovery="openai_models",
        default_base_url="https://api.together.xyz/v1",
        env_api_key_vars=("TOGETHER_API_KEY", "TOGETHERAI_API_KEY"),
        litellm_model_prefix="openai/",
    ),
    ProviderTemplate(
        id="fireworks",
        name="Fireworks AI",
        kind="fireworks",
        docs_url="https://fireworks.ai/account/api-keys",
        discovery="openai_models",
        default_base_url="https://api.fireworks.ai/inference/v1",
        env_api_key_vars=("FIREWORKS_API_KEY", "FIREWORKSAI_API_KEY"),
        litellm_model_prefix="openai/",
    ),
    ProviderTemplate(
        id="perplexity",
        name="Perplexity",
        kind="perplexity",
        docs_url="https://www.perplexity.ai/settings/api",
        discovery="openai_models",
        default_base_url="https://api.perplexity.ai",
        env_api_key_vars=("PERPLEXITY_API_KEY", "PPLX_API_KEY"),
        litellm_model_prefix="perplexity/",
        metadata={"preserveOpenAIBaseUrl": True},
    ),
    ProviderTemplate(
        id="ollama",
        name="Ollama",
        kind="ollama",
        docs_url="https://ollama.com/download",
        discovery="ollama_tags",
        default_base_url="http://localhost:11434",
        env_base_url_vars=("OLLAMA_BASE_URL",),
        api_key_required=False,
        base_url_required=True,
        model_id_supported=True,
        litellm_model_prefix="ollama_chat/",
    ),
    ProviderTemplate(
        id="vllm",
        name="vLLM",
        kind="vllm",
        docs_url="https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html",
        discovery="openai_models",
        default_base_url="http://localhost:8000/v1",
        env_api_key_vars=("VLLM_API_KEY",),
        env_base_url_vars=("VLLM_BASE_URL",),
        env_model_vars=("VLLM_MODEL",),
        api_key_required=False,
        base_url_required=True,
        model_id_supported=True,
        litellm_model_prefix="openai/",
    ),
    ProviderTemplate(
        id="openai-compatible",
        name="OpenAI Compatible",
        kind="openai_compatible",
        docs_url="https://platform.openai.com/docs/api-reference",
        discovery="openai_models",
        default_base_url="https://api.example.com/v1",
        env_api_key_vars=("OPENAI_COMPATIBLE_API_KEY",),
        env_base_url_vars=("OPENAI_COMPATIBLE_BASE_URL",),
        env_model_vars=("OPENAI_COMPATIBLE_MODEL",),
        env_wire_protocol_vars=("OPENAI_COMPATIBLE_WIRE_PROTOCOL",),
        supported_wire_protocols=LlmWireProtocol.ALL,
        litellm_model_prefix="openai/",
        api_key_required=False,
        base_url_required=True,
        model_id_supported=True,
    ),
)


class ProviderRegistry:
    def __init__(self, adapters: tuple[ProviderAdapter, ...]):
        self._adapters_by_kind: dict[str, ProviderAdapter] = {}
        self._templates_by_id: dict[str, ProviderTemplate] = {}
        for adapter in adapters:
            if adapter.kind in self._adapters_by_kind:
                raise ValueError(f"Duplicate LLM provider kind: {adapter.kind}")
            self._adapters_by_kind[adapter.kind] = adapter
            if isinstance(adapter, ProviderTemplate):
                if adapter.id in self._templates_by_id:
                    raise ValueError(f"Duplicate LLM provider template: {adapter.id}")
                self._templates_by_id[adapter.id] = adapter

    def list_templates(self) -> list[ProviderTemplate]:
        return list(self._templates_by_id.values())

    def get_template(self, template_id: str) -> ProviderTemplate | None:
        return self._templates_by_id.get(template_id)

    def adapter_for_kind(self, kind: str) -> ProviderAdapter | None:
        validate_provider_kind(kind)
        return self._adapters_by_kind.get(kind)

    def validate_configuration(
        self,
        kind: str,
        wire_protocol: str,
    ) -> tuple[str, str]:
        adapter = self.adapter_for_kind(kind)
        if adapter is None:
            raise ValueError(f"Unsupported LLM provider kind: {kind!r}.")
        return kind, adapter.validate_wire_protocol(wire_protocol)

    def route_model_name(
        self,
        kind: str,
        model_name: str,
        wire_protocol: str,
    ) -> str:
        adapter = self.adapter_for_kind(kind)
        if adapter is None:
            raise ValueError(f"Unsupported LLM provider kind: {kind!r}.")
        return adapter.route_model_name(model_name, wire_protocol)


_HEADLESS_PROVIDER_ADAPTERS: tuple[ProviderAdapter, ...] = (
    ProviderAdapter(kind="azure", litellm_model_prefix="azure/"),
    ProviderAdapter(kind="minimax"),
)

PROVIDER_REGISTRY = ProviderRegistry(
    (*PROVIDER_TEMPLATES, *_HEADLESS_PROVIDER_ADAPTERS)
)


def list_provider_templates() -> list[ProviderTemplate]:
    return PROVIDER_REGISTRY.list_templates()


def get_provider_template(template_id: str) -> ProviderTemplate | None:
    return PROVIDER_REGISTRY.get_template(template_id)


def provider_template_for_kind(kind: str) -> ProviderTemplate | None:
    adapter = PROVIDER_REGISTRY.adapter_for_kind(kind)
    return adapter if isinstance(adapter, ProviderTemplate) else None


def validate_provider_configuration(
    kind: str,
    wire_protocol: str,
) -> tuple[str, str]:
    return PROVIDER_REGISTRY.validate_configuration(kind, wire_protocol)


def route_provider_model_name(
    provider_kind: str,
    model_name: str,
    *,
    wire_protocol: str,
) -> str:
    return PROVIDER_REGISTRY.route_model_name(
        provider_kind,
        model_name,
        wire_protocol,
    )


def provider_template_for_provider(provider) -> ProviderTemplate | None:
    metadata = getattr(provider, "provider_metadata", None) or {}
    template_id = str(metadata.get("providerTemplate") or "").strip()
    if template_id:
        return get_provider_template(template_id)
    return provider_template_for_kind(str(getattr(provider, "kind", "") or ""))


def normalize_openai_compatible_base_url(
    base_url: str,
    *,
    prefer_loopback_ip: bool = False,
) -> str:
    normalized = (base_url or "").strip().rstrip("/")
    if not normalized:
        return normalized
    if prefer_loopback_ip:
        normalized = normalized.replace("http://localhost:", "http://127.0.0.1:", 1)
        normalized = normalized.replace("https://localhost:", "https://127.0.0.1:", 1)
    if not normalized.endswith("/v1"):
        normalized = f"{normalized}/v1"
    return normalized


def normalize_ollama_base_url(base_url: str) -> str:
    normalized = (base_url or "").strip().rstrip("/")
    if not normalized:
        return normalized
    normalized = normalized.replace("http://localhost:", "http://127.0.0.1:", 1)
    normalized = normalized.replace("https://localhost:", "https://127.0.0.1:", 1)
    if normalized.endswith("/v1"):
        normalized = normalized[:-3].rstrip("/")
    return normalized


def normalize_anthropic_base_url(base_url: str) -> str:
    normalized = (base_url or "").strip().rstrip("/")
    if not normalized:
        return normalized
    for suffix in ("/v1/messages", "/v1"):
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)].rstrip("/")
    return normalized


def normalize_provider_base_url(kind: str, base_url: str | None) -> str | None:
    if not base_url:
        return None
    if kind == "ollama":
        return normalize_ollama_base_url(base_url)
    if kind == "anthropic":
        return normalize_anthropic_base_url(base_url)
    if kind == "gemini":
        # These providers use native list endpoints (/v1/models, /v1beta/models)
        # appended at discovery time, so keep the host root intact.
        return base_url.strip().rstrip("/")
    template = provider_template_for_kind(kind)
    if template and template.metadata.get("preserveOpenAIBaseUrl") is True:
        return base_url.strip().rstrip("/")
    return normalize_openai_compatible_base_url(
        base_url,
        prefer_loopback_ip=kind == "vllm",
    )


def litellm_model_name(
    provider_kind: str,
    model: str,
    *,
    provider_metadata: dict[str, Any] | None = None,
    wire_protocol: str = LlmWireProtocol.CHAT_COMPLETIONS,
) -> str:
    template: ProviderTemplate | None = None
    if provider_metadata:
        template_id = str(provider_metadata.get("providerTemplate") or "")
        template = get_provider_template(template_id) if template_id else None
    return route_provider_model_name(
        template.kind if template else provider_kind,
        model,
        wire_protocol=wire_protocol,
    )
