from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.path_layout import workflow_bundle_home
from tests.support.auth import TEST_SESSION_COOKIE, create_better_auth_db


@pytest.mark.asyncio
async def test_workflows_crud(async_client):
    payload = {
        "source": "nf-core",
        "name": "viralrecon-test",
        "version": "1.0.0",
        "engine": "nextflow",
    }
    with patch(
        "app.services.workflow_service.SchemaExtractor.extract",
        new_callable=AsyncMock,
        return_value={"parameters": {}},
    ):
        create_resp = await async_client.post("/api/v1/workflows", json=payload)
    assert create_resp.status_code == 201
    workflow_id = create_resp.json()["data"]["id"]

    list_resp = await async_client.get("/api/v1/workflows")
    assert list_resp.status_code == 200

    get_resp = await async_client.get(f"/api/v1/workflows/{workflow_id}")
    assert get_resp.status_code == 200

    update_resp = await async_client.patch(
        f"/api/v1/workflows/{workflow_id}", json={"description": "updated"}
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["data"]["description"] == "updated"

    delete_resp = await async_client.delete(f"/api/v1/workflows/{workflow_id}")
    assert delete_resp.status_code == 204


@pytest.mark.asyncio
async def test_create_local_workflow_from_single_file_builds_bundle(async_client, tmp_path):
    workflow_path = tmp_path / "main.nf"
    workflow_path.write_text(
        "nextflow.enable.dsl=2\nworkflow { }\n",
        encoding="utf-8",
    )

    payload = {
        "source": "local",
        "engine": "nextflow",
        "source_ref": str(workflow_path),
        "file_name": "main.nf",
    }

    response = await async_client.post("/api/v1/workflows", json=payload)
    assert response.status_code == 201
    data = response.json()["data"]

    bundle_entry = workflow_bundle_home(data["id"]) / "main.nf"
    assert bundle_entry.exists()
    assert data["bundle_kind"] == "local_bundle"
    assert data["entrypoint_relpath"] == "main.nf"
    assert data["source_ref"] == "local"


@pytest.mark.asyncio
async def test_workflow_source_endpoint_reads_bundle_entrypoint(async_client, tmp_path):
    bundle_root = tmp_path / "bundle"
    bundle_root.mkdir()
    entrypoint = bundle_root / "pipelines" / "main.wdl"
    entrypoint.parent.mkdir(parents=True, exist_ok=True)
    entrypoint.write_text("version 1.0\nworkflow hello {}", encoding="utf-8")

    payload = {
        "source": "local",
        "engine": "wdl",
        "bundle_path": str(bundle_root),
        "entrypoint_relpath": "pipelines/main.wdl",
        "name": "hello",
    }

    create_resp = await async_client.post("/api/v1/workflows", json=payload)
    assert create_resp.status_code == 201
    workflow_id = create_resp.json()["data"]["id"]

    source_resp = await async_client.get(f"/api/v1/workflows/{workflow_id}/source")
    assert source_resp.status_code == 200
    assert "workflow hello" in source_resp.json()["data"]["content"]


@pytest.mark.asyncio
async def test_create_local_workflow_from_uploaded_bundle(async_client):
    data = {
        "engine": "nextflow",
        "name": "rnaseq-quant-mini",
        "entrypoint_relpath": "rnaseq_quant.nf",
        "bundle_paths": '["rnaseq_quant.nf","nextflow.config","data/samplesheet.csv"]',
    }
    files = [
        (
            "bundle_files",
            (
                "rnaseq_quant.nf",
                b"nextflow.enable.dsl=2\nworkflow { }\n",
                "application/octet-stream",
            ),
        ),
        (
            "bundle_files",
            (
                "nextflow.config",
                b"process.executor = 'local'\n",
                "application/octet-stream",
            ),
        ),
        (
            "bundle_files",
            (
                "samplesheet.csv",
                b"sample,fastq_1,fastq_2\n",
                "text/csv",
            ),
        ),
    ]

    response = await async_client.post(
        "/api/v1/workflows/local-bundle",
        data=data,
        files=files,
    )

    assert response.status_code == 201, response.json()
    payload = response.json()["data"]
    bundle_root = workflow_bundle_home(payload["id"])

    assert payload["bundle_kind"] == "local_bundle"
    assert payload["entrypoint_relpath"] == "rnaseq_quant.nf"
    assert (bundle_root / "rnaseq_quant.nf").exists()
    assert (bundle_root / "nextflow.config").exists()
    assert (bundle_root / "data" / "samplesheet.csv").exists()


@pytest.mark.asyncio
async def test_workflow_registry_id_requires_admin_in_team_mode(
    async_client,
    tmp_path,
    monkeypatch,
):
    registry_resp = await async_client.post(
        "/api/v1/container-registries",
        json={
            "name": "Harbor Bio",
            "endpoint": "https://harbor.example.test",
            "credential_source": "none",
        },
    )
    assert registry_resp.status_code == 201
    registry_id = registry_resp.json()["data"]["id"]

    auth_db_path = tmp_path / "better-auth-member.db"
    create_better_auth_db(auth_db_path)
    monkeypatch.setattr(settings, "auth_mode", "team")
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "better_auth_db_path", str(auth_db_path))
    async_client.cookies.set("better-auth.session_token", TEST_SESSION_COOKIE)

    create_resp = await async_client.post(
        "/api/v1/workflows",
        json={
            "source": "local",
            "engine": "nextflow",
            "name": "private-flow",
            "file_name": "main.nf",
            "content": "nextflow.enable.dsl=2\nworkflow { }\n",
            "container_registry_id": registry_id,
        },
    )
    assert create_resp.status_code == 403
    assert create_resp.json()["error"]["code"] == "PERMISSION_DENIED"

    bundle_resp = await async_client.post(
        "/api/v1/workflows/local-bundle",
        data={
            "engine": "nextflow",
            "name": "private-bundle",
            "entrypoint_relpath": "main.nf",
            "container_registry_id": registry_id,
            "bundle_paths": '["main.nf"]',
        },
        files={
            "bundle_files": (
                "main.nf",
                b"nextflow.enable.dsl=2\nworkflow { }\n",
                "application/octet-stream",
            ),
        },
    )
    assert bundle_resp.status_code == 403
    assert bundle_resp.json()["error"]["code"] == "PERMISSION_DENIED"
