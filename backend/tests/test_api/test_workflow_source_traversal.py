"""Tests for path traversal protection in workflow source endpoint."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.workflow import Workflow, WorkflowEngine, WorkflowSource
from app.path_layout import workflow_bundle_home


@pytest.mark.asyncio
async def test_workflow_source_rejects_path_traversal(
    async_client, db_session, tmp_path
):
    """Source endpoint must reject entrypoints that escape the workflow bundle."""

    # Create a secret file outside the registry root
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET DATA")

    workflow_id = str(uuid4())
    bundle_root = workflow_bundle_home(workflow_id)
    bundle_root.mkdir(parents=True, exist_ok=True)

    wf = Workflow(
        id=workflow_id,
        name=f"malicious-{uuid4().hex[:8]}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version="1.0.0",
        source_ref="local",
        bundle_kind="local_bundle",
        entrypoint_relpath=f"../../../../{secret.name}",
    )
    db_session.add(wf)
    await db_session.commit()
    await db_session.refresh(wf)

    resp = await async_client.get(f"/api/v1/workflows/{wf.id}/source")
    assert resp.status_code == 403
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_workflow_source_allows_valid_path(
    async_client, db_session, tmp_path
):
    """Source endpoint must allow entrypoints within the workflow bundle."""
    workflow_id = str(uuid4())
    bundle_root = workflow_bundle_home(workflow_id)
    bundle_root.mkdir(parents=True, exist_ok=True)

    wf_file = bundle_root / "main.nf"
    wf_file.write_text("workflow { }")

    wf = Workflow(
        id=workflow_id,
        name=f"legit-{uuid4().hex[:8]}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version="1.0.0",
        source_ref="local",
        bundle_kind="local_bundle",
        entrypoint_relpath="main.nf",
    )
    db_session.add(wf)
    await db_session.commit()
    await db_session.refresh(wf)

    resp = await async_client.get(f"/api/v1/workflows/{wf.id}/source")
    assert resp.status_code == 200
    assert resp.json()["data"]["content"] == "workflow { }"


@pytest.mark.asyncio
async def test_workflow_source_rejects_symlink_escape(
    async_client, db_session, tmp_path
):
    """Source endpoint must reject symlinks that escape the workflow bundle."""

    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET DATA")

    workflow_id = str(uuid4())
    bundle_root = workflow_bundle_home(workflow_id)
    bundle_root.mkdir(parents=True, exist_ok=True)
    link = bundle_root / "link.nf"
    link.symlink_to(secret)

    wf = Workflow(
        id=workflow_id,
        name=f"symlink-{uuid4().hex[:8]}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version="1.0.0",
        source_ref="local",
        bundle_kind="local_bundle",
        entrypoint_relpath="link.nf",
    )
    db_session.add(wf)
    await db_session.commit()
    await db_session.refresh(wf)

    resp = await async_client.get(f"/api/v1/workflows/{wf.id}/source")
    assert resp.status_code == 403
