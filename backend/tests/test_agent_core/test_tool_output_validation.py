from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from uuid import UUID

import pytest

from app.services.agent_core.tools import middleware
from app.utils.exceptions import BadRequestError


class _State(str, Enum):
    READY = "ready"


def test_normalize_tool_output_converts_nested_platform_types() -> None:
    result = middleware.normalize_tool_output(
        {
            "nested": {
                "sampled_at": datetime(2026, 7, 29, 7, 30, tzinfo=timezone.utc),
                "id": UUID("12345678-1234-5678-1234-567812345678"),
                "state": _State.READY,
                "path": Path("/srv/bioinfoflow/project"),
                "ratio": Decimal("1.25"),
            }
        }
    )

    assert result == {
        "nested": {
            "sampled_at": "2026-07-29T07:30:00+00:00",
            "id": "12345678-1234-5678-1234-567812345678",
            "state": "ready",
            "path": "/srv/bioinfoflow/project",
            "ratio": 1.25,
        }
    }
    assert type(result["nested"]["state"]) is str


@pytest.mark.parametrize("value", [float("nan"), float("inf"), Decimal("NaN")])
def test_normalize_tool_output_rejects_non_finite_numbers(value: object) -> None:
    with pytest.raises(BadRequestError, match="finite JSON number"):
        middleware.normalize_tool_output({"value": value})


def test_normalize_tool_output_rejects_unknown_objects_with_path() -> None:
    with pytest.raises(
        BadRequestError,
        match=r"output\.nested\.value.*not JSON-serializable",
    ):
        middleware.normalize_tool_output({"nested": {"value": object()}})
