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
    project_home,
    projects_root,
    workflow_bundle_home,
    workflow_metadata_path,
)
from app.services.demo_bootstrap_service import DemoBootstrapService
from app.services.project_directory_service import ProjectDirectoryService
from app.workspace import DEFAULT_WORKSPACE_ID
from tests.support.path_contract import create_project


DEMO_PROJECT_NAME = "Bioinfoflow Demo"
DEMO_WORKFLOW_NAME = "bioinfoflow-quickstart"
DEMO_WORKFLOW_VERSION = "1.0.0"
DEMO_RUNTIME_IMAGE = (
    "ubuntu:24.04@sha256:4fbb8e6a8395de5a7550b33509421a2bafbc0aab6c06ba2cef9ebffbc7092d90"
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
    assert project.directory_name == "bioinfoflow-demo"
    assert project_home(project).name == "bioinfoflow-demo"
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
    project = await db_session.get(Project, first["demo_project_id"])
    assert project is not None
    directory_name = project.directory_name
    second = await _bootstrap(async_client)

    assert first["created"] is True
    assert second["created"] is False
    assert second["ready"] is True
    assert second["demo_project_id"] == first["demo_project_id"]
    assert second["workflow_id"] == first["workflow_id"]
    await db_session.refresh(project)
    assert project.directory_name == directory_name == "bioinfoflow-demo"
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
    directory_name = project.directory_name
    (project_data_root(project) / "sample-a.fastq").unlink()
    (workflow_bundle_home(str(workflow.id)) / "workflow.wdl").unlink()
    workflow_metadata_path(str(workflow.id)).unlink()

    repaired = await _bootstrap(async_client)

    assert repaired["created"] is False
    assert repaired["ready"] is True
    await db_session.refresh(project)
    assert project.directory_name == directory_name == "bioinfoflow-demo"
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
    demo_project_id = str(
        uuid5(
            NAMESPACE_URL,
            f"bioinfoflow:quickstart-project:{DEFAULT_WORKSPACE_ID}",
        )
    )
    assert await db_session.get(Project, demo_project_id) is None
    assert not (projects_root() / "bioinfoflow-demo").exists()
    assert not (projects_root() / demo_project_id).exists()



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
    default_project = await db_session.get(Project, default_data["demo_project_id"])
    assert other_project is not None
    assert default_project is not None
    assert default_project.directory_name == "bioinfoflow-demo"
    assert other_project.directory_name == "bioinfoflow-demo-2"
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


@pytest.mark.asyncio
async def test_first_run_bootstrap_preserves_legacy_demo_uuid_directory(
    async_client, db_session
):
    project_id = str(
        uuid5(
            NAMESPACE_URL,
            f"bioinfoflow:quickstart-project:{DEFAULT_WORKSPACE_ID}",
        )
    )
    legacy = Project(
        id=project_id,
        name=DEMO_PROJECT_NAME,
        description=(
            "Managed quickstart assets for the first Agent-guided analysis. "
            "Marker: bioinfoflow.demo.quickstart.v1"
        ),
        storage_mode="managed",
        user_id="dev",
        created_by_user_id="dev",
        workspace_id=DEFAULT_WORKSPACE_ID,
        is_default=False,
    )
    db_session.add(legacy)
    await db_session.commit()

    data = await _bootstrap(async_client)

    assert data["created"] is False
    await db_session.refresh(legacy)
    assert legacy.directory_name is None
    assert project_home(legacy).name == project_id
    assert project_data_root(legacy).is_dir()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_step", ["project_files", "binding"])
async def test_first_run_bootstrap_failure_rolls_back_reserved_project(
    db_session, monkeypatch, failure_step
):
    service = DemoBootstrapService(db_session)

    if failure_step == "project_files":
        def fail_project_files(project):
            del project
            raise RuntimeError("project files failed")

        monkeypatch.setattr(service, "_repair_project_files", fail_project_files)
    else:
        async def fail_binding(*, project_id, workflow):
            del project_id, workflow
            raise RuntimeError("binding failed")

        monkeypatch.setattr(service, "_ensure_binding_and_pin", fail_binding)

    with pytest.raises(RuntimeError, match="failed"):
        await service.bootstrap(
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
        )

    project_id = str(
        uuid5(
            NAMESPACE_URL,
            f"bioinfoflow:quickstart-project:{DEFAULT_WORKSPACE_ID}",
        )
    )
    assert await db_session.get(Project, project_id) is None
    assert not (projects_root() / "bioinfoflow-demo").exists()
    assert not (projects_root() / project_id).exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_first_run_bootstrap_closes_project_reservation_fds(
    db_session, monkeypatch, cancelled
):
    reservations = []
    original_add_pending = ProjectDirectoryService.add_pending

    async def capture_reservation(self, data):
        reservation = await original_add_pending(self, data)
        reservations.append(reservation)
        return reservation

    monkeypatch.setattr(ProjectDirectoryService, "add_pending", capture_reservation)
    service = DemoBootstrapService(db_session)
    if cancelled:
        async def cancel_commit():
            raise asyncio.CancelledError

        monkeypatch.setattr(db_session, "commit", cancel_commit)

    if cancelled:
        with pytest.raises(asyncio.CancelledError):
            await service.bootstrap(
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
            )
    else:
        await service.bootstrap(
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
        )

    assert len(reservations) == 1
    assert reservations[0].root_fd is None
    assert reservations[0].parent_fd is None
    assert reservations[0].root.exists() is (not cancelled)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rollback_error",
    [RuntimeError("rollback failed"), asyncio.CancelledError()],
)
async def test_first_run_bootstrap_cleans_reservation_when_rollback_fails(
    db_session, monkeypatch, rollback_error
):
    reservations = []
    original_add_pending = ProjectDirectoryService.add_pending

    async def capture_reservation(self, data):
        reservation = await original_add_pending(self, data)
        reservations.append(reservation)
        return reservation

    def fail_project_files(project):
        del project
        raise RuntimeError("project files failed")

    async def fail_rollback():
        raise rollback_error

    monkeypatch.setattr(ProjectDirectoryService, "add_pending", capture_reservation)
    service = DemoBootstrapService(db_session)
    monkeypatch.setattr(service, "_repair_project_files", fail_project_files)
    monkeypatch.setattr(db_session, "rollback", fail_rollback)

    with pytest.raises(type(rollback_error)) as caught:
        await service.bootstrap(
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
        )

    if isinstance(rollback_error, RuntimeError):
        assert str(caught.value) == "rollback failed"
    contexts = []
    context = caught.value.__context__
    while context is not None:
        contexts.append(context)
        context = context.__context__
    assert any(str(error) == "project files failed" for error in contexts)
    assert len(reservations) == 1
    assert reservations[0].root_fd is None
    assert reservations[0].parent_fd is None
    assert not reservations[0].root.exists()
