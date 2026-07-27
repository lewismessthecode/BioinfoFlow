from __future__ import annotations

import pytest

from app.services.agent_core.tools.web.public_url_policy import validate_public_url
from app.utils.exceptions import PermissionDeniedError


async def _resolve_public(_host: str) -> set[str]:
    return {"93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"}


@pytest.mark.asyncio
async def test_public_url_policy_accepts_http_and_https_with_global_dns() -> None:
    validated = await validate_public_url(
        "https://example.com/docs?q=1", resolver=_resolve_public
    )

    assert validated.url == "https://example.com/docs?q=1"
    assert validated.host == "example.com"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/file",
        "https://user:secret@example.com/",
        "https:///missing-host",
        "https://localhost/",
        "https://database/",
        "http://127.0.0.1/",
        "http://10.0.0.8/",
        "http://169.254.169.254/latest/meta-data/",
        "https://metadata.google.internal/",
        "http://[::1]/",
    ],
)
async def test_public_url_policy_rejects_unsafe_syntax_and_hosts(url: str) -> None:
    with pytest.raises(PermissionDeniedError, match="public URL"):
        await validate_public_url(url, resolver=_resolve_public)


@pytest.mark.asyncio
async def test_public_url_policy_rejects_when_any_dns_address_is_not_global() -> None:
    async def resolve_mixed(_host: str) -> set[str]:
        return {"93.184.216.34", "192.168.1.10"}

    with pytest.raises(PermissionDeniedError, match="public URL"):
        await validate_public_url("https://example.com", resolver=resolve_mixed)


@pytest.mark.asyncio
async def test_public_url_policy_rejects_dns_failure() -> None:
    async def resolve_empty(_host: str) -> set[str]:
        return set()

    with pytest.raises(PermissionDeniedError, match="public URL"):
        await validate_public_url("https://example.com", resolver=resolve_empty)
