from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import hmac
import json
from typing import Any

from app.models.llm import LlmModel, LlmProvider, LlmProviderCredential
from app.services.llm.credentials import (
    credential_hmac_digest,
    resolve_credential_material,
)
from app.services.llm.provider_templates import normalize_provider_base_url


_FINGERPRINT_DOMAIN = "llm-provider-test-status.v1"
_INTERNAL_FINGERPRINT_KEY = "_invocation_fingerprint"
_PUBLIC_STATUS_FIELDS = (
    "success",
    "checked_at",
    "wire_protocol",
    "model",
    "model_id",
    "latency_ms",
    "error",
    "error_message",
    "error_code",
    "retryable",
    "http_status",
    "provider_code",
    "mode",
)


def compute_provider_test_fingerprint(
    provider: LlmProvider,
    credential: LlmProviderCredential | None,
    tested_model: LlmModel | None,
) -> str:
    credential_material = resolve_credential_material(credential)
    metadata = (
        provider.provider_metadata
        if isinstance(provider.provider_metadata, dict)
        else {}
    )
    template_id = metadata.get("providerTemplate")
    payload = {
        "provider": {
            "kind": str(provider.kind),
            "base_url": normalize_provider_base_url(
                str(provider.kind),
                provider.base_url,
            ),
            "wire_protocol": str(provider.wire_protocol),
            "template_id": str(template_id) if template_id is not None else None,
        },
        "credential": {
            "source": credential_material.source,
            "env_var_name": (
                credential.env_var_name
                if credential is not None and credential_material.source == "env"
                else None
            ),
            "resolved_value": credential_material.api_key,
        },
        "tested_model": {
            "id": str(tested_model.id) if tested_model is not None else None,
            "model_id": (
                str(tested_model.model_id)
                if tested_model is not None
                else "__model_not_configured__"
            ),
        },
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return credential_hmac_digest(encoded, domain=_FINGERPRINT_DOMAIN)


def attach_provider_test_fingerprint(
    public_status: Mapping[str, Any],
    fingerprint: str,
) -> dict[str, Any]:
    if not fingerprint:
        raise ValueError("Provider test fingerprint must not be empty")
    internal = sanitize_provider_test_status(public_status) or {}
    internal[_INTERNAL_FINGERPRINT_KEY] = fingerprint
    return internal


def sanitize_provider_test_status(status: object) -> dict[str, Any] | None:
    if not isinstance(status, Mapping):
        return None
    public = {
        field: deepcopy(status[field])
        for field in _PUBLIC_STATUS_FIELDS
        if field in status
    }
    return public or None


def is_provider_test_status_current(
    status: object,
    *,
    provider: LlmProvider,
    credential: LlmProviderCredential | None,
    tested_model: LlmModel | None,
) -> bool:
    if not isinstance(status, Mapping):
        return False
    stored = status.get(_INTERNAL_FINGERPRINT_KEY)
    if not isinstance(stored, str) or not stored:
        return False
    try:
        current = compute_provider_test_fingerprint(
            provider,
            credential,
            tested_model,
        )
    except Exception:  # noqa: BLE001 - unreadable credentials make status stale
        return False
    return hmac.compare_digest(stored, current)
