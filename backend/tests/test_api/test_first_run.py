from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.services.demo_bootstrap_service as demo_bootstrap_module
from app.api.deps import get_current_user
from app.auth.session import AuthUser
from app.models.project import Project
from app.models.project_workflow_binding import ProjectWorkflowBinding
from app.models.project_workflow_pin import ProjectWorkflowPin
from app.models.workflow import Workflow
from app.models.workspace import Workspace
from app.path_layout import (
    project_data_root,
    workflow_bundle_home,
    workflow_metadata_path,
)
from app.services.demo_bootstrap_service import DemoBootstrapService
from app.workspace import DEFAULT_WORKSPACE_ID
from tests.support.path_contract import create_project


DEMO_PROJECT_NAME = "Bioinfoflow Demo"
DEMO_WORKFLOW_NAME = "bioinfoflow-quickstart"
DEMO_WORKFLOW_VERSION = "1.0.0"
DEMO_RUNTIME_IMAGE = (
    "bash:5.3.15@sha256:a19c811ee9e97fa8a080001d82b8e0ded303f0795cffdb1cbd162731bc8ce208"
)
SAMPLES_TSV = (
    "sample\tfastq\n"
    "sample-a\tsample-a.fastq\n"
    "sample-b\tsample-b.fastq\n"
)
SAMPLE_A_FASTQ = "@sample-a-1\nACGTACGT\n+\nFFFFFFFF\n@sample-a-2\nTGCATGCA\n+\nFFFFFFFF\n"
SAMPLE_B_FASTQ = "@sample-b-1\nAACCGG\n+\nFFFFFF\n@sample-b-2\nTTGGCC\n+\nFFFFFF\n"


def _session_factory(db_engine):
    return async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )


async def _bootstrap_service(session_factory, *, user_id: str = "dev"):
    async with session_factory() as session:
        return await DemoBootstrapService(session).bootstrap(
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id=user_id,
        )


async def _bootstrap(async_client):
    response = await async_client.post("/api/v1/first-run/bootstrap")
    assert response.status_code == 200
    return response.json()["data"]


@pytest.mark.asyncio
async def test_first_run_bootstrap_creates_exact_demo_state(async_client, db_session):
    default_response = await async_client.get("/api/v1/projects/default")
    assert default_response.status_code == 200

    data = await _bootstrap(async_client)

    assert data["ready"] is True
    assert data["created"] is True
    assert data["demo_project_id"]
    assert data["workflow_id"]
    assert data["starter_context"] == {
        "project_id": data["demo_project_id"],
        "workflow": {
            "id": data["workflow_id"],
            "name": DEMO_WORKFLOW_NAME,
            "version": DEMO_WORKFLOW_VERSION,
            "source": "local",
            "engine": "wdl",
            "scope": "project",
            "project_id": data["demo_project_id"],
        },
        "values": {
            "samples_tsv": "asset://project/samples.tsv",
            "sample_a_fastq": "asset://project/sample-a.fastq",
            "sample_b_fastq": "asset://project/sample-b.fastq",
        },
    }

    project = await db_session.get(Project, data["demo_project_id"])
    workflow = await db_session.get(Workflow, data["workflow_id"])
    assert project is not None
    assert project.name == DEMO_PROJECT_NAME
    assert project.storage_mode == "managed"
    assert project.is_default is False
    assert project.user_id == "dev"
    assert str(project.workspace_id) == DEFAULT_WORKSPACE_ID
    assert "bioinfoflow.demo.quickstart.v1" in (project.description or "")
    assert workflow is not None
    assert workflow.name == DEMO_WORKFLOW_NAME
    assert workflow.version == DEMO_WORKFLOW_VERSION
    assert str(workflow.source) == "local"
    assert str(workflow.engine) == "wdl"
    assert workflow.entrypoint_relpath == "workflow.wdl"
    assert workflow.source_ref == "local"
    assert "bioinfoflow.demo.quickstart.v1" in (workflow.description or "")
    assert {
        task["name"]: task["container"] for task in workflow.schema_json["tasks"]
    } == {
        "summarize_reads": DEMO_RUNTIME_IMAGE,
        "render_report": DEMO_RUNTIME_IMAGE,
    }

    binding = await db_session.scalar(
        select(ProjectWorkflowBinding).where(
            ProjectWorkflowBinding.project_id == project.id,
            ProjectWorkflowBinding.workflow_id == workflow.id,
        )
    )
    pin = await db_session.scalar(
        select(ProjectWorkflowPin).where(ProjectWorkflowPin.project_id == project.id)
    )
    assert binding is not None
    assert pin is not None
    assert str(pin.pinned_workflow_id) == str(workflow.id)

    data_root = project_data_root(project)
    assert (data_root / "samples.tsv").read_text() == SAMPLES_TSV
    assert (data_root / "sample-a.fastq").read_text() == SAMPLE_A_FASTQ
    assert (data_root / "sample-b.fastq").read_text() == SAMPLE_B_FASTQ
    workflow_text = (workflow_bundle_home(str(workflow.id)) / "workflow.wdl").read_text()
    assert DEMO_RUNTIME_IMAGE in workflow_text
    assert "summary.tsv" in workflow_text
    assert "report.md" in workflow_text


