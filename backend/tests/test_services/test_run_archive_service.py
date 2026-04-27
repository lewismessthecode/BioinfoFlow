from __future__ import annotations

import io
import json
import zipfile
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.path_layout import run_results_root
from app.repositories.project_repo import ProjectRepository
from app.services.run_archive import RunArchiveService
from tests.support.path_contract import create_project


def _run_stub(*, project_id: str, run_id: str, config: dict | None = None):
    return SimpleNamespace(
        project_id=project_id,
        run_id=run_id,
        workflow_id=str(uuid4()),
        config=config or {},
    )


@pytest.mark.asyncio
async def test_persist_run_archive_redacts_secrets_and_uses_archived_documents(
    db_session, tmp_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = await create_project(
        db_session,
        name=f"Archive Project {uuid4()}",
        storage_mode="external",
        external_root_path=str(workspace),
    )
    run = _run_stub(
        project_id=str(project.id),
        run_id="run_archive_redaction",
        config={
            "request": {
                "params": {"api_key": "live-secret", "sample": "tumor"},
                "inputs": {"password": "pw", "manifest": "sample.csv"},
                "config_overrides": {"authorization": "Bearer token", "cpus": 4},
                "archive_documents": {
                    "params": {"api_key": "archived-secret", "sample": "archived"},
                    "inputs": {"token": "input-secret", "manifest": "archived.csv"},
                },
            },
            "resolved": {
                "runspec": {
                    "workspace": str(workspace),
                    "params": {"secret_token": "hide-me", "sample": "tumor"},
                }
            },
        },
    )

    service = RunArchiveService(ProjectRepository(db_session))
    await service.persist_run_archive(
        run=run,
        workspace_path=workspace,
        engine="nextflow",
    )

    run_dir = workspace / "runs" / run.run_id
    params_payload = json.loads((run_dir / "input" / "params.json").read_text())
    inputs_payload = json.loads((run_dir / "input" / "inputs.json").read_text())
    overrides_payload = json.loads(
        (run_dir / "input" / "config_overrides.json").read_text()
    )
    manifest_payload = json.loads(
        (run_dir / "audit" / "run.manifest.json").read_text()
    )

    assert params_payload == {"api_key": "[REDACTED]", "sample": "archived"}
    assert inputs_payload == {"token": "[REDACTED]", "manifest": "archived.csv"}
    assert overrides_payload == {"authorization": "[REDACTED]", "cpus": 4}
    assert manifest_payload["engine"] == "nextflow"
    assert manifest_payload["resolved_inputs"]["params"] == {
        "secret_token": "[REDACTED]",
        "sample": "tumor",
    }


@pytest.mark.asyncio
async def test_list_outputs_skips_symlinks_and_builds_result_asset_uris(
    db_session, tmp_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "stolen.txt").write_text("secret", encoding="utf-8")

    project = await create_project(
        db_session,
        name=f"Archive Outputs {uuid4()}",
        storage_mode="external",
        external_root_path=str(workspace),
    )
    run = _run_stub(project_id=str(project.id), run_id="run_outputs")
    results_root = run_results_root(project, run.run_id)
    results_root.mkdir(parents=True)
    (results_root / "report.txt").write_text("report", encoding="utf-8")
    nested = results_root / "nested"
    nested.mkdir()
    (nested / "metrics.json").write_text("{}", encoding="utf-8")
    (results_root / "outside-link").symlink_to(outside / "stolen.txt")

    service = RunArchiveService(ProjectRepository(db_session))
    payload = await service.list_outputs(run)

    by_name = {item["name"]: item for item in payload["files"]}
    assert "outside-link" not in by_name
    assert by_name["report.txt"]["uri"] == "asset://results/run_outputs/report.txt"
    assert by_name["nested"]["uri"] == "asset://results/run_outputs/nested"
    assert by_name["metrics.json"]["uri"] == "asset://results/run_outputs/nested/metrics.json"


@pytest.mark.asyncio
async def test_build_output_archive_returns_zip_with_expected_contents(
    db_session, tmp_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = await create_project(
        db_session,
        name=f"Archive Zip {uuid4()}",
        storage_mode="external",
        external_root_path=str(workspace),
    )
    run = _run_stub(project_id=str(project.id), run_id="run_zip")
    results_root = run_results_root(project, run.run_id)
    results_root.mkdir(parents=True)
    (results_root / "summary.txt").write_text("hello", encoding="utf-8")
    (results_root / "nested").mkdir()
    (results_root / "nested" / "metrics.tsv").write_text("sample\t1\n", encoding="utf-8")

    service = RunArchiveService(ProjectRepository(db_session))
    archive_bytes, content_type = await service.build_output_archive(
        run,
        archive_format="zip",
    )

    assert content_type == "application/zip"
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        assert sorted(archive.namelist()) == [
            f"runs/{run.run_id}/results/",
            f"runs/{run.run_id}/results/nested/",
            f"runs/{run.run_id}/results/nested/metrics.tsv",
            f"runs/{run.run_id}/results/summary.txt",
        ]


@pytest.mark.asyncio
async def test_build_output_archive_refuses_symlink_targets_outside_workspace(
    db_session, tmp_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")

    project = await create_project(
        db_session,
        name=f"Archive Guard {uuid4()}",
        storage_mode="external",
        external_root_path=str(workspace),
    )
    run = _run_stub(project_id=str(project.id), run_id="run_guard")
    (workspace / "exports").symlink_to(outside, target_is_directory=True)

    service = RunArchiveService(ProjectRepository(db_session))

    with pytest.raises(PermissionError, match="project root"):
        await service.build_output_archive(
            run,
            file_path="exports",
            archive_format="tar.gz",
        )


@pytest.mark.asyncio
async def test_delete_outputs_removes_existing_results_directory(
    db_session, tmp_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = await create_project(
        db_session,
        name=f"Archive Delete {uuid4()}",
        storage_mode="external",
        external_root_path=str(workspace),
    )
    run = _run_stub(project_id=str(project.id), run_id="run_delete")
    results_root = run_results_root(project, run.run_id)
    results_root.mkdir(parents=True)
    (results_root / "summary.txt").write_text("bye", encoding="utf-8")

    service = RunArchiveService(ProjectRepository(db_session))
    await service.delete_outputs(run)

    assert not results_root.exists()
