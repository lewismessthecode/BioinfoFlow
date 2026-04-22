from __future__ import annotations

import pytest

import app.models  # noqa: F401
from app.models.project import Project
from app.path_layout import (
    deliveries_root,
    project_data_root,
    run_results_root,
)
from app.services.storage_service import StorageService


async def _create_project(db_session) -> Project:
    project = Project(
        name="storage-test-project",
        storage_mode="managed",
        external_root_path=None,
        user_id="dev",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest.mark.asyncio
async def test_storage_service_lists_all_four_sources(db_session):
    project = await _create_project(db_session)
    service = StorageService(db_session)

    sources = await service.list_sources(project_id=str(project.id))

    assert [source.id for source in sources] == [
        "project",
        "results",
        "deliveries",
        "reference",
        "database",
    ]


@pytest.mark.asyncio
async def test_storage_service_resolves_project_asset_under_data_root(db_session):
    project = await _create_project(db_session)
    target = project_data_root(project) / "reads" / "sample_R1.fastq.gz"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("FASTQ")

    service = StorageService(db_session)
    resolved = await service.resolve_asset(
        project_id=str(project.id),
        uri="asset://project/reads/sample_R1.fastq.gz",
    )

    assert resolved.source.id == "project"
    assert resolved.path == target.resolve()


@pytest.mark.asyncio
async def test_storage_service_resolves_run_results_asset(db_session):
    project = await _create_project(db_session)
    target = run_results_root(project, "run_123abc") / "report.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("done")

    service = StorageService(db_session)
    resolved = await service.resolve_asset(
        project_id=str(project.id),
        uri="asset://results/run_123abc/report.txt",
    )

    assert resolved.source.id == "results"
    assert resolved.path == target.resolve()


@pytest.mark.asyncio
async def test_storage_service_scans_deliveries_source(db_session):
    project = await _create_project(db_session)
    deliveries = deliveries_root()
    deliveries.mkdir(parents=True, exist_ok=True)
    (deliveries / "S1_R1.fastq.gz").write_text("FASTQ")
    (deliveries / "S1_R2.fastq.gz").write_text("FASTQ")

    service = StorageService(db_session)
    result = await service.scan(
        project_id=str(project.id),
        source_id="deliveries",
        path=".",
        file_types=["fastq"],
    )

    assert result.total_samples == 1
    assert result.detected_samples[0].files[0].uri.startswith("asset://deliveries/")