@pytest.mark.asyncio
async def test_first_run_bootstrap_is_idempotent(async_client, db_session):
    first = await _bootstrap(async_client)
    second = await _bootstrap(async_client)

    assert first["created"] is True
    assert second["created"] is False
    assert second["ready"] is True
    assert second["demo_project_id"] == first["demo_project_id"]
    assert second["workflow_id"] == first["workflow_id"]
    assert await db_session.scalar(
        select(func.count()).select_from(Project).where(Project.name == DEMO_PROJECT_NAME)
    ) == 1
    assert await db_session.scalar(
        select(func.count()).select_from(Workflow).where(
            Workflow.name == DEMO_WORKFLOW_NAME,
            Workflow.version == DEMO_WORKFLOW_VERSION,
        )
    ) == 1


@pytest.mark.asyncio
async def test_first_run_bootstrap_repairs_missing_files(async_client, db_session):
    first = await _bootstrap(async_client)
    project = await db_session.get(Project, first["demo_project_id"])
    workflow = await db_session.get(Workflow, first["workflow_id"])
    assert project is not None and workflow is not None
    (project_data_root(project) / "sample-a.fastq").unlink()
    (workflow_bundle_home(str(workflow.id)) / "workflow.wdl").unlink()
    workflow_metadata_path(str(workflow.id)).unlink()

    repaired = await _bootstrap(async_client)

    assert repaired["created"] is False
    assert repaired["ready"] is True
    assert (project_data_root(project) / "sample-a.fastq").read_text() == SAMPLE_A_FASTQ
    assert DEMO_RUNTIME_IMAGE in (
        workflow_bundle_home(str(workflow.id)) / "workflow.wdl"
    ).read_text()
    assert "bioinfoflow.demo.quickstart.v1" in workflow_metadata_path(
        str(workflow.id)
    ).read_text()


@pytest.mark.asyncio
async def test_first_run_bootstrap_repairs_missing_binding_and_pin(
    async_client, db_session
):
    first = await _bootstrap(async_client)
    binding = await db_session.scalar(
        select(ProjectWorkflowBinding).where(
            ProjectWorkflowBinding.project_id == first["demo_project_id"]
        )
    )
    pin = await db_session.scalar(
        select(ProjectWorkflowPin).where(
            ProjectWorkflowPin.project_id == first["demo_project_id"]
        )
    )
    assert binding is not None and pin is not None
    await db_session.delete(binding)
    await db_session.delete(pin)
    await db_session.commit()

    repaired = await _bootstrap(async_client)

    assert repaired["created"] is False
    assert await db_session.scalar(
        select(func.count()).select_from(ProjectWorkflowBinding).where(
            ProjectWorkflowBinding.project_id == first["demo_project_id"],
            ProjectWorkflowBinding.workflow_id == first["workflow_id"],
        )
    ) == 1
    assert await db_session.scalar(
        select(func.count()).select_from(ProjectWorkflowPin).where(
            ProjectWorkflowPin.project_id == first["demo_project_id"],
            ProjectWorkflowPin.pinned_workflow_id == first["workflow_id"],
        )
    ) == 1


