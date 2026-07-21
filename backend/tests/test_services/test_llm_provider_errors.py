import pytest

from app.services.llm.errors import ProviderErrorCode, classify_provider_error


@pytest.mark.parametrize(
    ("status", "provider_code", "expected"),
    [
        (401, None, ProviderErrorCode.AUTHENTICATION),
        (403, None, ProviderErrorCode.AUTHORIZATION),
        (404, None, ProviderErrorCode.MODEL_NOT_FOUND),
        (429, None, ProviderErrorCode.RATE_LIMIT),
        (402, "insufficient_quota", ProviderErrorCode.QUOTA_EXHAUSTED),
    ],
)
def test_provider_error_classifier_has_finite_public_codes(
    status: int,
    provider_code: str | None,
    expected: ProviderErrorCode,
) -> None:
    error = classify_provider_error(
        http_status=status,
        provider_code=provider_code,
    )

    assert error.code is expected


def test_kimi_code_key_on_moonshot_endpoint_is_reported_as_endpoint_mismatch() -> None:
    error = classify_provider_error(
        http_status=401,
        provider_kind="kimi_code",
        base_url="https://api.moonshot.cn/v1",
    )

    assert error.code is ProviderErrorCode.ENDPOINT_MISMATCH
    assert "api.kimi.com/coding/v1" in error.message


def test_provider_error_never_echoes_secret_material() -> None:
    secret = "sentinel-secret-api-key"
    error = classify_provider_error(
        http_status=401,
        provider_code=secret,
        detail=f"Authorization: Bearer {secret}",
    )

    assert secret not in error.message
    assert secret not in repr(error)
