"""Tests for agent approval workflow via _check_risk() in the v2 runtime loop."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.enums import ApprovalStatus
from app.services.agent.runtime.loop import ToolRejectedError, _check_risk
from app.services.agent.tools.base import RiskLevel

# The production code reads the policy via:
#   getattr(settings, "agent_execution_policy", "auto")
# The field doesn't exist on the Pydantic Settings model, so it always
# falls back to "auto". To test other policies we patch the helper.
_POLICY_PATH = "app.services.agent.runtime.loop._requires_approval_by_policy"


@pytest.mark.asyncio
class TestCheckRiskRead:
    """READ risk level should auto-allow silently."""

    async def test_read_returns_immediately(self):
        on_event = AsyncMock()
        await _check_risk(
            "file_read", {"path": "/tmp"}, RiskLevel.READ, on_event=on_event
        )
        on_event.assert_not_called()


@pytest.mark.asyncio
class TestCheckRiskActLow:
    """ACT_LOW risk level should allow with info log."""

    async def test_act_low_returns_without_event(self):
        on_event = AsyncMock()
        await _check_risk(
            "file_write", {"path": "/tmp/out"}, RiskLevel.ACT_LOW, on_event=on_event
        )
        on_event.assert_not_called()


def _make_approval_mocks(*, status: str = ApprovalStatus.APPROVED, side_effect=None):
    """Create mock ApprovalService and related objects."""
    mock_svc = AsyncMock()
    mock_approval = MagicMock()
    mock_approval.id = "approval-test"
    mock_svc.get_approval_type_for_tool.return_value = "code_exec"
    mock_svc.create_approval.return_value = mock_approval

    if side_effect:
        mock_svc.wait_for_approval.side_effect = side_effect
    else:
        resolved = MagicMock()
        resolved.status = status
        mock_svc.wait_for_approval.return_value = resolved

    return mock_svc


@pytest.mark.asyncio
class TestCheckRiskActHigh:
    """ACT_HIGH risk level should require user approval."""

    async def test_execute_code_auto_policy_runs_without_approval(self):
        """Under the default 'auto' policy, execute_code at ACT_HIGH skips approval."""
        on_event = AsyncMock()
        await _check_risk(
            "execute_code",
            {"code": "print('hello')"},
            RiskLevel.ACT_HIGH,
            on_event=on_event,
            session=MagicMock(),
            conversation_id="conv-1",
        )
        on_event.assert_not_called()

    async def test_act_high_no_session_returns(self):
        """Without a DB session, ACT_HIGH should return (fail-open)."""
        on_event = AsyncMock()
        assert getattr(settings, "agent_execution_policy", "auto") == "auto"
        await _check_risk(
            "execute_code",
            {"code": "rm -rf /"},
            RiskLevel.ACT_HIGH,
            on_event=on_event,
            session=None,
            conversation_id="",
        )
        on_event.assert_not_called()

    async def test_act_high_no_conversation_id_returns(self):
        """Without a conversation ID, ACT_HIGH should return (fail-open)."""
        on_event = AsyncMock()
        mock_session = MagicMock()
        await _check_risk(
            "execute_code",
            {"code": "rm -rf /"},
            RiskLevel.ACT_HIGH,
            on_event=on_event,
            session=mock_session,
            conversation_id="",
        )
        on_event.assert_not_called()

    async def test_act_high_approved(self):
        """ACT_HIGH with approved response should return normally."""
        mock_svc = _make_approval_mocks(status=ApprovalStatus.APPROVED)
        with patch(_POLICY_PATH, return_value=True):
            with patch(
                "app.services.agent.approval_service.ApprovalService",
                return_value=mock_svc,
            ):
                on_event = AsyncMock()
                await _check_risk(
                    "execute_code",
                    {"code": "print('hello')"},
                    RiskLevel.ACT_HIGH,
                    on_event=on_event,
                    session=MagicMock(),
                    conversation_id="conv-1",
                )

        mock_svc.create_approval.assert_called_once()
        mock_svc.wait_for_approval.assert_called_once_with(
            "approval-test", timeout=None, poll_interval=1.0
        )
        on_event.assert_called_once()
        event_data = on_event.call_args[0][0]
        assert event_data["type"] == "status"
        assert event_data["metadata"]["requires_approval"] is True
        assert event_data["metadata"]["tool"] == "execute_code"

    async def test_act_high_rejected(self):
        """ACT_HIGH with rejected response should raise ToolRejectedError."""
        mock_svc = _make_approval_mocks(status=ApprovalStatus.REJECTED)

        with patch(_POLICY_PATH, return_value=True):
            with patch(
                "app.services.agent.approval_service.ApprovalService",
                return_value=mock_svc,
            ):
                on_event = AsyncMock()
                with pytest.raises(ToolRejectedError, match="User rejected execute_code"):
                    await _check_risk(
                        "execute_code",
                        {"code": "dangerous"},
                        RiskLevel.ACT_HIGH,
                        on_event=on_event,
                        session=MagicMock(),
                        conversation_id="conv-1",
                    )

    async def test_act_high_timeout(self):
        """ACT_HIGH with timeout should raise ToolRejectedError."""
        from app.services.agent.approval_service import ApprovalTimeoutError

        mock_svc = _make_approval_mocks(
            side_effect=ApprovalTimeoutError("approval-test", 300)
        )

        with patch(_POLICY_PATH, return_value=True):
            with patch(
                "app.services.agent.approval_service.ApprovalService",
                return_value=mock_svc,
            ):
                on_event = AsyncMock()
                with pytest.raises(ToolRejectedError, match="timed out"):
                    await _check_risk(
                        "execute_code",
                        {"code": "slow"},
                        RiskLevel.ACT_HIGH,
                        on_event=on_event,
                        session=MagicMock(),
                        conversation_id="conv-1",
                    )


@pytest.mark.asyncio
class TestCheckRiskUnknown:
    """Unknown risk levels should be logged and allowed."""

    async def test_unknown_risk_returns(self):
        on_event = AsyncMock()
        await _check_risk(
            "some_tool", {}, "unknown_level", on_event=on_event
        )
        on_event.assert_not_called()