@pytest.mark.asyncio
async def test_first_run_bootstrap_serializes_concurrent_calls(db_engine, db_session):
    session_factory = _session_factory(db_engine)
    first, second = await asyncio.gather(
        _bootstrap_service(session_factory),
        _bootstrap_service(session_factory),
    )

    results = [first, second]
    assert all(item["ready"] is True for item in results)
    assert sum(item["created"] is True for item in results) == 1
    assert results[0]["demo_project_id"] == results[1]["demo_project_id"]
    assert await db_session.scalar(
        select(func.count()).select_from(Project).where(Project.name == DEMO_PROJECT_NAME)
    ) == 1


@pytest.mark.asyncio
async def test_first_run_bootstrap_converges_different_users_in_one_workspace(
    db_engine, db_session, monkeypatch
):
    users = {
        "user-one": AuthUser(
            id="user-one",
            name="First User",
            email="first@example.test",
            role="owner",
            workspace_id=DEFAULT_WORKSPACE_ID,
        ),
        "user-two": AuthUser(
            id="user-two",
            name="Second User",
            email="second@example.test",
            role="member",
            workspace_id=DEFAULT_WORKSPACE_ID,
        ),
    }

    class IndependentLockRegistry(dict):
        @asynccontextmanager
        async def hold(self, key):
            del key
            async with asyncio.Lock():
                yield

    monkeypatch.setattr(
        demo_bootstrap_module,
        "_bootstrap_locks",
        IndependentLockRegistry(),
    )
    session_factory = _session_factory(db_engine)
    first_data, second_data = await asyncio.gather(
        _bootstrap_service(session_factory, user_id="user-one"),
        _bootstrap_service(session_factory, user_id="user-two"),
    )
    assert first_data["ready"] is True
    assert second_data["ready"] is True
    assert first_data["demo_project_id"] == second_data["demo_project_id"]
    assert await db_session.scalar(
        select(func.count()).select_from(Project).where(
            Project.workspace_id == DEFAULT_WORKSPACE_ID,
            Project.name == DEMO_PROJECT_NAME,
        )
    ) == 1
    project = await db_session.get(Project, first_data["demo_project_id"])
    assert project is not None
    assert project.user_id in users


@pytest.mark.asyncio
async def test_first_run_rejects_preclaimed_canonical_workflow(async_client, db_session):
    preclaimed = Workflow(
        id=str(uuid4()),
        name=DEMO_WORKFLOW_NAME,
        description="Marker: bioinfoflow.demo.quickstart.v1",
        source="local",
        engine="wdl",
        source_ref="local",
        entrypoint_relpath="workflow.wdl",
        bundle_kind="local_bundle",
        version=DEMO_WORKFLOW_VERSION,
        schema_json={},
        form_spec={},
    )
    db_session.add(preclaimed)
    await db_session.commit()

    preclaimed_response = await async_client.post("/api/v1/first-run/bootstrap")
    assert preclaimed_response.status_code == 409
    assert preclaimed_response.json()["error"]["code"] == "CONFLICT"



