"""Tests for response envelope consistency in system API endpoints."""

from __future__ import annotations

import pytest
from sqlalchemy import insert

from app.config import settings
from app.models.project import Project
from app.models.project_workflow_binding import ProjectWorkflowBinding
from app.models.user_settings import UserSettings
from app.models.workflow import Workflow


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
                    "detected": False,
                    "nvidia_smi_found": False,
                    "docker_nvidia_runtime": False,
                    "runtime_visible_to_backend": False,
                    "usable_for_gpu_workflows": False,
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


@pytest.mark.asyncio
async def test_readiness_returns_blocking_checks(async_client, monkeypatch):
    """GET /system/readiness summarizes first-run blockers in one envelope."""

    class MockDockerService:
        async def is_available(self):
            return False

        async def check_nvidia_runtime(self):
            return False

        async def get_parabricks_image(self):
            return None

    class MockGpuService:
        async def get_status(self):
            return type(
                "GpuStatus",
                (),
                {
                    "available": False,
                    "detected": False,
                    "parabricks_compatible": False,
                },
            )()

    monkeypatch.setattr("app.api.v1.system.DockerService", MockDockerService)
    monkeypatch.setattr("app.api.v1.system.get_gpu_service", lambda: MockGpuService())
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "deepseek_api_key", "")

    resp = await async_client.get("/api/v1/system/readiness")
    assert resp.status_code == 200
    body = resp.json()

    assert body["success"] is True
    data = body["data"]
    assert data["severity"] == "blocked"
    assert data["next_action"]["href"] == "/settings"

    checks = {check["id"]: check for check in data["checks"]}
    assert checks["backend"]["status"] == "pass"
    assert checks["docker"]["status"] == "fail"
    assert checks["provider_key"]["status"] == "fail"
    assert "parabricks_image" not in checks
    assert checks["project"]["status"] == "fail"
    assert checks["workflow_binding"]["status"] == "fail"
    assert data["summary"]["required_total"] == 6
    assert data["summary"]["required_completed"] == 1
    assert data["summary"]["optional_total"] == 1
    assert data["summary"]["optional_warnings"] == 1


@pytest.mark.asyncio
async def test_readiness_describes_visible_nvidia_runtime_without_claiming_no_gpu(
    async_client,
    monkeypatch,
):
    class MockDockerService:
        async def is_available(self):
            return True

        async def check_nvidia_runtime(self):
            return True

        async def get_parabricks_image(self):
            return None

    class MockGpuService:
        async def get_status(self):
            return type(
                "GpuStatus",
                (),
                {
                    "available": False,
                    "detected": False,
                    "nvidia_smi_found": False,
                    "docker_nvidia_runtime": True,
                    "runtime_visible_to_backend": False,
                    "usable_for_gpu_workflows": False,
                    "gpus": [],
                    "parabricks_compatible": False,
                    "recommendation": "NVIDIA container runtime is configured, but nvidia-smi is not available to the backend process.",
                    "error": "nvidia-smi not found",
                },
            )()

    monkeypatch.setattr("app.api.v1.system.DockerService", MockDockerService)
    monkeypatch.setattr("app.api.v1.system.get_gpu_service", lambda: MockGpuService())
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")

    resp = await async_client.get("/api/v1/system/readiness")
    assert resp.status_code == 200

    checks = {check["id"]: check for check in resp.json()["data"]["checks"]}
    gpu_check = checks["gpu"]

    assert gpu_check["status"] == "warn"
    assert gpu_check["facts"]["docker_nvidia_runtime"] is True
    assert gpu_check["facts"]["runtime_visible_to_backend"] is False
    assert gpu_check["facts"]["host_signal"] == "nvidia_runtime"
    assert "nvidia-smi" in gpu_check["facts"]["recommendation"]


@pytest.mark.asyncio
async def test_readiness_accepts_saved_user_provider_credentials(
    async_client,
    db_session,
    monkeypatch,
):
    """A provider key saved from settings should satisfy first-run readiness."""

    class MockDockerService:
        async def is_available(self):
            return True

        async def check_nvidia_runtime(self):
            return False

        async def get_parabricks_image(self):
            return None

    class MockGpuService:
        async def get_status(self):
            return type(
                "GpuStatus",
                (),
                {
                    "available": False,
                    "detected": False,
                    "parabricks_compatible": False,
                },
            )()

    monkeypatch.setattr("app.api.v1.system.DockerService", MockDockerService)
    monkeypatch.setattr("app.api.v1.system.get_gpu_service", lambda: MockGpuService())
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "deepseek_api_key", "")

    await db_session.execute(
        insert(UserSettings).values(
            id="00000000-0000-0000-0000-000000000401",
            user_id="user-with-provider",
            provider_credentials='{"openai":{"api_key":"sk-user-key"}}',
            selected_provider="openai",
        )
    )
    await db_session.commit()

    resp = await async_client.get("/api/v1/system/readiness")
    assert resp.status_code == 200

    checks = {check["id"]: check for check in resp.json()["data"]["checks"]}
    assert checks["provider_key"]["status"] == "pass"


@pytest.mark.asyncio
async def test_readiness_reports_ready_when_first_run_prereqs_exist(
    async_client,
    db_session,
    monkeypatch,
):
    """Readiness becomes ready once environment and first-run entities exist."""

    class MockDockerService:
        async def is_available(self):
            return True

        async def check_nvidia_runtime(self):
            return False

        async def get_parabricks_image(self):
            return None

    class MockGpuService:
        async def get_status(self):
            return type(
                "GpuStatus",
                (),
                {
                    "available": False,
                    "detected": False,
                    "parabricks_compatible": False,
                },
            )()

    monkeypatch.setattr("app.api.v1.system.DockerService", MockDockerService)
    monkeypatch.setattr("app.api.v1.system.get_gpu_service", lambda: MockGpuService())
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")

    await db_session.execute(
        insert(Project).values(
            id="00000000-0000-0000-0000-000000000101",
            name="Ready Project",
            user_id="user-ready",
            workspace_id="00000000-0000-0000-0000-000000000001",
            is_default=True,
        )
    )
    await db_session.execute(
        insert(Workflow).values(
            id="00000000-0000-0000-0000-000000000201",
            name="rnaseq",
            source="local",
            engine="nextflow",
            version="1.0.0",
        )
    )
    await db_session.execute(
        insert(ProjectWorkflowBinding).values(
            id="00000000-0000-0000-0000-000000000301",
            project_id="00000000-0000-0000-0000-000000000101",
            workflow_id="00000000-0000-0000-0000-000000000201",
        )
    )
    await db_session.commit()

    resp = await async_client.get("/api/v1/system/readiness")
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert data["severity"] == "ready"
    assert data["next_action"]["href"] == "/workflows?scope=project"
    assert all(check["status"] != "fail" for check in data["checks"])
