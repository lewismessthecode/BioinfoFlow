from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.models.llm import LlmWireProtocol


ProviderDiscovery = Literal[
    "static",
    "openai_models",
    "ollama_tags",
    "anthropic_models",
    "gemini_models",
]


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


@dataclass(frozen=True)
class ProviderTemplate:
    id: str
    name: str
    kind: str
    docs_url: str
    discovery: ProviderDiscovery
    litellm_prefix: str = ""
    default_base_url: str | None = None
    env_api_key_vars: tuple[str, ...] = ()
    env_base_url_vars: tuple[str, ...] = ()
    env_model_vars: tuple[str, ...] = ()
    env_wire_protocol_vars: tuple[str, ...] = ()
    supported_wire_protocols: tuple[str, ...] = (
        LlmWireProtocol.CHAT_COMPLETIONS,
    )
    default_wire_protocol: str = LlmWireProtocol.CHAT_COMPLETIONS
    api_key_required: bool = True
    base_url_required: bool = False
    model_id_supported: bool = False
    models: tuple[ModelTemplate, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for wire_protocol in self.supported_wire_protocols:
            LlmWireProtocol.validate_for_kind(self.kind, wire_protocol)
        if self.default_wire_protocol not in self.supported_wire_protocols:
            raise ValueError(
                f"Default wire protocol {self.default_wire_protocol!r} is not supported "
                f"by provider template {self.id!r}."
            )

    def validate_wire_protocol(self, wire_protocol: str) -> str:
        LlmWireProtocol.validate_for_kind(self.kind, wire_protocol)
        if wire_protocol not in self.supported_wire_protocols:
            raise ValueError(
                f"Provider template {self.id!r} does not support wire protocol "
                f"{wire_protocol!r}."
            )
        return wire_protocol

    def fields(self) -> list[ProviderFieldTemplate]:
        fields: list[ProviderFieldTemplate] = []
        if self.base_url_required:
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
    ),
    ProviderTemplate(
        id="anthropic",
        name="Anthropic",
        kind="anthropic",
        docs_url="https://console.anthropic.com/settings/keys",
        discovery="anthropic_models",
        litellm_prefix="anthropic/",
        default_base_url="https://api.anthropic.com",
        env_api_key_vars=("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
    ),
    ProviderTemplate(
        id="gemini",
        name="Gemini",
        kind="gemini",
        docs_url="https://aistudio.google.com/apikey",
        discovery="gemini_models",
        litellm_prefix="gemini/",
        default_base_url="https://generativelanguage.googleapis.com",
        env_api_key_vars=("GEMINI_API_KEY",),
    ),
    ProviderTemplate(
        id="grok",
        name="Grok",
        kind="grok",
        docs_url="https://console.x.ai/",
        discovery="openai_models",
        litellm_prefix="xai/",
        default_base_url="https://api.x.ai/v1",
        env_api_key_vars=("XAI_API_KEY", "GROK_API_KEY"),
    ),
    ProviderTemplate(
        id="groq",
        name="Groq",
        kind="groq",
        docs_url="https://console.groq.com/keys",
        discovery="openai_models",
        litellm_prefix="groq/",
        default_base_url="https://api.groq.com/openai/v1",
        env_api_key_vars=("GROQ_API_KEY",),
    ),
    ProviderTemplate(
        id="deepseek",
        name="DeepSeek",
        kind="deepseek",
        docs_url="https://platform.deepseek.com/api_keys",
        discovery="openai_models",
        litellm_prefix="deepseek/",
        default_base_url="https://api.deepseek.com/v1",
        env_api_key_vars=("DEEPSEEK_API_KEY",),
    ),
    ProviderTemplate(
        id="openrouter",
        name="OpenRouter",
        kind="openrouter",
        docs_url="https://openrouter.ai/settings/keys",
        discovery="openai_models",
        litellm_prefix="openrouter/",
        default_base_url="https://openrouter.ai/api/v1",
        env_api_key_vars=("OPENROUTER_API_KEY",),
        model_id_supported=True,
    ),
    ProviderTemplate(
        id="ollama",
        name="Ollama",
        kind="ollama",
        docs_url="https://ollama.com/download",
        discovery="ollama_tags",
        litellm_prefix="ollama_chat/",
        default_base_url="http://localhost:11434",
        env_base_url_vars=("OLLAMA_BASE_URL",),
        api_key_required=False,
        base_url_required=True,
        model_id_supported=True,
    ),
    ProviderTemplate(
        id="vllm",
        name="vLLM",
        kind="vllm",
        docs_url="https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html",
        discovery="openai_models",
        litellm_prefix="openai/",
        default_base_url="http://localhost:8000/v1",
        env_api_key_vars=("VLLM_API_KEY",),
        env_base_url_vars=("VLLM_BASE_URL",),
        env_model_vars=("VLLM_MODEL",),
        api_key_required=False,
        base_url_required=True,
        model_id_supported=True,
    ),
    ProviderTemplate(
        id="openai-compatible",
        name="OpenAI Compatible",
        kind="openai_compatible",
        docs_url="https://platform.openai.com/docs/api-reference",
        discovery="openai_models",
        litellm_prefix="openai/",
        default_base_url="https://api.example.com/v1",
        env_api_key_vars=("OPENAI_COMPATIBLE_API_KEY",),
        env_base_url_vars=("OPENAI_COMPATIBLE_BASE_URL",),
        env_model_vars=("OPENAI_COMPATIBLE_MODEL",),
        env_wire_protocol_vars=("OPENAI_COMPATIBLE_WIRE_PROTOCOL",),
        supported_wire_protocols=LlmWireProtocol.ALL,
        api_key_required=False,
        base_url_required=True,
        model_id_supported=True,
    ),
)

_TEMPLATES_BY_ID = {template.id: template for template in PROVIDER_TEMPLATES}
_TEMPLATES_BY_KIND = {template.kind: template for template in PROVIDER_TEMPLATES}


def list_provider_templates() -> list[ProviderTemplate]:
    return list(PROVIDER_TEMPLATES)


def get_provider_template(template_id: str) -> ProviderTemplate | None:
    return _TEMPLATES_BY_ID.get(template_id)


def provider_template_for_kind(kind: str) -> ProviderTemplate | None:
    return _TEMPLATES_BY_KIND.get(kind)


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


def normalize_provider_base_url(kind: str, base_url: str | None) -> str | None:
    if not base_url:
        return None
    if kind == "ollama":
        return normalize_ollama_base_url(base_url)
    if kind in ("anthropic", "gemini"):
        # These providers use native list endpoints (/v1/models, /v1beta/models)
        # appended at discovery time, so keep the host root intact.
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
) -> str:
    template = None
    if provider_metadata:
        template_id = str(provider_metadata.get("providerTemplate") or "")
        template = get_provider_template(template_id) if template_id else None
    template = template or provider_template_for_kind(provider_kind)
    prefix = template.litellm_prefix if template else ""
    if prefix and model.startswith(prefix):
        return model
    return f"{prefix}{model}"
