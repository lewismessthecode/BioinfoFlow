from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from app.models.llm import LlmModel, LlmProvider, LlmProviderCredential
from app.services.llm.credentials import (
    CredentialMaterial,
    credential_hmac_digest,
    encrypt_secret,
)
from app.services.llm.test_status import (
    attach_provider_test_fingerprint,
    compute_provider_test_fingerprint,
    is_provider_test_status_current,
    sanitize_provider_test_status,
)


_PROVIDER_ID = "00000000-0000-0000-0000-00000000a001"
_MODEL_ID = "00000000-0000-0000-0000-00000000b001"


def _provider() -> LlmProvider:
    return LlmProvider(
        id=_PROVIDER_ID,
        name="Responses relay",
        kind="openai_compatible",
        wire_protocol="responses",
        base_url="https://relay.example.com/v1/",
        scope="user",
        workspace_id="00000000-0000-0000-0000-000000000001",
        user_id="user-1",
        enabled=True,
        allow_insecure_http=False,
        provider_metadata={
            "providerTemplate": "openai-compatible",
            "unrelated": "first",
        },
    )


def _model() -> LlmModel:
    return LlmModel(
        id=_MODEL_ID,
        provider_id=_PROVIDER_ID,
        model_id="gpt-5.4-mini",
        display_name="GPT 5.4 Mini",
        supports_tools=True,
        supports_streaming=True,
    )


def _env_credential(name: str = "RELAY_API_KEY") -> LlmProviderCredential:
    return LlmProviderCredential(
        provider_id=_PROVIDER_ID,
        source="env",
        env_var_name=name,
        fingerprint="display-only-fingerprint",
        masked_hint="env:RELAY_API_KEY",
    )


def test_credential_hmac_digest_is_keyed_and_domain_separated(monkeypatch) -> None:
    key = b"unit-test-server-key"
    payload = b"provider-test-material"
    monkeypatch.setattr(
        "app.services.llm.credentials._credential_key",
        lambda: key,
    )

    digest = credential_hmac_digest(payload, domain="llm-provider-test-status.v1")
    other_domain = credential_hmac_digest(payload, domain="another-domain.v1")
    derived_key = hmac.new(
        key,
        b"bioinfoflow-domain-key.v1\x00llm-provider-test-status.v1",
        hashlib.sha256,
    ).digest()
    expected = hmac.new(derived_key, payload, hashlib.sha256).hexdigest()

    assert digest == expected
    assert digest != hashlib.sha256(payload).hexdigest()
    assert other_domain != digest
    assert key.hex() not in digest


def test_resolved_credential_material_hides_secret_from_repr() -> None:
    secret = "sentinel-resolved-credential"

    material = CredentialMaterial(api_key=secret, source="stored")

    assert secret not in repr(material)


