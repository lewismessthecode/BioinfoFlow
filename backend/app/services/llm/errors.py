from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProviderErrorCode(str, Enum):
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    ENDPOINT_MISMATCH = "endpoint_mismatch"
    MODEL_NOT_FOUND = "model_not_found"
    RATE_LIMIT = "rate_limit"
    QUOTA_EXHAUSTED = "quota_exhausted"
    NETWORK = "network"
    INVALID_REQUEST = "invalid_request"
    PROVIDER = "provider"


@dataclass(frozen=True)
class PublicProviderError:
    code: ProviderErrorCode
    message: str
    retryable: bool = False


def classify_provider_error(
    *,
    http_status: int | None = None,
    provider_code: str | None = None,
    provider_kind: str | None = None,
    base_url: str | None = None,
    detail: str | None = None,
) -> PublicProviderError:
    del detail
    if provider_kind == "kimi_code" and "moonshot." in (base_url or "").lower():
        return PublicProviderError(
            ProviderErrorCode.ENDPOINT_MISMATCH,
            "Kimi Code keys require https://api.kimi.com/coding/v1; "
            "Moonshot platform endpoints use different credentials.",
        )
    normalized_code = (provider_code or "").lower()
    if http_status == 402 or normalized_code in {
        "insufficient_quota",
        "quota_exceeded",
        "insufficient_balance",
    }:
        return PublicProviderError(
            ProviderErrorCode.QUOTA_EXHAUSTED,
            "The provider account has insufficient quota or balance.",
        )
    if http_status == 401:
        return PublicProviderError(
            ProviderErrorCode.AUTHENTICATION,
            "The provider rejected the API key.",
        )
    if http_status == 403:
        return PublicProviderError(
            ProviderErrorCode.AUTHORIZATION,
            "The API key is not allowed to use this model or endpoint.",
        )
    if http_status == 404:
        return PublicProviderError(
            ProviderErrorCode.MODEL_NOT_FOUND,
            "The selected model or provider endpoint was not found.",
        )
    if http_status == 429:
        return PublicProviderError(
            ProviderErrorCode.RATE_LIMIT,
            "The provider rate limit was exceeded.",
            retryable=True,
        )
    if http_status == 400:
        return PublicProviderError(
            ProviderErrorCode.INVALID_REQUEST,
            "The provider rejected the request parameters.",
        )
    if http_status is None:
        return PublicProviderError(
            ProviderErrorCode.NETWORK,
            "The provider endpoint could not be reached.",
            retryable=True,
        )
    return PublicProviderError(
        ProviderErrorCode.PROVIDER,
        "The provider request failed.",
        retryable=bool(http_status >= 500),
    )
