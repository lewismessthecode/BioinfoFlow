from __future__ import annotations

import pytest

from app.path_layout import workflow_home


@pytest.mark.asyncio
async def test_duplicate_local_workflow_registration_cleans_staged_bundle(
    async_client, tmp_path
):
    workflow_path = tmp_path / "main.nf"
    workflow_path.write_text(
        "nextflow.enable.dsl=2\nworkflow { }\n",
        encoding="utf-8",
    )

    payload = {
        "source": "local",
        "engine": "nextflow",
        "name": "duplicate-demo",
        "version": "1.0.0",
        "source_ref": str(workflow_path),
        "file_name": "main.nf",
    }

    create_resp = await async_client.post("/api/v1/workflows", json=payload)
    assert create_resp.status_code == 201

    duplicate_resp = await async_client.post("/api/v1/workflows", json=payload)
    assert duplicate_resp.status_code == 409

    existing_ids = {
        item["id"] for item in (await async_client.get("/api/v1/workflows")).json()["data"]
    }
    workflow_dirs = {
        path.name for path in workflow_home(create_resp.json()["data"]["id"]).parent.iterdir()
    }

    assert workflow_dirs == existing_ids
