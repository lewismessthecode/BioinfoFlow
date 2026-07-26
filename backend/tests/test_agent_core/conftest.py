from __future__ import annotations

import pytest


@pytest.fixture
def run_shell_without_platform_sandbox(monkeypatch):
    """Keep orchestration tests independent from host namespace support."""
    monkeypatch.setattr(
        "app.services.agent_core.tools.execution.shell.SandboxRunner.build",
        lambda self, **kwargs: type(
            "SandboxResult",
            (),
            {"argv": ["bash", "-lc", kwargs["command"]]},
        )(),
    )
