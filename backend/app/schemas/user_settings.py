from __future__ import annotations

from pydantic import BaseModel


class UserSettingsRead(BaseModel):
    """Returned to frontend — API keys are MASKED."""

    provider_credentials: dict[str, dict[str, str]]
    selected_provider: str
    selected_model: str
    configured_providers: list[str]


class UserSettingsUpdate(BaseModel):
    """Partial update. Merges into existing provider_credentials."""

    provider_credentials: dict[str, dict[str, str]] | None = None
    selected_provider: str | None = None
    selected_model: str | None = None


class ProviderTestResult(BaseModel):
    provider: str
    success: bool
    error: str | None = None
    model: str | None = None


class ModelInfo(BaseModel):
    id: str
    name: str
    context_window: int | None = None


class ProviderModels(BaseModel):
    provider: str
    label: str = ""
    models: list[ModelInfo]
