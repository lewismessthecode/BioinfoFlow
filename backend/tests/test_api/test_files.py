from __future__ import annotations

import pytest

from app.repositories.project_repo import ProjectRepository


@pytest.mark.asyncio
async def test_files_endpoints(async_client, db_session, tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "S001_R1.fq.gz").write_text("FASTQ")
    (raw_dir / "S001_R2.fq.gz").write_text("FASTQ")
    (tmp_path / "samplesheet.csv").write_text("sample,fastq_1,fastq_2\n")

    project = await ProjectRepository(db_session).create(
        name="Files Project",
        description=None,
        storage_mode="external", external_root_path=str(tmp_path),
        user_id="dev",
    )

    project_id = str(project.id)

    list_resp = await async_client.get(
        "/api/v1/files",
        params={"project_id": project_id, "path": "."},
    )
    assert list_resp.status_code == 200

    read_resp = await async_client.get(
        "/api/v1/files/read",
        params={"project_id": project_id, "path": "samplesheet.csv"},
    )
    assert read_resp.status_code == 200
    assert "samplesheet.csv" in read_resp.json()["data"]["path"]

    write_resp = await async_client.post(
        "/api/v1/files/write",
        json={"project_id": project_id, "path": "notes.txt", "content": "hello"},
    )
    assert write_resp.status_code == 200

    scan_resp = await async_client.post(
        "/api/v1/files/scan",
        json={"project_id": project_id, "path": ".", "file_types": ["fastq"]},
    )
    assert scan_resp.status_code == 200
    assert scan_resp.json()["data"]["total_samples"] == 1


@pytest.mark.asyncio
async def test_files_error_paths(async_client, db_session, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "existing.txt").write_text("hello")
    nested = workspace / "nested"
    nested.mkdir()

    project = await ProjectRepository(db_session).create(
        name="Files Errors",
        description=None,
        storage_mode="external", external_root_path=str(workspace),
        user_id="dev",
    )
    project_id = str(project.id)

    escape_resp = await async_client.get(
        "/api/v1/files/read",
        params={"project_id": project_id, "path": "../outside.txt"},
    )
    assert escape_resp.status_code == 403
    assert escape_resp.json()["error"]["code"] == "PERMISSION_DENIED"

    read_missing = await async_client.get(
        "/api/v1/files/read",
        params={"project_id": project_id, "path": "missing.txt"},
    )
    assert read_missing.status_code == 404
    assert read_missing.json()["error"]["code"] == "FILE_NOT_FOUND"

    download_missing = await async_client.get(
        "/api/v1/files/download",
        params={"project_id": project_id, "path": "missing.txt"},
    )
    assert download_missing.status_code == 404
    assert download_missing.json()["error"]["code"] == "FILE_NOT_FOUND"

    download_dir = await async_client.get(
        "/api/v1/files/download",
        params={"project_id": project_id, "path": "nested"},
    )
    assert download_dir.status_code == 400
    assert download_dir.json()["error"]["code"] == "VALIDATION_ERROR"

    upload_conflict = await async_client.post(
        "/api/v1/files/upload",
        data={"project_id": project_id, "path": "existing.txt"},
        files={"file": ("existing.txt", b"new content", "text/plain")},
    )
    assert upload_conflict.status_code == 409
    assert upload_conflict.json()["error"]["code"] == "CONFLICT"

    delete_missing = await async_client.delete(
        "/api/v1/files",
        params={"project_id": project_id, "path": "missing.txt"},
    )
    assert delete_missing.status_code == 404
    assert delete_missing.json()["error"]["code"] == "FILE_NOT_FOUND"


# --- Phase 2 Fix 16: Upload size limits ---


@pytest.mark.asyncio
async def test_file_upload_rejects_oversized_file(
    async_client, db_session, tmp_path, monkeypatch
):
    """File uploads exceeding max_upload_size_bytes must be rejected."""
    from app import config as config_module

    monkeypatch.setattr(config_module.settings, "max_upload_size_bytes", 100)

    project = await ProjectRepository(db_session).create(
        name="Upload Limit Project",
        description=None,
        storage_mode="external", external_root_path=str(tmp_path),
        user_id="dev",
    )
    project_id = str(project.id)

    oversized_content = b"x" * 200

    resp = await async_client.post(
        "/api/v1/files/upload",
        data={"project_id": project_id},
        files={"file": ("big.bin", oversized_content, "application/octet-stream")},
    )
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "FILE_TOO_LARGE"


@pytest.mark.asyncio
async def test_file_upload_allows_small_file(
    async_client, db_session, tmp_path, monkeypatch
):
    """File uploads under the limit should succeed."""
    from app import config as config_module

    monkeypatch.setattr(config_module.settings, "max_upload_size_bytes", 1000)

    project = await ProjectRepository(db_session).create(
        name="Upload Small Project",
        description=None,
        storage_mode="external", external_root_path=str(tmp_path),
        user_id="dev",
    )
    project_id = str(project.id)

    small_content = b"hello"

    resp = await async_client.post(
        "/api/v1/files/upload",
        data={"project_id": project_id},
        files={"file": ("small.txt", small_content, "text/plain")},
    )
    assert resp.status_code == 201
