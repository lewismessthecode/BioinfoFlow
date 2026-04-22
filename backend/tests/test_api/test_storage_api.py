from __future__ import annotations

import pytest

from app.path_layout import deliveries_root, project_data_root
from tests.support.path_contract import create_project


@pytest.mark.asyncio
async def test_storage_api_lists_sources_and_browses_without_absolute_paths(
    async_client, db_session
):
    project = await create_project(db_session, name="Storage API Project")
    (project_data_root(project) / "notes.txt").write_text("hello")

    deliveries = deliveries_root()
    deliveries.mkdir(parents=True, exist_ok=True)
    (deliveries / "sample.bam").write_text("BAM")

    project_id = str(project.id)

    sources_resp = await async_client.get(
        "/api/v1/storage/sources", params={"project_id": project_id}
    )
    assert sources_resp.status_code == 200
    assert [item["id"] for item in sources_resp.json()["data"]] == [
        "project",
        "results",
        "deliveries",
        "reference",
        "database",
    ]

    browse_resp = await async_client.get(
        "/api/v1/storage/browse",
        params={"project_id": project_id, "source_id": "deliveries", "path": "."},
    )
    assert browse_resp.status_code == 200
    item = browse_resp.json()["data"]["files"][0]
    assert item["path"] == "sample.bam"
    assert item["uri"] == "asset://deliveries/sample.bam"
    assert str(deliveries) not in browse_resp.text


@pytest.mark.asyncio
async def test_storage_api_reads_uploads_and_scans_project_source(
    async_client, db_session
):
    project = await create_project(db_session, name="Storage API Project Two")
    project_id = str(project.id)

    upload_resp = await async_client.post(
        "/api/v1/storage/upload",
        data={"project_id": project_id, "source_id": "project", "path": "reads"},
        files={"file": ("S1_R1.fastq.gz", b"FASTQ", "application/gzip")},
    )
    assert upload_resp.status_code == 201
    assert upload_resp.json()["data"]["uri"] == "asset://project/reads/S1_R1.fastq.gz"

    read_resp = await async_client.get(
        "/api/v1/storage/read",
        params={
            "project_id": project_id,
            "uri": "asset://project/reads/S1_R1.fastq.gz",
        },
    )
    assert read_resp.status_code == 200
    assert "FASTQ" in read_resp.json()["data"]["content"]

    scan_resp = await async_client.post(
        "/api/v1/storage/scan",
        json={
            "project_id": project_id,
            "source_id": "project",
            "path": "reads",
            "file_types": ["fastq"],
        },
    )
    assert scan_resp.status_code == 200
    assert scan_resp.json()["data"]["detected_samples"][0]["files"][0][
        "uri"
    ] == "asset://project/reads/S1_R1.fastq.gz"


@pytest.mark.asyncio
async def test_storage_api_rejects_upload_to_read_only_source(
    async_client, db_session
):
    deliveries = deliveries_root()
    deliveries.mkdir(parents=True, exist_ok=True)

    project = await create_project(db_session, name="Storage API Project Three")
    project_id = str(project.id)

    resp = await async_client.post(
        "/api/v1/storage/upload",
        data={"project_id": project_id, "source_id": "deliveries"},
        files={"file": ("sample.bam", b"BAM", "application/octet-stream")},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"
