from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_preflight_allows_localhost_and_loopback_dev_origins(async_client):
    response = await async_client.options(
        "/api/v1/workflows",
        headers={
            "Origin": "http://127.0.0.1:3003",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3003"


@pytest.mark.asyncio
async def test_preflight_still_rejects_untrusted_origins(async_client):
    response = await async_client.options(
        "/api/v1/workflows",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
