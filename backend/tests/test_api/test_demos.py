from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_removed_demos_endpoints_return_404(async_client):
    list_response = await async_client.get("/api/v1/demos")
    run_response = await async_client.post(
        "/api/v1/demos/rnaseq-quant-mini/run",
        json={},
    )

    assert list_response.status_code == 404
    assert run_response.status_code == 404


@pytest.mark.asyncio
async def test_removed_workflow_market_endpoint_returns_404(async_client):
    response = await async_client.get("/api/v1/workflows/market")

    assert response.status_code == 404
