"""Tests for response envelope consistency in system API endpoints."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_gpu_metrics_returns_envelope(async_client, monkeypatch):
    """GET /system/gpu/metrics must return a standard API envelope."""

    async def mock_get_gpu_metrics():
        return [{"index": 0, "utilization": 50}]

    # Mock the gpu_service to avoid real GPU detection
    class MockGpuService:
        async def get_status(self):
            return type(
                "GpuStatus",
                (),
                {
                    "available": False,
                    "nvidia_smi_found": False,
                    "docker_nvidia_runtime": False,
                    "parabricks_compatible": False,
                    "recommendation": "No GPU",
                    "error": None,
                    "gpus": [],
                },
            )()

        async def get_gpu_metrics(self):
            return [{"index": 0, "utilization": 50}]

    monkeypatch.setattr("app.api.v1.system.get_gpu_service", lambda: MockGpuService())

    resp = await async_client.get("/api/v1/system/gpu/metrics")
    assert resp.status_code == 200
    body = resp.json()

    # Must have standard envelope fields
    assert "success" in body, "Response missing 'success' field"
    assert body["success"] is True
    assert "data" in body, "Response missing 'data' field"
    assert "meta" in body, "Response missing 'meta' field"
    assert body["data"]["metrics"] == [{"index": 0, "utilization": 50}]