@pytest.mark.asyncio
@pytest.mark.parametrize("corruption", ["source_ref", "runtime_schema"])
async def test_first_run_rejects_corrupted_canonical_workflow(
    async_client, db_session, corruption
):
    canonical_id = str(
        uuid5(NAMESPACE_URL, "bioinfoflow:quickstart-workflow:1.0.0")
    )
    source_ref = "local" if corruption != "source_ref" else "replaced.wdl"
    runtime_image = DEMO_RUNTIME_IMAGE if corruption != "runtime_schema" else "latest"
    corrupted = Workflow(
        id=canonical_id,
        name=DEMO_WORKFLOW_NAME,
        description="Marker: bioinfoflow.demo.quickstart.v1",
        source="local",
        engine="wdl",
        source_ref=source_ref,
        entrypoint_relpath="workflow.wdl",
        bundle_kind="local_bundle",
        version=DEMO_WORKFLOW_VERSION,
        schema_json={
            "tasks": [
                {"name": "summarize_reads", "container": runtime_image},
                {"name": "render_report", "container": runtime_image},
            ]
        },
        form_spec={},
    )
    db_session.add(corrupted)
    await db_session.commit()

    corrupted_response = await async_client.post("/api/v1/first-run/bootstrap")
    assert corrupted_response.status_code == 409
    assert corrupted_response.json()["error"]["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_canonical_workflow_is_reserved_and_protected(async_client):
    create_response = await async_client.post(
        "/api/v1/workflows",
        json={
            "source": "local",
            "name": DEMO_WORKFLOW_NAME,
            "version": DEMO_WORKFLOW_VERSION,
            "engine": "wdl",
            "file_name": "workflow.wdl",
            "content": "version 1.0\nworkflow bioinfoflow_quickstart {}\n",
        },
    )
    assert create_response.status_code == 409
    assert create_response.json()["error"]["code"] == "CONFLICT"

    data = await _bootstrap(async_client)
    update_response = await async_client.patch(
        f"/api/v1/workflows/{data['workflow_id']}",
        json={"description": "User replacement"},
    )
    delete_response = await async_client.delete(
        f"/api/v1/workflows/{data['workflow_id']}"
    )

    assert update_response.status_code == 403
    assert update_response.json()["error"]["code"] == "PERMISSION_DENIED"
    assert delete_response.status_code == 403
    assert delete_response.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_bootstrap_lock_registry_releases_many_non_fresh_workspace_keys(
    async_client, db_session, app
):
    demo_bootstrap_module._bootstrap_locks.clear()
    users: dict[str, AuthUser] = {}
    for index in range(12):
        workspace_id = str(uuid4())
        user_id = f"non-fresh-{index}"
        db_session.add(
            Workspace(
                id=workspace_id,
                name=f"Workspace {index}",
                slug=f"workspace-{index}-{workspace_id}",
                is_default=False,
            )
        )
        db_session.add(
            Project(
                name=f"Existing project {index}",
                storage_mode="managed",
                user_id=user_id,
                created_by_user_id=user_id,
                workspace_id=workspace_id,
                is_default=False,
            )
        )
        users[user_id] = AuthUser(
            id=user_id,
            name=f"User {index}",
            email=f"user-{index}@example.test",
            role="member",
            workspace_id=workspace_id,
        )
    await db_session.commit()

    async def override_current_user(request: Request):
        return users[request.headers["x-test-user"]]

    app.dependency_overrides[get_current_user] = override_current_user
    try:
        for user_id in users:
            response = await async_client.post(
                "/api/v1/first-run/bootstrap",
                headers={"x-test-user": user_id},
            )
            assert response.status_code == 200
            assert response.json()["data"]["ready"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert len(demo_bootstrap_module._bootstrap_locks) == 0


@pytest.mark.asyncio
async def test_first_run_bootstrap_isolates_workspaces(
    async_client, db_session, app
):
    default_data = await _bootstrap(async_client)
    workspace_id = str(uuid4())
    db_session.add(
        Workspace(
            id=workspace_id,
            name="Second workspace",
            slug=f"second-{workspace_id}",
            is_default=False,
        )
    )
    await db_session.commit()
    other_user = AuthUser(
        id="user-two",
        name="Second User",
        email="second@example.test",
        role="owner",
        workspace_id=workspace_id,
    )

    async def override_current_user():
        return other_user

    app.dependency_overrides[get_current_user] = override_current_user
    try:
        other_data = await _bootstrap(async_client)
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert other_data["ready"] is True
    assert other_data["created"] is True
    assert other_data["demo_project_id"] != default_data["demo_project_id"]
    other_project = await db_session.get(Project, other_data["demo_project_id"])
    assert other_project is not None
    assert other_project.user_id == "user-two"
    assert str(other_project.workspace_id) == workspace_id
    assert other_data["workflow_id"] == default_data["workflow_id"]


@pytest.mark.asyncio
async def test_first_run_bootstrap_does_not_seed_non_fresh_workspace(
    async_client, db_session
):
    await create_project(db_session, name="Existing analysis")

    data = await _bootstrap(async_client)

    assert data == {
        "ready": False,
        "created": False,
        "demo_project_id": None,
        "workflow_id": None,
        "starter_context": None,
    }
    assert await db_session.scalar(
        select(func.count()).select_from(Project).where(Project.name == DEMO_PROJECT_NAME)
    ) == 0
