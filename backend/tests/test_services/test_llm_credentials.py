from __future__ import annotations

import pytest

from app.config import settings
from app.models.llm import LlmCredentialSource, LlmProviderCredential
from app.services.llm.credentials import (
    credential_available,
    encrypt_secret,
    generate_credential_fingerprint,
    to_credential_read_dict,
)
from app.utils.exceptions import AppError


def test_local_development_credential_key_lives_under_state_root(tmp_path, monkeypatch):
    home = tmp_path / "bioinfoflow-home"
    monkeypatch.setattr(settings, "bioinfoflow_home", str(home))
    monkeypatch.setattr(settings, "bioinfoflow_credential_key", "")
    monkeypatch.setattr(settings, "auth_mode", "personal")
    monkeypatch.setattr(settings, "auth_enabled", True)

    token = encrypt_secret("sk-local-test")

    assert token
    assert (home / "state" / "credentials" / "fernet.key").exists()
    assert not (home / "credentials" / "fernet.key").exists()


def test_team_mode_requires_configured_credential_key(monkeypatch):
    monkeypatch.setattr(settings, "bioinfoflow_credential_key", "")
    monkeypatch.setattr(settings, "auth_mode", "team")
    monkeypatch.setattr(settings, "auth_enabled", True)

    with pytest.raises(AppError) as exc_info:
        encrypt_secret("sk-team-test")

    assert exc_info.value.code == "CONFIGURATION_ERROR"
    assert exc_info.value.status_code == 503
    assert "BIOINFOFLOW_CREDENTIAL_KEY" in exc_info.value.message


def test_env_credential_is_configured_and_available_only_when_env_exists(monkeypatch):
    credential = LlmProviderCredential(
        provider_id="provider-1",
        source=LlmCredentialSource.ENV,
        env_var_name="BIOINFOFLOW_TEST_LLM_KEY",
        masked_hint="env:BIOINFOFLOW_TEST_LLM_KEY",
    )
    monkeypatch.delenv("BIOINFOFLOW_TEST_LLM_KEY", raising=False)

    assert credential_available(credential) is False
    assert to_credential_read_dict(provider_id="provider-1", credential=credential) == {
        "provider_id": "provider-1",
        "source": LlmCredentialSource.ENV,
        "configured": False,
        "available": False,
        "env_var_name": "BIOINFOFLOW_TEST_LLM_KEY",
        "fingerprint": None,
        "masked_hint": "env:BIOINFOFLOW_TEST_LLM_KEY",
        "updated_at": None,
    }

    monkeypatch.setenv("BIOINFOFLOW_TEST_LLM_KEY", "sk-test")

    assert credential_available(credential) is True
    refreshed = to_credential_read_dict(provider_id="provider-1", credential=credential)
    assert refreshed["configured"] is True
    assert refreshed["available"] is True


def test_none_credential_can_be_available_for_no_auth_providers():
    payload = to_credential_read_dict(
        provider_id="provider-1",
        credential=None,
        credential_required=False,
    )

    assert payload["configured"] is False
    assert payload["available"] is True


def test_generate_credential_fingerprint_returns_hex_identifier():
    fingerprint = generate_credential_fingerprint()

    assert len(fingerprint) == 16
    int(fingerprint, 16)
