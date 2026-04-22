"""Tests for UserSettingsService — key masking, CRUD, model catalog."""

from __future__ import annotations

import pytest

import app.models  # noqa: F401
from app.services.user_settings_service import UserSettingsService, _mask_key


# ---------------------------------------------------------------------------
# _mask_key unit tests (pure function, no DB)
# ---------------------------------------------------------------------------


class TestMaskKey:
    def test_empty_string(self):
        assert _mask_key("") == ""

    def test_short_key(self):
        assert _mask_key("abcd") == "ab...cd"

    def test_exactly_8_chars(self):
        assert _mask_key("12345678") == "12...78"

    def test_long_key(self):
        assert _mask_key("sk-ant-api03-abcdefghijk") == "sk-a...hijk"

    def test_preserves_prefix_suffix(self):
        key = "sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        masked = _mask_key(key)
        assert masked.startswith("sk-a")
        assert masked.endswith(key[-4:])
        assert "..." in masked


# ---------------------------------------------------------------------------
# UserSettingsService integration tests (require DB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_settings_returns_defaults_when_empty(db_session):
    service = UserSettingsService(db_session)
    result = await service.get_settings("user-no-settings")

    assert result.provider_credentials == {}
    assert result.selected_provider == "auto"
    assert result.selected_model == ""
    assert result.configured_providers == []


@pytest.mark.asyncio
async def test_update_and_get_settings(db_session):
    from app.schemas.user_settings import UserSettingsUpdate

    service = UserSettingsService(db_session)
    user_id = "user-settings-test-1"

    await service.update_settings(
        user_id,
        UserSettingsUpdate(
            provider_credentials={"anthropic": {"api_key": "sk-ant-test-key-very-long-value"}},
            selected_provider="anthropic",
            selected_model="claude-sonnet-4-5",
        ),
    )

    result = await service.get_settings(user_id)
    assert result.selected_provider == "anthropic"
    assert result.selected_model == "claude-sonnet-4-5"
    assert "anthropic" in result.configured_providers
    # Key should be masked
    masked_key = result.provider_credentials["anthropic"]["api_key"]
    assert "..." in masked_key
    assert masked_key != "sk-ant-test-key-very-long-value"


@pytest.mark.asyncio
async def test_update_settings_upserts_existing(db_session):
    from app.schemas.user_settings import UserSettingsUpdate

    service = UserSettingsService(db_session)
    user_id = "user-settings-upsert"

    # Create initial settings
    await service.update_settings(
        user_id,
        UserSettingsUpdate(
            provider_credentials={"anthropic": {"api_key": "key1"}},
            selected_provider="anthropic",
        ),
    )

    # Update with new provider (partial merge — anthropic should persist)
    await service.update_settings(
        user_id,
        UserSettingsUpdate(
            provider_credentials={"openai": {"api_key": "key2"}},
            selected_provider="openai",
        ),
    )

    result = await service.get_settings(user_id)
    assert result.selected_provider == "openai"
    assert "anthropic" in result.configured_providers
    assert "openai" in result.configured_providers


@pytest.mark.asyncio
async def test_get_raw_key_returns_unmasked(db_session):
    from app.schemas.user_settings import UserSettingsUpdate

    service = UserSettingsService(db_session)
    user_id = "user-raw-key"
    raw_key = "sk-ant-api03-real-secret"

    await service.update_settings(
        user_id,
        UserSettingsUpdate(provider_credentials={"anthropic": {"api_key": raw_key}}),
    )

    assert await service.get_raw_key(user_id, "anthropic") == raw_key
    assert await service.get_raw_key(user_id, "openai") == ""
    assert await service.get_raw_key(user_id, "unknown") == ""


@pytest.mark.asyncio
async def test_get_raw_key_no_settings(db_session):
    service = UserSettingsService(db_session)
    assert await service.get_raw_key("nonexistent-user", "anthropic") == ""


@pytest.mark.asyncio
async def test_configured_providers_reflects_set_keys(db_session):
    from app.schemas.user_settings import UserSettingsUpdate

    service = UserSettingsService(db_session)
    user_id = "user-providers"

    await service.update_settings(
        user_id,
        UserSettingsUpdate(
            provider_credentials={
                "anthropic": {"api_key": "key-a"},
                "gemini": {"api_key": "key-g"},
            },
        ),
    )

    result = await service.get_settings(user_id)
    assert "anthropic" in result.configured_providers
    assert "gemini" in result.configured_providers
    assert "openai" not in result.configured_providers


@pytest.mark.asyncio
async def test_test_provider_no_settings(db_session):
    service = UserSettingsService(db_session)
    result = await service.test_provider("no-user", "anthropic")
    assert result.success is False
    assert "No settings" in result.error


@pytest.mark.asyncio
async def test_test_provider_no_key(db_session):
    from app.schemas.user_settings import UserSettingsUpdate

    service = UserSettingsService(db_session)
    user_id = "user-test-no-key"
    await service.update_settings(
        user_id, UserSettingsUpdate(selected_provider="anthropic")
    )

    result = await service.test_provider(user_id, "anthropic")
    assert result.success is False
    assert "No API key" in result.error


@pytest.mark.asyncio
async def test_test_provider_unknown_returns_error(db_session):
    from app.schemas.user_settings import UserSettingsUpdate

    service = UserSettingsService(db_session)
    user_id = "user-test-unknown"
    await service.update_settings(
        user_id,
        UserSettingsUpdate(provider_credentials={"anthropic": {"api_key": "key"}}),
    )

    result = await service.test_provider(user_id, "invalid-provider")
    assert result.success is False
    assert "Unknown provider" in result.error


@pytest.mark.asyncio
async def test_clearing_a_key_removes_provider(db_session):
    from app.schemas.user_settings import UserSettingsUpdate

    service = UserSettingsService(db_session)
    user_id = "user-clear-key"

    # Set a key
    await service.update_settings(
        user_id,
        UserSettingsUpdate(provider_credentials={"anthropic": {"api_key": "key-a"}}),
    )
    result = await service.get_settings(user_id)
    assert "anthropic" in result.configured_providers

    # Clear the key (empty string = remove)
    await service.update_settings(
        user_id,
        UserSettingsUpdate(provider_credentials={"anthropic": {"api_key": ""}}),
    )
    result = await service.get_settings(user_id)
    assert "anthropic" not in result.configured_providers
