"""Tests for platform_* tools — thin adapters over the service layer.

Strategy: mock the service methods and assert the tool forwards the right
auth context and returns the right shape. Full service-layer integration is
already covered by each service's own tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.agent.tools.base import RiskLevel
from app.services.agent.tools.platform_tools import (
    PlatformProjectListTool,
    PlatformProjectShowTool,
    PlatformRunCancelTool,
    PlatformRunListTool,
    PlatformRunShowTool,
    PlatformRunSubmitTool,
    PlatformWorkflowBindTool,
    PlatformWorkflowListTool,
    PlatformWorkflowProjectListTool,
)


class TestRiskLevels:
    """Risk is static on the class — approval UX depends on this mapping."""

    def test_read_tools_are_read(self):
        for tool in (
            PlatformProjectListTool,
            PlatformProjectShowTool,
            PlatformWorkflowListTool,
            PlatformRunListTool,
            PlatformRunShowTool,
        ):
            assert tool.risk_level == RiskLevel.READ, tool.__name__

    def test_mutating_tools_are_act_high(self):
        for tool in (
            PlatformRunSubmitTool,
            PlatformRunCancelTool,
            PlatformWorkflowBindTool,
        ):
            assert tool.risk_level == RiskLevel.ACT_HIGH, tool.__name__


class TestAuthScopingForwarded:
    """user_id/workspace_id must reach every service call that accepts them.
    This is what makes platform tools safer than shell+bif: the LLM never
    picks the auth scope — the tool constructor does.
    """

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_run_show_forwards_user_and_workspace(self, mock_session):
        tool = PlatformRunShowTool(
            mock_session,
            project_id="proj-1",
            user_id="alice",
            workspace_id="ws-42",
        )
        with patch.object(
            tool, "_run_service", None
        ), patch(
            "app.services.agent.tools.platform_tools.RunService"
        ) as svc_class:
            instance = svc_class.return_value
            instance.get_run = AsyncMock()
            # Stub out the normalized ORM run with enough fields for RunRead
            run = AsyncMock()
            run.id = uuid4()
            run.run_id = "r-abc"
            run.project_id = uuid4()
            run.status = "queued"
            run.config = {}
            run.created_at = None
            run.updated_at = None
            instance.get_run.return_value = run

            # Intercept _serialize_run rather than reshape the whole Run
            with patch(
                "app.services.agent.tools.platform_tools._serialize_run",
                return_value={"run_id": "r-abc"},
            ):
                result = await tool.execute(run_id="r-abc")

            instance.get_run.assert_awaited_once_with(
                "r-abc", user_id="alice", workspace_id="ws-42"
            )
            assert result.success
            assert result.data == {"run": {"run_id": "r-abc"}}

    @pytest.mark.asyncio
    async def test_run_submit_forwards_user_and_workspace(self, mock_session):
        project_id = "11111111-1111-1111-1111-111111111111"
        workflow_id = "22222222-2222-2222-2222-222222222222"
        tool = PlatformRunSubmitTool(
            mock_session,
            project_id=project_id,
            user_id="alice",
            workspace_id="ws-42",
        )
        with patch(
            "app.services.agent.tools.platform_tools.RunCompiler"
        ) as svc_class:
            instance = svc_class.return_value
            instance.create_run = AsyncMock()
            instance.create_run.return_value = AsyncMock()
            with patch(
                "app.services.agent.tools.platform_tools._serialize_run",
                return_value={"run_id": "r-new"},
            ):
                result = await tool.execute(
                    workflow_id=workflow_id,
                    values={"sample": "s1"},
                )

            call = instance.create_run.await_args
            assert call.kwargs["user_id"] == "alice"
            payload = call.args[0]
            assert str(payload.project_id) == project_id
            assert str(payload.workflow_id) == workflow_id
            assert payload.values == {"sample": "s1"}
            assert result.success

    @pytest.mark.asyncio
    async def test_project_list_requires_workspace_id(self, mock_session):
        """Without workspace_id the tool refuses rather than silently
        listing every project in the DB. Policy is defensive."""
        tool = PlatformProjectListTool(
            mock_session,
            project_id="proj-1",
            user_id="alice",
            workspace_id=None,
        )
        result = await tool.execute()
        assert not result.success
        assert "workspace_id" in (result.error or "")

    @pytest.mark.asyncio
    async def test_project_show_returns_not_found_cleanly(self, mock_session):
        tool = PlatformProjectShowTool(
            mock_session,
            project_id="proj-1",
            user_id="alice",
            workspace_id="ws-42",
        )
        with patch(
            "app.services.agent.tools.platform_tools.ProjectService"
        ) as svc_class:
            instance = svc_class.return_value
            instance.get_project = AsyncMock(return_value=None)

            result = await tool.execute(project_id="proj-missing")

            assert not result.success
            assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_project_workflow_list_serializes_nested_workflows(self, mock_session):
        tool = PlatformWorkflowProjectListTool(
            mock_session,
            project_id="proj-1",
            user_id="alice",
            workspace_id="ws-42",
        )
        pinned = object()
        old_version = object()
        newest_version = object()
        now = datetime.now(UTC)

        with patch(
            "app.services.agent.tools.platform_tools.ProjectWorkflowService"
        ) as svc_class:
            instance = svc_class.return_value
            instance.list_project_workflows = AsyncMock(
                return_value=[
                    {
                        "source": "local",
                        "name": "rna-seq",
                        "pinned_workflow": newest_version,
                        "versions": [newest_version, old_version, pinned],
                    }
                ]
            )

            with patch(
                "app.services.agent.tools.platform_tools._serialize_workflow",
                side_effect=[
                    {
                        "id": str(uuid4()),
                        "name": "rna-seq",
                        "description": "Newest workflow",
                        "source": "local",
                        "engine": "nextflow",
                        "source_ref": "/tmp/new.nf",
                        "entrypoint_relpath": "main.nf",
                        "bundle_kind": "single_file",
                        "version": "2.0.0",
                        "estimated_time": None,
                        "schema_json": None,
                        "created_at": now.isoformat(),
                        "updated_at": now.isoformat(),
                    },
                    {
                        "id": str(uuid4()),
                        "name": "rna-seq",
                        "description": "Newest workflow",
                        "source": "local",
                        "engine": "nextflow",
                        "source_ref": "/tmp/new.nf",
                        "entrypoint_relpath": "main.nf",
                        "bundle_kind": "single_file",
                        "version": "2.0.0",
                        "estimated_time": None,
                        "schema_json": None,
                        "created_at": now.isoformat(),
                        "updated_at": now.isoformat(),
                    },
                    {
                        "id": str(uuid4()),
                        "name": "rna-seq",
                        "description": "Older workflow",
                        "source": "local",
                        "engine": "nextflow",
                        "source_ref": "/tmp/old.nf",
                        "entrypoint_relpath": "main.nf",
                        "bundle_kind": "single_file",
                        "version": "1.0.0",
                        "estimated_time": None,
                        "schema_json": None,
                        "created_at": now.isoformat(),
                        "updated_at": now.isoformat(),
                    },
                    {
                        "id": str(uuid4()),
                        "name": "rna-seq",
                        "description": "Pinned workflow",
                        "source": "local",
                        "engine": "nextflow",
                        "source_ref": "/tmp/pinned.nf",
                        "entrypoint_relpath": "main.nf",
                        "bundle_kind": "single_file",
                        "version": "0.9.0",
                        "estimated_time": None,
                        "schema_json": None,
                        "created_at": now.isoformat(),
                        "updated_at": now.isoformat(),
                    },
                ],
            ) as serialize_workflow:
                result = await tool.execute()

            instance.list_project_workflows.assert_awaited_once_with(project_id="proj-1")
            assert serialize_workflow.call_count == 4
            assert result.success
            workflow_group = result.data["workflows"][0]
            assert workflow_group["source"] == "local"
            assert workflow_group["name"] == "rna-seq"
            assert workflow_group["pinned_workflow"]["version"] == "2.0.0"
            assert [version["version"] for version in workflow_group["versions"]] == [
                "2.0.0",
                "1.0.0",
                "0.9.0",
            ]
