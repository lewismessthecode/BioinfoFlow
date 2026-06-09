from __future__ import annotations

from app.config import settings
from app.models.llm import LlmCredentialSource, LlmProviderCredential
from app.services.llm.credentials import (
    credential_available,
    encrypt_secret,
    fingerprint_secret,
    to_credential_read_dict,
)


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


def test_env_credential_is_configured_but_not_available_until_env_exists(monkeypatch):
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
        "configured": True,
        "available": False,
        "env_var_name": "BIOINFOFLOW_TEST_LLM_KEY",
        "fingerprint": None,
        "masked_hint": "env:BIOINFOFLOW_TEST_LLM_KEY",
        "updated_at": None,
    }

    monkeypatch.setenv("BIOINFOFLOW_TEST_LLM_KEY", "sk-test")

    assert credential_available(credential) is True
    assert to_credential_read_dict(provider_id="provider-1", credential=credential)[
        "available"
    ] is True


def test_none_credential_can_be_available_for_no_auth_providers():
    payload = to_credential_read_dict(
        provider_id="provider-1",
        credential=None,
        credential_required=False,
    )

    assert payload["configured"] is False
    assert payload["available"] is True


def test_fingerprint_secret_is_keyed_and_stable(monkeypatch):
    monkeypatch.setattr(settings, "bioinfoflow_credential_key", "test-credential-key")
    monkeypatch.setattr(settings, "auth_mode", "personal")
    monkeypatch.setattr(settings, "auth_enabled", True)

    first = fingerprint_secret("sk-test-secret")
    second = fingerprint_secret("sk-test-secret")
    different = fingerprint_secret("sk-other-secret")

    assert first == second
    assert first != different
    assert len(first) == 32
