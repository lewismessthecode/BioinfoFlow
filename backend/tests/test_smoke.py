from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app as fastapi_app


def test_settings_defaults():
    assert settings.app_name == "Bioinfoflow"
    assert settings.cors_origins


def test_fastapi_version_matches_release_version():
    assert fastapi_app.version == "0.1.0"


@pytest.mark.asyncio
async def test_docs_route(async_client):
    response = await async_client.get("/api/v1/docs")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_rejects_untrusted_host(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://evil.example",
    ) as client:
        response = await client.get("/api/v1/docs")

    assert response.status_code == 400