@pytest.mark.parametrize(
    "change",
    [
        "kind",
        "base_url",
        "wire_protocol",
        "credential_source",
        "credential_env_name",
        "provider_template",
        "model_record_id",
        "provider_model_id",
    ],
)
def test_provider_test_fingerprint_changes_for_material_configuration(
    change: str,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RELAY_API_KEY", "sentinel-secret-one")
    provider = _provider()
    credential = _env_credential()
    model = _model()
    original = compute_provider_test_fingerprint(provider, credential, model)

    if change == "kind":
        provider.kind = "openai"
    elif change == "base_url":
        provider.base_url = "https://other-relay.example.com/v1"
    elif change == "wire_protocol":
        provider.wire_protocol = "chat_completions"
    elif change == "credential_source":
        credential.source = "none"
    elif change == "credential_env_name":
        monkeypatch.setenv("OTHER_RELAY_API_KEY", "sentinel-secret-one")
        credential.env_var_name = "OTHER_RELAY_API_KEY"
    elif change == "provider_template":
        provider.provider_metadata = {"providerTemplate": "openai"}
    elif change == "model_record_id":
        model.id = "00000000-0000-0000-0000-00000000b002"
    else:
        model.model_id = "gpt-5.4"

    changed = compute_provider_test_fingerprint(provider, credential, model)

    assert changed != original


def test_provider_test_fingerprint_uses_normalized_base_url(monkeypatch) -> None:
    monkeypatch.setenv("RELAY_API_KEY", "sentinel-secret")
    provider = _provider()
    credential = _env_credential()
    model = _model()
    with_trailing_slash = compute_provider_test_fingerprint(provider, credential, model)

    provider.base_url = "https://relay.example.com/v1"

    assert (
        compute_provider_test_fingerprint(provider, credential, model)
        == with_trailing_slash
    )


def test_unrelated_provider_credential_and_model_edits_preserve_status(
    monkeypatch,
) -> None:
    monkeypatch.setenv("RELAY_API_KEY", "sentinel-secret")
    provider = _provider()
    credential = _env_credential()
    model = _model()
    original = compute_provider_test_fingerprint(provider, credential, model)

    provider.name = "Renamed relay"
    provider.enabled = False
    provider.scope = "workspace"
    provider.allow_insecure_http = True
    provider.provider_metadata = {
        "providerTemplate": "openai-compatible",
        "unrelated": "changed",
    }
    credential.fingerprint = "rotated-display-only-fingerprint"
    credential.masked_hint = "changed-mask"
    model.display_name = "Renamed model"
    model.supports_vision = True

    assert compute_provider_test_fingerprint(provider, credential, model) == original


def test_environment_value_rotation_under_same_name_invalidates_status(
    monkeypatch,
) -> None:
    provider = _provider()
    credential = _env_credential()
    model = _model()
    monkeypatch.setenv("RELAY_API_KEY", "sentinel-secret-one")
    original = compute_provider_test_fingerprint(provider, credential, model)

    monkeypatch.setenv("RELAY_API_KEY", "sentinel-secret-two")

    assert compute_provider_test_fingerprint(provider, credential, model) != original


def test_stored_credential_uses_resolved_value_not_ciphertext() -> None:
    provider = _provider()
    model = _model()
    credential = LlmProviderCredential(
        provider_id=_PROVIDER_ID,
        source="stored",
        encrypted_secret=encrypt_secret("stored-secret-one"),
    )
    original = compute_provider_test_fingerprint(provider, credential, model)

    credential.encrypted_secret = encrypt_secret("stored-secret-one")
    assert compute_provider_test_fingerprint(provider, credential, model) == original

    credential.encrypted_secret = encrypt_secret("stored-secret-two")
    assert compute_provider_test_fingerprint(provider, credential, model) != original


def test_internal_status_current_check_uses_material_fingerprint(monkeypatch) -> None:
    monkeypatch.setenv("RELAY_API_KEY", "sentinel-secret")
    provider = _provider()
    credential = _env_credential()
    model = _model()
    fingerprint = compute_provider_test_fingerprint(provider, credential, model)
    status = attach_provider_test_fingerprint(
        {
            "success": True,
            "checked_at": "2026-07-13T00:00:00Z",
            "wire_protocol": "responses",
            "model": "gpt-5.4-mini",
            "latency_ms": 12,
            "error": None,
        },
        fingerprint,
    )

    assert is_provider_test_status_current(
        status,
        provider=provider,
        credential=credential,
        tested_model=model,
    )
    monkeypatch.setenv("RELAY_API_KEY", "rotated-secret")
    assert not is_provider_test_status_current(
        status,
        provider=provider,
        credential=credential,
        tested_model=model,
    )
    assert not is_provider_test_status_current(
        {"success": True},
        provider=provider,
        credential=credential,
        tested_model=model,
    )


def test_public_status_sanitizer_excludes_internal_fingerprint_and_secrets(
    monkeypatch,
    caplog,
) -> None:
    secret = "sentinel-provider-secret"
    hmac_key = b"sentinel-server-hmac-key"
    monkeypatch.setenv("RELAY_API_KEY", secret)
    monkeypatch.setattr(
        "app.services.llm.credentials._credential_key",
        lambda: hmac_key,
    )
    provider = _provider()
    credential = _env_credential()
    model = _model()
    fingerprint = compute_provider_test_fingerprint(provider, credential, model)
    internal = attach_provider_test_fingerprint(
        {
            "success": False,
            "checked_at": "2026-07-13T00:00:00Z",
            "wire_protocol": "responses",
            "model": "gpt-5.4-mini",
            "model_id": _MODEL_ID,
            "latency_ms": 18,
            "error": {"code": "authentication", "message": "Authentication failed."},
            "error_message": "Authentication failed.",
            "error_code": "authentication",
            "retryable": False,
            "http_status": 401,
            "provider_code": "invalid_api_key",
            "raw_request": {"api_key": secret},
            "raw_response": secret,
        },
        fingerprint,
    )

    public = sanitize_provider_test_status(internal)

    assert public == {
        "success": False,
        "checked_at": "2026-07-13T00:00:00Z",
        "wire_protocol": "responses",
        "model": "gpt-5.4-mini",
        "model_id": _MODEL_ID,
        "latency_ms": 18,
        "error": {"code": "authentication", "message": "Authentication failed."},
        "error_message": "Authentication failed.",
        "error_code": "authentication",
        "retryable": False,
        "http_status": 401,
        "provider_code": "invalid_api_key",
    }
    for rendered in (repr(public), json.dumps(public), str(RuntimeError(public))):
        assert fingerprint not in rendered
        assert secret not in rendered
        assert hmac_key.decode() not in rendered
        assert hmac_key.hex() not in rendered
    assert fingerprint not in caplog.text
    assert secret not in caplog.text
    assert hmac_key.decode() not in caplog.text


@pytest.mark.parametrize("status", [None, "invalid", [], {}])
def test_public_status_sanitizer_rejects_missing_or_invalid_status(status: object) -> None:
    assert sanitize_provider_test_status(status) is None
