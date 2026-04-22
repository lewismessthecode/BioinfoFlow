from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class UserSettings(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "user_settings"

    user_id: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False, index=True
    )

    # --- Unified credential storage (JSON blob) ---
    # Structure: {"anthropic": {"api_key": "sk-..."}, "ollama": {"base_url": "..."}}
    provider_credentials: Mapped[str] = mapped_column(Text, default="{}")

    # --- Legacy per-provider columns (kept for rollback safety) ---
    anthropic_api_key: Mapped[str] = mapped_column(String(500), default="")
    openai_api_key: Mapped[str] = mapped_column(String(500), default="")
    openai_base_url: Mapped[str] = mapped_column(String(500), default="")
    gemini_api_key: Mapped[str] = mapped_column(String(500), default="")
    openrouter_api_key: Mapped[str] = mapped_column(String(500), default="")
    ollama_base_url: Mapped[str] = mapped_column(String(500), default="")
    ollama_model: Mapped[str] = mapped_column(String(100), default="")
    deepseek_api_key: Mapped[str] = mapped_column(String(500), default="")
    qwen_api_key: Mapped[str] = mapped_column(String(500), default="")
    kimi_api_key: Mapped[str] = mapped_column(String(500), default="")
    minimax_api_key: Mapped[str] = mapped_column(String(500), default="")

    selected_provider: Mapped[str] = mapped_column(String(50), default="auto")
    selected_model: Mapped[str] = mapped_column(String(100), default="")
