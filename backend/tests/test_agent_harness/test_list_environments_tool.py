from __future__ import annotations

import pytest

from app.services.agent_harness.environment_scope import EnvironmentDescriptor
from app.services.agent_harness.tools.list_environments import ListEnvironmentsTool
from app.services.agent_harness.tools.specs import ToolExecutionContext


@pytest.mark.asyncio
async def test_list_environments_returns_the_frozen_run_scope() -> None:
    tool = ListEnvironmentsTool(
        (
            EnvironmentDescriptor(
                "local",
                "local",
                "Local",
                "This machine",
                "online",
            ),
            EnvironmentDescriptor(
                "ssh:gpu",
                "ssh",
                "GPU",
                "runner@gpu.internal:22",
                "offline",
            ),
        )
    )

    result = await tool.run({}, ToolExecutionContext(backend=object()))

    assert result == {
        "environments": [
            {
                "environment_id": "local",
                "kind": "local",
                "display_name": "Local",
                "description": "This machine",
                "status": "online",
            },
            {
                "environment_id": "ssh:gpu",
                "kind": "ssh",
                "display_name": "GPU",
                "description": "runner@gpu.internal:22",
                "status": "offline",
            },
        ]
    }
    assert "ssh:gpu" not in repr(tool.spec.input_schema)
