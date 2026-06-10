from __future__ import annotations

import base64
import hashlib
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from cryptography.fernet import Fernet

from app.config import settings
from app.models.llm import LlmCredentialSource, LlmProviderCredential


@dataclass(frozen=True)
class CredentialMaterial:
    api_key: str | None
    source: str


def credential_configured(credential: LlmProviderCredential | None) -> bool:
    if credential is None:
        return False
    if credential.source == LlmCredentialSource.ENV:
        # An env-backed credential is only "configured" when the referenced
        # variable actually resolves to a value. A recorded variable name with
        # an empty/unset value is not usable.
        env_var_name = credential.env_var_name or ""
        return bool(env_var_name and os.getenv(env_var_name))
    if credential.source == LlmCredentialSource.STORED:
        return bool(credential.encrypted_secret)
    return False


def credential_available(
    credential: LlmProviderCredential | None,
    *,
    credential_required: bool = True,
) -> bool:
    if credential is None or credential.source == LlmCredentialSource.NONE:
        return not credential_required
    if credential.source == LlmCredentialSource.ENV:
        env_var_name = credential.env_var_name or ""
        return bool(env_var_name and os.getenv(env_var_name))
    if credential.source == LlmCredentialSource.STORED:
        try:
            return bool(decrypt_secret(credential.encrypted_secret))
        except Exception:
            return False
    return False


def mask_secret(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 8:
        return f"{secret[:2]}...{secret[-2:]}"
    return f"{secret[:4]}...{secret[-4:]}"


def generate_credential_fingerprint() -> str:
    return secrets.token_hex(8)


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str | None) -> str | None:
    if not token:
        return None
    return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")


def resolve_credential_material(
    credential: LlmProviderCredential | None,
) -> CredentialMaterial:
    if credential is None or credential.source == LlmCredentialSource.NONE:
        return CredentialMaterial(api_key=None, source=LlmCredentialSource.NONE)
    if credential.source == LlmCredentialSource.ENV:
        env_var_name = credential.env_var_name or ""
        return CredentialMaterial(
            api_key=os.getenv(env_var_name) or None,
            source=LlmCredentialSource.ENV,
        )
    return CredentialMaterial(
        api_key=decrypt_secret(credential.encrypted_secret),
        source=LlmCredentialSource.STORED,
    )


def _fernet() -> Fernet:
    return Fernet(_credential_key())


def _credential_key() -> bytes:
    configured = settings.bioinfoflow_credential_key.strip()
    if configured:
        return _normalize_key(configured)
    if settings.auth_is_team:
        raise RuntimeError(
            "BIOINFOFLOW_CREDENTIAL_KEY is required before storing provider secrets in team mode"
        )
    return _local_development_key()


def _normalize_key(value: str) -> bytes:
    raw = value.encode("utf-8")
    try:
        Fernet(raw)
        return raw
    except Exception:
        digest = hashlib.sha256(raw).digest()
        return base64.urlsafe_b64encode(digest)


def _local_development_key() -> bytes:
    path = Path(settings.state_root) / "credentials" / "fernet.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_bytes().strip()
    key = Fernet.generate_key()
    path.write_bytes(key)
    return key


def to_credential_read_dict(
    *,
    provider_id: str | UUID,
    credential: LlmProviderCredential | None,
    credential_required: bool = True,
) -> dict:
    if credential is None:
        return {
            "provider_id": provider_id,
            "source": LlmCredentialSource.NONE,
            "configured": False,
            "available": not credential_required,
            "env_var_name": None,
            "fingerprint": None,
            "masked_hint": None,
            "updated_at": None,
        }
    return {
        "provider_id": provider_id,
        "source": credential.source,
        "configured": credential_configured(credential),
        "available": credential_available(
            credential,
            credential_required=credential_required,
        ),
        "env_var_name": credential.env_var_name,
        "fingerprint": credential.fingerprint,
        "masked_hint": credential.masked_hint,
        "updated_at": credential.updated_at,
    }
