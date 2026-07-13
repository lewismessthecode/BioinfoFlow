from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class LlmProviderScope:
    GLOBAL = "global"
    WORKSPACE = "workspace"
    USER = "user"


class LlmWireProtocol:
    CHAT_COMPLETIONS = "chat_completions"
    RESPONSES = "responses"

    ALL = (CHAT_COMPLETIONS, RESPONSES)

    @classmethod
    def validate(cls, wire_protocol: str) -> str:
        if wire_protocol not in cls.ALL:
            raise ValueError(f"Unknown LLM wire protocol: {wire_protocol}")
        return wire_protocol


class LlmCredentialSource:
    NONE = "none"
    ENV = "env"
    STORED = "stored"


class LlmProvider(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "llm_providers"
    __table_args__ = (
        UniqueConstraint("scope", "workspace_id", "user_id", "name", name="uq_llm_providers_scope_name"),
        CheckConstraint(
            "wire_protocol IN ('chat_completions', 'responses')",
            name="ck_llm_providers_wire_protocol",
        ),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    wire_protocol: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=LlmWireProtocol.CHAT_COMPLETIONS,
        server_default=LlmWireProtocol.CHAT_COMPLETIONS,
    )
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    api_key_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)
    scope: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=LlmProviderScope.USER,
        index=True,
    )
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_insecure_http: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    test_status: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    provider_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    workspace = relationship("Workspace")
    models = relationship(
        "LlmModel",
        back_populates="provider",
        cascade="all, delete-orphan",
    )
    credential = relationship(
        "LlmProviderCredential",
        back_populates="provider",
        cascade="all, delete-orphan",
        uselist=False,
    )


class LlmProviderCredential(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "llm_provider_credentials"
    __table_args__ = (
        UniqueConstraint("provider_id", name="uq_llm_provider_credentials_provider_id"),
    )

    provider_id: Mapped[str] = mapped_column(
        ForeignKey("llm_providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=LlmCredentialSource.NONE,
    )
    env_var_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    encrypted_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    masked_hint: Mapped[str | None] = mapped_column(String(120), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    provider = relationship("LlmProvider", back_populates="credential")


class LlmModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "llm_models"
    __table_args__ = (
        UniqueConstraint("provider_id", "model_id", name="uq_llm_models_provider_model"),
    )

    provider_id: Mapped[str] = mapped_column(
        ForeignKey("llm_providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    context_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    supports_tools: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_streaming: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supports_vision: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_json_schema: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_reasoning: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    default_temperature: Mapped[str | None] = mapped_column(String(20), nullable=True)
    default_top_p: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cost_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    provider = relationship("LlmProvider", back_populates="models")
    primary_profiles = relationship(
        "LlmModelProfile",
        back_populates="primary_model",
        foreign_keys="LlmModelProfile.primary_model_id",
    )


class LlmModelProfile(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "llm_model_profiles"
    __table_args__ = (
        UniqueConstraint("scope", "workspace_id", "user_id", "name", name="uq_llm_model_profiles_scope_name"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    task_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    primary_model_id: Mapped[str] = mapped_column(
        ForeignKey("llm_models.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    fallback_model_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    reasoning_budget: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prefer_streaming: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_thinking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_tools: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    cost_ceiling: Mapped[str | None] = mapped_column(String(40), nullable=True)
    routing_policy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    permission_overrides: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    scope: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=LlmProviderScope.USER,
        index=True,
    )
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    profile_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    primary_model = relationship(
        "LlmModel",
        back_populates="primary_profiles",
        foreign_keys=[primary_model_id],
    )
    workspace = relationship("Workspace")
