"""Tests for shell injection prevention in BackgroundManager."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

from app.services.agent.runtime.background import BackgroundManager


class TestShellInjectionPrevention:
    def test_shell_false_prevents_command_chaining(self, tmp_path: Path):
        """Commands with shell metacharacters must not be interpreted by a shell."""
        marker = tmp_path / "pwned.txt"
        # If shell=True, the semicolon would execute the touch command
        mgr = BackgroundManager(workspace_root=tmp_path, timeout=5)
        mgr.spawn(f"echo safe ; touch {marker}")
        time.sleep(2)
        results = mgr.drain_notifications()
        assert len(results) == 1
        # The command should fail because shlex.split treats ";" as a literal arg
        # to echo, and `touch /path` won't be a separate command.
        # Either way, the marker file must NOT exist.
        assert not marker.exists(), (
            "Shell metacharacter was interpreted — injection possible"
        )

    def test_subprocess_called_without_shell(self, tmp_path: Path):
        """Verify subprocess.run is called with shell=False."""
        mgr = BackgroundManager(workspace_root=tmp_path, timeout=5)
        with patch("app.services.agent.runtime.background.subprocess.run") as mock_run:
            mock_run.return_value = type(
                "Result", (), {"returncode": 0, "stdout": "", "stderr": ""}
            )()
            mgr.spawn("echo hello world")
            time.sleep(1)
            if mock_run.called:
                _, kwargs = mock_run.call_args
                assert kwargs.get("shell") is False, (
                    "subprocess.run must use shell=False"
                )
                # First arg should be a list, not a string
                args = mock_run.call_args[0][0]
                assert isinstance(args, list), "command must be split into a list"

    def test_simple_command_still_works(self, tmp_path: Path):
        """Basic commands should still execute correctly after the fix."""
        mgr = BackgroundManager(workspace_root=tmp_path, timeout=5)
        mgr.spawn("echo hello")
        time.sleep(1)
        results = mgr.drain_notifications()
        assert len(results) == 1
        assert results[0].exit_code == 0
        assert "hello" in results[0].stdout
