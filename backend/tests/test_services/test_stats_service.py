"""Tests for StatsService — dashboard statistics aggregation.

Validates that StatsService correctly delegates to StatsRepository
and transforms the raw data into the expected dashboard format.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.stats_service import StatsService


def _make_mock_run(
    *,
    run_id: str = "run-1",
    workflow_id: str | None = "wf-1",
    status: str = "completed",
    started_at: datetime | None = None,
    duration_seconds: int | None = 120,
    current_task: str | None = None,
) -> MagicMock:
    run = MagicMock()
    run.run_id = run_id
    run.workflow_id = workflow_id
    run.status = status
    run.started_at = started_at or datetime(2026, 1, 1, tzinfo=timezone.utc)
    run.duration_seconds = duration_seconds
    run.current_task = current_task
    return run


@pytest.mark.asyncio
async def test_get_dashboard_stats_aggregates_all_sources():
    """Happy path: all repository calls succeed, response shape is correct."""
    mock_session = MagicMock()

    with patch("app.services.stats_service.StatsRepository") as MockRepo:
        repo = MockRepo.return_value
        repo.get_run_counts_by_status = AsyncMock(
            return_value={"running": 2, "completed": 10, "failed": 1}
        )
        repo.get_workflow_count = AsyncMock(return_value=5)
        repo.get_image_counts_by_status = AsyncMock(
            return_value={"local": 3, "remote": 1}
        )
        repo.get_project_count = AsyncMock(return_value=7)
        repo.get_recent_runs = AsyncMock(
            return_value=[_make_mock_run(run_id="run-42", status="completed")]
        )

        service = StatsService(mock_session)
        result = await service.get_dashboard_stats(user_id="user-1")

    assert result["runs"]["total"] == 13
    assert result["runs"]["running"] == 2
    assert result["runs"]["completed"] == 10
    assert result["runs"]["failed"] == 1
    assert result["runs"]["queued"] == 0
    assert result["workflows"]["total"] == 5
    assert result["images"]["total"] == 4
    assert result["images"]["local"] == 3
    assert result["projects"]["total"] == 7
    assert len(result["recent_runs"]) == 1
    assert result["recent_runs"][0]["run_id"] == "run-42"


@pytest.mark.asyncio
async def test_get_dashboard_stats_with_empty_data():
    """Edge case: no runs, no workflows, no images, no projects."""
    mock_session = MagicMock()

    with patch("app.services.stats_service.StatsRepository") as MockRepo:
        repo = MockRepo.return_value
        repo.get_run_counts_by_status = AsyncMock(return_value={})
        repo.get_workflow_count = AsyncMock(return_value=0)
        repo.get_image_counts_by_status = AsyncMock(return_value={})
        repo.get_project_count = AsyncMock(return_value=0)
        repo.get_recent_runs = AsyncMock(return_value=[])

        service = StatsService(mock_session)
        result = await service.get_dashboard_stats()

    assert result["runs"]["total"] == 0
    assert result["runs"]["running"] == 0
    assert result["workflows"]["total"] == 0
    assert result["images"]["total"] == 0
    assert result["projects"]["total"] == 0
    assert result["recent_runs"] == []


@pytest.mark.asyncio
async def test_get_dashboard_stats_recent_runs_serialization():
    """Verify recent_runs entries serialize started_at to ISO and handle None workflow_id."""
    mock_session = MagicMock()
    ts = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)

    with patch("app.services.stats_service.StatsRepository") as MockRepo:
        repo = MockRepo.return_value
        repo.get_run_counts_by_status = AsyncMock(return_value={})
        repo.get_workflow_count = AsyncMock(return_value=0)
        repo.get_image_counts_by_status = AsyncMock(return_value={})
        repo.get_project_count = AsyncMock(return_value=0)
        repo.get_recent_runs = AsyncMock(
            return_value=[
                _make_mock_run(
                    run_id="run-x",
                    workflow_id=None,
                    started_at=ts,
                    duration_seconds=None,
                    current_task="FASTQC",
                ),
            ]
        )

        service = StatsService(mock_session)
        result = await service.get_dashboard_stats()

    run = result["recent_runs"][0]
    assert run["run_id"] == "run-x"
    assert run["workflow_id"] is None
    assert run["started_at"] == ts.isoformat()
    assert run["duration_seconds"] is None
    assert run["current_task"] == "FASTQC"


@pytest.mark.asyncio
async def test_get_dashboard_stats_passes_user_id_to_repo():
    """Verify user_id is forwarded to scoped repository methods."""
    mock_session = MagicMock()

    with patch("app.services.stats_service.StatsRepository") as MockRepo:
        repo = MockRepo.return_value
        repo.get_run_counts_by_status = AsyncMock(return_value={})
        repo.get_workflow_count = AsyncMock(return_value=0)
        repo.get_image_counts_by_status = AsyncMock(return_value={})
        repo.get_project_count = AsyncMock(return_value=0)
        repo.get_recent_runs = AsyncMock(return_value=[])

        service = StatsService(mock_session)
        await service.get_dashboard_stats(user_id="user-42")

    repo.get_run_counts_by_status.assert_called_once_with(
        user_id="user-42",
        workspace_id=None,
    )
    repo.get_project_count.assert_called_once_with(
        user_id="user-42",
        workspace_id=None,
    )
    repo.get_recent_runs.assert_called_once_with(
        limit=5,
        user_id="user-42",
        workspace_id=None,
    )


@pytest.mark.asyncio
async def test_get_dashboard_stats_run_with_no_started_at():
    """Verify a run with started_at=None serializes to None, not crash."""
    mock_session = MagicMock()
    run = _make_mock_run(run_id="run-none")
    run.started_at = None

    with patch("app.services.stats_service.StatsRepository") as MockRepo:
        repo = MockRepo.return_value
        repo.get_run_counts_by_status = AsyncMock(return_value={"running": 1})
        repo.get_workflow_count = AsyncMock(return_value=0)
        repo.get_image_counts_by_status = AsyncMock(return_value={})
        repo.get_project_count = AsyncMock(return_value=0)
        repo.get_recent_runs = AsyncMock(return_value=[run])

        service = StatsService(mock_session)
        result = await service.get_dashboard_stats()

    assert result["recent_runs"][0]["started_at"] is None
