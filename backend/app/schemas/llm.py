from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


ProviderKind = Literal[
    "openai",
    "anthropic",
    "gemini",
    "grok",
    "groq",
    "openrouter",
    "deepseek",
    "ollama",
    "vllm",
    "openai_compatible",
    "qwen",
    "kimi",
    "minimax",
]
ProviderScope = Literal["global", "workspace", "user"]
CredentialSource = Literal["none", "env", "stored"]


class LlmProviderCredentialUpdate(BaseModel):
    source: CredentialSource
    env_var_name: str | None = None
    secret: str | None = None


class LlmProviderCredentialRead(BaseModel):
    provider_id: UUID
    source: CredentialSource
    configured: bool
    available: bool
    env_var_name: str | None = None
    fingerprint: str | None = None
    masked_hint: str | None = None
    updated_at: datetime | None = None


class LlmProviderCreate(BaseModel):
    name: str
    kind: ProviderKind
    base_url: str | None = None
    api_key_ref: str | None = None
    scope: ProviderScope = "user"
    enabled: bool = True
    allow_insecure_http: bool = False
    metadata: dict | None = None


class LlmProviderUpdate(BaseModel):
    name: str | None = None
    kind: ProviderKind | None = None
    base_url: str | None = None
    api_key_ref: str | None = None
    scope: ProviderScope | None = None
    enabled: bool | None = None
    allow_insecure_http: bool | None = None
    metadata: dict | None = None


class LlmProviderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    kind: ProviderKind
    base_url: str | None = None
    api_key_ref: str | None = None
    scope: ProviderScope
    workspace_id: UUID | None = None
    user_id: str | None = None
    enabled: bool
    allow_insecure_http: bool = False
    test_status: dict | None = None
    metadata: dict | None = Field(default=None, validation_alias="provider_metadata")
    created_at: datetime
    updated_at: datetime


class LlmProviderTemplateFieldRead(BaseModel):
    name: str
    label: str
    secret: bool
    required: bool
    placeholder: str
    default: str | None = None


class LlmProviderTemplateModelRead(BaseModel):
    id: str
    name: str
    context_length: int | None = None
    max_output_tokens: int | None = None
    supports_tools: bool
    supports_streaming: bool
    supports_vision: bool
    supports_json_schema: bool
    supports_reasoning: bool


class LlmProviderTemplateRead(BaseModel):
    id: str
    name: str
    kind: ProviderKind
    docs_url: str
    discovery: Literal[
        "static",
        "openai_models",
        "ollama_tags",
        "anthropic_models",
        "gemini_models",
    ]
    default_base_url: str | None = None
    fields: list[LlmProviderTemplateFieldRead]
    models: list[LlmProviderTemplateModelRead]


class LlmProviderSetupRequest(BaseModel):
    template_id: str
    provider_id: UUID | None = None
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model_ids: list[str] | None = None
    discover: bool = False
    scope: ProviderScope = "user"
    enabled: bool = True
    allow_insecure_http: bool = False


class LlmModelCreate(BaseModel):
    provider_id: UUID
    model_id: str
    display_name: str
    context_length: int | None = None
    max_output_tokens: int | None = None
    supports_tools: bool = False
    supports_streaming: bool = True
    supports_vision: bool = False
    supports_json_schema: bool = False
    supports_reasoning: bool = False
    default_temperature: str | None = None
    default_top_p: str | None = None
    cost_metadata: dict | None = None
    metadata: dict | None = None


class LlmModelUpdate(BaseModel):
    model_id: str | None = None
    display_name: str | None = None
    context_length: int | None = None
    max_output_tokens: int | None = None
    supports_tools: bool | None = None
    supports_streaming: bool | None = None
    supports_vision: bool | None = None
    supports_json_schema: bool | None = None
    supports_reasoning: bool | None = None
    default_temperature: str | None = None
    default_top_p: str | None = None
    cost_metadata: dict | None = None
    metadata: dict | None = None


class LlmModelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider_id: UUID
    model_id: str
    display_name: str
    context_length: int | None = None
    max_output_tokens: int | None = None
    supports_tools: bool
    supports_streaming: bool
    supports_vision: bool
    supports_json_schema: bool
    supports_reasoning: bool
    default_temperature: str | None = None
    default_top_p: str | None = None
    cost_metadata: dict | None = None
    metadata: dict | None = Field(default=None, validation_alias="model_metadata")
    created_at: datetime
    updated_at: datetime


class LlmModelProfileCreate(BaseModel):
    name: str
    task_type: str
    primary_model_id: UUID
    fallback_model_ids: list[UUID] | None = None
    reasoning_budget: int | None = None
    max_tokens: int | None = None
    prefer_streaming: bool = True
    allow_thinking: bool = True
    allow_tools: bool = True
    cost_ceiling: str | None = None
    routing_policy: dict | None = None
    permission_overrides: dict | None = None
    scope: ProviderScope = "user"
    enabled: bool = True
    metadata: dict | None = None


class LlmModelProfileUpdate(BaseModel):
    name: str | None = None
    task_type: str | None = None
    primary_model_id: UUID | None = None
    fallback_model_ids: list[UUID] | None = None
    reasoning_budget: int | None = None
    max_tokens: int | None = None
    prefer_streaming: bool | None = None
    allow_thinking: bool | None = None
    allow_tools: bool | None = None
    cost_ceiling: str | None = None
    routing_policy: dict | None = None
    permission_overrides: dict | None = None
    scope: ProviderScope | None = None
    enabled: bool | None = None
    metadata: dict | None = None


class LlmModelProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    task_type: str
    primary_model_id: UUID
    fallback_model_ids: list[UUID] | None = None
    reasoning_budget: int | None = None
    max_tokens: int | None = None
    prefer_streaming: bool
    allow_thinking: bool
    allow_tools: bool
    cost_ceiling: str | None = None
    routing_policy: dict | None = None
    permission_overrides: dict | None = None
    scope: ProviderScope
    workspace_id: UUID | None = None
    user_id: str | None = None
    enabled: bool
    metadata: dict | None = Field(default=None, validation_alias="profile_metadata")
    created_at: datetime
    updated_at: datetime


class LlmProviderTestResult(BaseModel):
    provider_id: UUID
    success: bool
    model: str | None = None
    error: str | None = None
    latency_ms: int | None = None


class LlmConfigurationSummary(BaseModel):
    provider_count: int
    configured_provider_count: int
    available_provider_count: int = 0
    model_count: int
    profile_count: int


class LlmConfiguredProviderRead(LlmProviderRead):
    credential: LlmProviderCredentialRead


class LlmConfigurationRead(BaseModel):
    summary: LlmConfigurationSummary
    providers: list[LlmConfiguredProviderRead]
    models: list[LlmModelRead]
    profiles: list[LlmModelProfileRead]


class LlmProviderSetupResult(BaseModel):
    provider: LlmConfiguredProviderRead
    models: list[LlmModelRead]
    discovered: bool = False
