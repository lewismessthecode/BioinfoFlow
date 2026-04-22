from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.services.terminal_service import TerminalSessionManager


async def _next_message(
    queue: asyncio.Queue[dict], kind: str, *, contains: str | None = None
) -> dict:
    deadline = asyncio.get_running_loop().time() + 5
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise AssertionError(f"Timed out waiting for terminal message: {kind}")
        message = await asyncio.wait_for(queue.get(), timeout=remaining)
        if message["type"] == kind and (
            contains is None or contains in str(message.get("data", ""))
        ):
            return message


@pytest.mark.asyncio
async def test_terminal_session_manager_reuses_project_session(tmp_path: Path):
    manager = TerminalSessionManager(shell="/bin/sh", idle_timeout_seconds=30)
    first = None

    try:
        first = await manager.create_or_get(project_id="project-1", root_path=tmp_path)
        second = await manager.create_or_get(project_id="project-1", root_path=tmp_path)

        assert second.id == first.id
        assert second.cwd == str(tmp_path.resolve())
    finally:
        if first is not None:
            await manager.close_session(first.id)
        await manager.shutdown()


@pytest.mark.asyncio
async def test_terminal_session_manager_streams_output_and_reports_cwd(tmp_path: Path):
    manager = TerminalSessionManager(shell="/bin/sh", idle_timeout_seconds=30)
    session = await manager.create_or_get(project_id="project-2", root_path=tmp_path)
    try:
        queue = await manager.attach(session.id)

        await manager.send_input(session.id, "printf 'hello-terminal\\n'\n")
        output = await _next_message(queue, "output", contains="hello-terminal")
        assert "hello-terminal" in output["data"]

        nested = tmp_path / "nested"
        nested.mkdir()

        await manager.change_directory(session.id, "nested")
        cwd = await _next_message(queue, "cwd")
        assert cwd["cwd"] == str(nested.resolve())
    finally:
        await manager.close_session(session.id)
        await manager.shutdown()


@pytest.mark.asyncio
async def test_terminal_session_manager_replays_initial_output_to_late_subscribers(
    tmp_path: Path,
):
    shell_script = tmp_path / "prompt-shell.sh"
    shell_script.write_text(
        "#!/bin/sh\n"
        "printf 'bpiper/projects/demo main\\n❯ '\n"
        "exec /bin/sh\n"
    )
    shell_script.chmod(0o755)

    manager = TerminalSessionManager(shell=str(shell_script), idle_timeout_seconds=30)
    session = await manager.create_or_get(project_id="project-prompt", root_path=tmp_path)

    try:
        await asyncio.sleep(0.2)
        queue = await manager.attach(session.id)

        output = await _next_message(queue, "output", contains="bpiper/projects/demo main")
        assert "❯" in output["data"]
    finally:
        await manager.close_session(session.id)
        await manager.shutdown()


@pytest.mark.asyncio
async def test_terminal_session_manager_rejects_paths_outside_project_root(
    tmp_path: Path,
):
    manager = TerminalSessionManager(shell="/bin/sh", idle_timeout_seconds=30)
    session = await manager.create_or_get(project_id="project-3", root_path=tmp_path)
    try:
        with pytest.raises(PermissionError):
            await manager.change_directory(session.id, "../escape")
    finally:
        await manager.close_session(session.id)
        await manager.shutdown()


@pytest.mark.asyncio
async def test_terminal_session_manager_evicts_exited_sessions(tmp_path: Path):
    manager = TerminalSessionManager(shell="/bin/sh", idle_timeout_seconds=30)
    session = await manager.create_or_get(project_id="project-4", root_path=tmp_path)
    queue = await manager.attach(session.id)

    try:
        await manager.send_input(session.id, "exit\n")
        await _next_message(queue, "exit")

        deadline = asyncio.get_running_loop().time() + 5
        while asyncio.get_running_loop().time() < deadline:
            if (
                session.id not in manager._sessions_by_id
                and manager._project_index.get("project-4") is None
            ):
                break
            await asyncio.sleep(0.05)
        else:
            raise AssertionError("Exited session was not evicted from the manager")
    finally:
        await manager.shutdown()


def test_terminal_session_manager_builds_prompt_sanitized_environment(monkeypatch):
    monkeypatch.setenv("TERM", "screen-256color")
    manager = TerminalSessionManager(shell="/bin/zsh", idle_timeout_seconds=30)

    env = manager._build_terminal_environment()

    assert env["TERM"] == "xterm-256color"
    assert env["VIRTUAL_ENV_DISABLE_PROMPT"] == "1"
    assert env["PYENV_VIRTUALENV_DISABLE_PROMPT"] == "1"
    assert env["CONDA_CHANGEPS1"] == "no"
    assert env["STARSHIP_CONFIG"].endswith("terminal_starship.toml")


def test_terminal_session_manager_spawns_zsh_with_managed_prompt_config(
    monkeypatch, tmp_path: Path
):
    captured: dict[str, object] = {}

    class DummyProcess:
        pid = 12345

        def poll(self):
            return None

    monkeypatch.setattr("app.services.terminal_service.pty.openpty", lambda: (11, 12))
    monkeypatch.setattr("app.services.terminal_service.os.close", lambda _fd: None)

    def fake_popen(*args, **kwargs):
        captured["args"] = args[0]
        captured["env"] = kwargs["env"]
        captured["cwd"] = kwargs["cwd"]
        return DummyProcess()

    monkeypatch.setattr("app.services.terminal_service.subprocess.Popen", fake_popen)

    manager = TerminalSessionManager(shell="/bin/zsh", idle_timeout_seconds=30)
    session = manager._spawn_session(
        project_id="project-zsh",
        root_path=tmp_path,
        shell="/bin/zsh",
    )

    assert session.cwd == str(tmp_path)
    assert captured["args"] == ["/bin/zsh", "-i"]
    assert str(captured["cwd"]) == str(tmp_path)

    env = captured["env"]
    assert isinstance(env, dict)
    assert env["ZDOTDIR"].endswith("app/services/terminal_shell")
    assert env["HISTFILE"].endswith(".terminal_history")


def test_terminal_starship_config_disables_git_status_symbols():
    config_path = (
        Path(__file__).resolve().parents[2] / "app/services/terminal_starship.toml"
    )
    config = config_path.read_text()
    git_status_section = config.split("[git_status]", maxsplit=1)[1].split(
        "[character]", maxsplit=1
    )[0]

    assert "[git_status]" in config
    assert "disabled = true" in git_status_section


# --- Phase 2 Fix 11: Terminal environment variable filtering ---


def test_terminal_environment_filters_sensitive_vars(monkeypatch):
    """Sensitive env vars like API keys and secrets must be excluded."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-secret")
    monkeypatch.setenv("DATABASE_PASSWORD", "db-pass")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp-token")
    monkeypatch.setenv("MY_SECRET", "hidden")
    monkeypatch.setenv("SAFE_VAR", "visible")
    monkeypatch.setenv("PATH", "/usr/bin")

    manager = TerminalSessionManager(shell="/bin/sh")
    env = manager._build_terminal_environment()

    assert "ANTHROPIC_API_KEY" not in env
    assert "OPENAI_API_KEY" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert "DATABASE_PASSWORD" not in env
    assert "GITHUB_TOKEN" not in env
    assert "MY_SECRET" not in env
    assert env.get("SAFE_VAR") == "visible"
    assert env.get("PATH") == "/usr/bin"
